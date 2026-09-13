from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.discovery_engine import CandidateIntelligenceEngine
from app.models import AgentTask, ChannelListing, MarketSignal, MasterProduct, ProductCandidate, Supplier, SupplierProduct
from app.schemas import CandidateCreate, CandidateDecision, MarketSignalCreate, SelectionPolicy, TaskDecision

router = APIRouter(tags=["opportunity-intelligence"])
_policy = SelectionPolicy()


def _signals_for(db: Session, candidate: ProductCandidate) -> list[MarketSignal]:
    rows = db.scalars(select(MarketSignal)).all()
    matched = [
        row
        for row in rows
        if row.market == candidate.market
        and (
            row.channel in {candidate.recommended_channel, "MULTI"}
            or candidate.product_name.lower().split()[0] in row.keyword.lower()
            or any(token in row.keyword.lower() for token in candidate.product_name.lower().split() if len(token) > 3)
        )
    ]
    return matched or rows


def _apply_evaluation(candidate: ProductCandidate, db: Session) -> ProductCandidate:
    result = CandidateIntelligenceEngine(_policy).evaluate(candidate, _signals_for(db, candidate))
    selection = result["selection"]
    candidate.expected_margin_pct = result["expected_margin_pct"]
    candidate.market_demand = result["market_demand"]
    candidate.competition_intensity = result["competition_intensity"]
    candidate.zone = selection.zone
    candidate.opportunity_score = selection.opportunity_score
    candidate.decision = selection.decision
    candidate.risk_score = selection.risk_score
    candidate.status = "EVALUATED"
    candidate.rationale = "；".join(selection.reasons)
    candidate.next_actions = "；".join(selection.recommended_actions)
    candidate.evaluated_at = datetime.utcnow()
    return candidate


def _candidate_dict(row: ProductCandidate) -> dict:
    return {
        "id": row.id,
        "candidate_code": row.candidate_code,
        "product_name": row.product_name,
        "source": row.source,
        "supplier_name": row.supplier_name,
        "supplier_sku": row.supplier_sku,
        "market": row.market,
        "recommended_channel": row.recommended_channel,
        "supplier_price": row.supplier_price,
        "estimated_landed_cost": row.estimated_landed_cost,
        "target_retail_price": row.target_retail_price,
        "expected_margin_pct": row.expected_margin_pct,
        "exclusive_rights": row.exclusive_rights,
        "zone": row.zone,
        "opportunity_score": row.opportunity_score,
        "decision": row.decision,
        "risk_score": row.risk_score,
        "status": row.status,
        "rationale": row.rationale,
        "next_actions": row.next_actions,
        "promoted_master_product_id": row.promoted_master_product_id,
    }


def pipeline_stats(db: Session) -> dict:
    candidates = db.scalars(select(ProductCandidate)).all()
    pipeline = {"DISCOVERED": 0, "EVALUATED": 0, "PROMOTED": 0, "REJECTED": 0}
    for row in candidates:
        pipeline[row.status] = pipeline.get(row.status, 0) + 1
    return {
        "candidate_products": len(candidates),
        "scale_candidates": sum(1 for row in candidates if row.decision == "SCALE" and row.status != "REJECTED"),
        "candidate_pipeline": pipeline,
    }


def _promote(db: Session, candidate: ProductCandidate) -> MasterProduct:
    sku = f"JOY-{candidate.candidate_code}"
    existing = db.scalar(select(MasterProduct).where(MasterProduct.sku == sku))
    if existing:
        product = existing
    else:
        product = MasterProduct(
            sku=sku,
            name=candidate.product_name,
            target_market=candidate.market,
            retail_price=candidate.target_retail_price,
            landed_cost=candidate.estimated_landed_cost,
            expected_margin_pct=candidate.expected_margin_pct,
            zone=candidate.zone,
            opportunity_score=candidate.opportunity_score,
            decision=candidate.decision,
            selection_reason=candidate.rationale,
        )
        db.add(product)
        db.flush()
    supplier = db.scalar(select(Supplier).where(Supplier.name == candidate.supplier_name))
    if supplier is None:
        supplier = Supplier(name=candidate.supplier_name or "Unknown Supplier")
        db.add(supplier)
        db.flush()
    linked = db.scalar(
        select(SupplierProduct).where(
            SupplierProduct.master_product_id == product.id,
            SupplierProduct.supplier_sku == candidate.supplier_sku,
        )
    )
    if linked is None:
        db.add(
            SupplierProduct(
                supplier_id=supplier.id,
                master_product_id=product.id,
                supplier_sku=candidate.supplier_sku or candidate.candidate_code,
                supplier_price=candidate.supplier_price,
                exclusive_rights=candidate.exclusive_rights,
                authorization_scope="US online channels" if candidate.exclusive_rights else "non-exclusive",
            )
        )
    listing = db.scalar(
        select(ChannelListing).where(
            ChannelListing.master_product_id == product.id,
            ChannelListing.channel == candidate.recommended_channel,
        )
    )
    if listing is None:
        db.add(
            ChannelListing(
                master_product_id=product.id,
                channel=candidate.recommended_channel,
                market=candidate.market,
                status="DRAFT",
                selling_price=candidate.target_retail_price,
            )
        )
    candidate.status = "PROMOTED"
    candidate.promoted_master_product_id = product.id
    return product


@router.get("/api/opportunities")
def opportunities(db: Session = Depends(get_db)) -> dict:
    candidates = db.scalars(select(ProductCandidate).order_by(ProductCandidate.opportunity_score.desc())).all()
    signals = db.scalars(select(MarketSignal).order_by(MarketSignal.observed_at.desc())).all()
    pulse: dict[tuple[str, str], dict] = {}
    for row in signals:
        key = (row.market, row.channel)
        current = pulse.get(key)
        if current is None:
            pulse[key] = {
                "market": row.market,
                "channel": row.channel,
                "demand_score": row.demand_score,
                "growth_score": row.growth_score,
                "competition_score": row.competition_score,
                "n": 1,
            }
        else:
            current["demand_score"] += row.demand_score
            current["growth_score"] += row.growth_score
            current["competition_score"] += row.competition_score
            current["n"] += 1
    market_pulse = []
    for item in pulse.values():
        n = item.pop("n")
        market_pulse.append(
            {
                "market": item["market"],
                "channel": item["channel"],
                "demand_score": round(item["demand_score"] / n, 1),
                "growth_score": round(item["growth_score"] / n, 1),
                "competition_score": round(item["competition_score"] / n, 1),
            }
        )
    market_pulse.sort(key=lambda row: row["growth_score"], reverse=True)
    return {
        "summary": {
            "signals": len(signals),
            "candidates": len(candidates),
            "scale": sum(1 for row in candidates if row.decision == "SCALE"),
            "test": sum(1 for row in candidates if row.decision == "TEST"),
            "exclusive": sum(1 for row in candidates if row.zone == "EXCLUSIVE"),
        },
        "market_pulse": market_pulse,
        "candidates": [_candidate_dict(row) for row in candidates],
    }


@router.get("/api/market-signals")
def list_signals(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(MarketSignal).order_by(MarketSignal.id.desc())).all()
    return [
        {
            "id": row.id,
            "source": row.source,
            "market": row.market,
            "channel": row.channel,
            "keyword": row.keyword,
            "demand_score": row.demand_score,
            "growth_score": row.growth_score,
            "social_velocity": row.social_velocity,
            "competition_score": row.competition_score,
            "median_price": row.median_price,
            "confidence": row.confidence,
        }
        for row in rows
    ]


@router.post("/api/market-signals")
def create_signal(payload: MarketSignalCreate, db: Session = Depends(get_db)) -> dict:
    row = MarketSignal(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "keyword": row.keyword}


@router.get("/api/candidates")
def list_candidates(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(ProductCandidate).order_by(ProductCandidate.opportunity_score.desc())).all()
    return [_candidate_dict(row) for row in rows]


@router.post("/api/candidates")
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db)) -> dict:
    count = db.scalar(select(func.count()).select_from(ProductCandidate)) or 0
    row = ProductCandidate(candidate_code=f"CAND-{count + 1:03d}", **payload.model_dump())
    db.add(row)
    db.flush()
    _apply_evaluation(row, db)
    db.commit()
    db.refresh(row)
    return _candidate_dict(row)


@router.post("/api/candidates/{candidate_id}/evaluate")
def evaluate_candidate(candidate_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(ProductCandidate, candidate_id)
    if row is None:
        raise HTTPException(404, "candidate not found")
    _apply_evaluation(row, db)
    db.commit()
    db.refresh(row)
    return _candidate_dict(row)


@router.post("/api/candidates/{candidate_id}/decision")
def decide_candidate(candidate_id: int, payload: CandidateDecision, db: Session = Depends(get_db)) -> dict:
    row = db.get(ProductCandidate, candidate_id)
    if row is None:
        raise HTTPException(404, "candidate not found")
    if payload.action == "REJECT":
        row.status = "REJECTED"
    elif payload.action == "REEVALUATE":
        _apply_evaluation(row, db)
    else:
        _promote(db, row)
    db.commit()
    db.refresh(row)
    return _candidate_dict(row)


@router.post("/api/agent-tasks/{task_id}/decision")
def decide_task(task_id: int, payload: TaskDecision, db: Session = Depends(get_db)) -> dict:
    task = db.get(AgentTask, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    task.status = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "REEVALUATE": "OPEN"}[payload.action]
    if payload.action == "REEVALUATE":
        task.recommendation = (payload.note or task.recommendation) + "\n[CEO requested re-analysis]"
    db.commit()
    return {"id": task.id, "status": task.status}
