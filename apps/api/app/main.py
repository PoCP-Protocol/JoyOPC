from __future__ import annotations

from datetime import datetime, timedelta
import csv
import hashlib
import io
import json
import mimetypes
import os
import shutil
import time
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .adapters.saleor import SaleorAdapter
from .config import MAX_UPLOAD_MB, MEDIA_DIR, SCHEMA_MODE, UPLOAD_DIR, WEB_DIR, upsert_dotenv
from .content_factory import content_factory
from .listing_pack import build_listing_pack
from .content_factory import content_factory
from .database import Base, engine, get_db
from .foundation_bootstrap import ensure_v05a_bootstrap_schema
from . import foundation_models  # noqa: F401
from . import operations_models  # noqa: F401
from .fulfillment_runtime import allocate_unallocated_orders
from .discovery_engine import CandidateIntelligenceEngine
from .ingestion import MarketSignalFileImporter, SupplierCatalogImporter, json_dumps
from .adapters.market.crawler import CrawlError, PublicPageCrawler
from .market_data import GoogleTrendsAdapter
from .multimodal import AssetContext, MultimodalGateway
from .product_unit import candidate_orm_kwargs, copy_unit, dump_json_list, unit_api_dict
from .models import (
    AgentTask,
    ChannelAccount,
    ChannelCostEntry,
    ChannelListing,
    ChannelSyncRun,
    CommerceOrderItem,
    ChannelOrderLink,
    CommerceOrder,
    IngestionBatch,
    ImportedProductRecord,
    MarketConnectorRun,
    MarketSignal,
    MasterProduct,
    MultimodalAnalysis,
    ProductAsset,
    ProductCandidate,
    Supplier,
    SupplierProduct,
)
from .schemas import (
    CandidateCreate,
    ChannelAccountCreate,
    ChannelOrderSyncRequest,
    ChannelPublishRequest,
    ShopifyConnectRequest,
    CostEntryCreate,
    CandidateDecision,
    GoogleTrendsPull,
    MarketSignalBatch,
    MarketSignalCreate,
    PublicPageCrawl,
    MixPolicy,
    SelectionInput,
    SelectionPolicy,
    SelectionResult,
)
from .operating_os import (
    MixItem,
    analyze_portfolio,
    approve_management_gate,
    diagnose_sku,
    implementation_play,
    publish_management_error,
    talent_for_agent,
)
from .seed import seed_demo
from .selection_engine import ProductZoneEngine
from .channel_runtime import (
    account_dict,
    check_account,
    first_publishable_master_product,
    publish_master_product,
    reconcile_profit,
    shopify_channel_account,
    sku_profit,
    source_fulfillment,
    sync_orders,
)
from .opensource_stack import catalog as opensource_catalog
from .adapters.saleor_mcp import saleor_mcp
from .sku_matcher import match_master_sku
from .adapters.channels.shopify import ShopifyAdapter, looks_like_admin_token, normalize_shop_domain
from .routers.foundation import router as foundation_router
from .routers.operations import router as operations_router

app = FastAPI(title="JoyOPC API", version="0.5.0b1")
app.include_router(foundation_router)
app.include_router(operations_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_policy = SelectionPolicy()
_mix_policy = MixPolicy()


def _portfolio_mix_items(db: Session) -> list[MixItem]:
    products = db.scalars(select(MasterProduct).where(MasterProduct.active.is_(True))).all()
    suppliers = db.scalars(select(SupplierProduct)).all()
    exclusive_by_master = {row.master_product_id: row.exclusive_rights for row in suppliers}
    profit_rows = {row["sku"]: row for row in sku_profit(db)}
    items: list[MixItem] = []
    for p in products:
        profit = profit_rows.get(p.sku, {})
        exclusive = exclusive_by_master.get(p.id, p.zone == "EXCLUSIVE")
        zone_defaults = {
            "EXCLUSIVE": dict(uniqueness=82, channel_control=78, cost_advantage=70, supply_advantage=75, content_advantage=80, brand_advantage=60, market_demand=80, competition_intensity=50, return_risk=28, compliance_risk=30),
            "ADVANTAGE": dict(uniqueness=62, channel_control=55, cost_advantage=80, supply_advantage=82, content_advantage=75, brand_advantage=48, market_demand=74, competition_intensity=62, return_risk=28, compliance_risk=30),
            "HOMOGENEOUS": dict(uniqueness=28, channel_control=28, cost_advantage=50, supply_advantage=55, content_advantage=40, brand_advantage=30, market_demand=64, competition_intensity=85, return_risk=48, compliance_risk=34),
        }[p.zone]
        items.append(
            MixItem(
                name=p.name,
                zone=p.zone,
                expected_margin_pct=p.expected_margin_pct,
                gmv=float(profit.get("net_sales") or 0),
                contribution_profit=float(profit.get("contribution_profit") or 0),
                decision=p.decision,
                status="ACTIVE",
                exclusive_rights=bool(exclusive),
                opportunity_score=p.opportunity_score,
                market=p.target_market,
                channel=(p.listings[0].channel if p.listings else "TikTok Shop"),
                **zone_defaults,
            )
        )
    candidates = db.scalars(select(ProductCandidate)).all()
    for c in candidates:
        if c.status in {"REJECTED", "PROMOTED"}:
            continue
        items.append(
            MixItem(
                name=c.product_name,
                zone=c.zone,
                expected_margin_pct=c.expected_margin_pct,
                decision=c.decision,
                status=c.status,
                uniqueness=c.uniqueness,
                channel_control=c.channel_control,
                cost_advantage=c.cost_advantage,
                supply_advantage=c.supply_advantage,
                content_advantage=c.content_advantage,
                brand_advantage=c.brand_advantage,
                market_demand=c.market_demand,
                competition_intensity=c.competition_intensity,
                compliance_risk=c.compliance_risk,
                return_risk=c.return_risk,
                cash_cycle_days=c.cash_cycle_days,
                exclusive_rights=c.exclusive_rights,
                risk_score=c.risk_score,
                opportunity_score=c.opportunity_score,
                market=c.market,
                channel=c.recommended_channel,
            )
        )
    return items


def _homogeneous_share(db: Session) -> tuple[float, float]:
    os_state = analyze_portfolio(_portfolio_mix_items(db), _mix_policy)
    return os_state["mix"]["sku_share"]["HOMOGENEOUS"], _mix_policy.homogeneous_alert_pct


def _assert_publish_management(db: Session, product: MasterProduct) -> None:
    share, alert = _homogeneous_share(db)
    error = publish_management_error(
        zone=product.zone,
        decision=product.decision,
        homogeneous_share=share,
        homogeneous_alert=alert,
    )
    if error:
        raise HTTPException(409, error)


@app.on_event("startup")
def startup() -> None:
    last: Exception | None = None
    for _ in range(20):
        try:
            if SCHEMA_MODE == "bootstrap":
                Base.metadata.create_all(bind=engine)
            else:
                with engine.connect() as conn:
                    conn.exec_driver_sql("SELECT 1")
            last = None
            break
        except OperationalError as exc:
            last = exc
            time.sleep(0.5)
    if last is not None:
        raise RuntimeError(
            f"JoyOPC cannot connect to the database ({engine.url.render_as_string(hide_password=True)}). "
            "Start Postgres with `docker compose up -d postgres`."
        ) from last
    with next(get_db()) as db:
        seed_demo(db)
        if SCHEMA_MODE == "bootstrap":
            ensure_v05a_bootstrap_schema(engine)
        reconcile_profit(db)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "product": "JoyOPC",
        "version": "0.5.0b1",
        "schema_mode": SCHEMA_MODE,
        "database": engine.dialect.name,
        "database_url": engine.url.render_as_string(hide_password=True),
    }


def _candidate_dict(c: ProductCandidate) -> dict:
    return {
        "id": c.id,
        "candidate_code": c.candidate_code,
        "product_name": c.product_name,
        "source": c.source,
        "supplier_name": c.supplier_name,
        "supplier_sku": c.supplier_sku,
        "market": c.market,
        "recommended_channel": c.recommended_channel,
        "supplier_price": c.supplier_price,
        "estimated_landed_cost": c.estimated_landed_cost,
        "target_retail_price": c.target_retail_price,
        "expected_margin_pct": c.expected_margin_pct,
        "zone": c.zone,
        "opportunity_score": c.opportunity_score,
        "decision": c.decision,
        "risk_score": c.risk_score,
        "status": c.status,
        "rationale": c.rationale,
        "next_actions": c.next_actions,
        "promoted_master_product_id": c.promoted_master_product_id,
        "philosophy": diagnose_sku(
            SelectionInput(
                product_name=c.product_name,
                exclusive_rights=c.exclusive_rights,
                uniqueness=c.uniqueness,
                channel_control=c.channel_control,
                cost_advantage=c.cost_advantage,
                supply_advantage=c.supply_advantage,
                content_advantage=c.content_advantage,
                brand_advantage=c.brand_advantage,
                market_demand=c.market_demand,
                competition_intensity=c.competition_intensity,
                expected_margin_pct=c.expected_margin_pct,
                compliance_risk=c.compliance_risk,
                return_risk=c.return_risk,
                cash_cycle_days=c.cash_cycle_days,
            ),
            zone=c.zone,
            decision=c.decision,
            risk_score=c.risk_score,
        ).model_dump(),
        "product_unit": unit_api_dict(c, market=c.market),
    }


def _relevant_signals(db: Session, candidate: ProductCandidate) -> list[MarketSignal]:
    rows = db.scalars(select(MarketSignal).where(MarketSignal.market == candidate.market)).all()
    if not rows:
        return []
    name_tokens = {x.lower() for x in candidate.product_name.replace("-", " ").split() if len(x) > 2}
    matched = [s for s in rows if any(token in s.keyword.lower() for token in name_tokens)]
    return matched or rows


def _evaluate_candidate(db: Session, candidate: ProductCandidate) -> ProductCandidate:
    intelligence = CandidateIntelligenceEngine(_policy)
    result = intelligence.evaluate(candidate, _relevant_signals(db, candidate))
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
    candidate.cert_gap_json = dump_json_list(selection.cert_gap)
    candidate.needs_hardware_gate = selection.needs_hardware_gate
    return candidate


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    orders = db.scalars(select(CommerceOrder)).all()
    products = db.scalars(select(MasterProduct).where(MasterProduct.active.is_(True))).all()
    tasks = db.scalars(select(AgentTask).order_by(AgentTask.id.desc()).limit(8)).all()
    listings = db.scalars(select(ChannelListing)).all()
    candidates = db.scalars(select(ProductCandidate)).all()

    gmv = round(sum(o.gross_sales for o in orders), 2)
    profit = round(sum(o.contribution_profit for o in orders), 2)
    profit_rate = round(profit / gmv * 100, 1) if gmv else 0
    channel_sales: dict[str, float] = {}
    for o in orders:
        channel_sales[o.channel] = round(channel_sales.get(o.channel, 0) + o.gross_sales, 2)

    zone_counts = {"EXCLUSIVE": 0, "ADVANTAGE": 0, "HOMOGENEOUS": 0}
    for p in products:
        zone_counts[p.zone] = zone_counts.get(p.zone, 0) + 1

    pipeline = {"DISCOVERED": 0, "EVALUATED": 0, "PROMOTED": 0, "REJECTED": 0}
    for c in candidates:
        pipeline[c.status] = pipeline.get(c.status, 0) + 1

    return {
        "company": "JoyOPC AI Toy Trading",
        "kpis": {
            "gmv": gmv,
            "orders": len(orders),
            "contribution_profit": profit,
            "contribution_margin_pct": profit_rate,
            "active_products": len(products),
            "active_listings": sum(1 for l in listings if l.status == "ACTIVE"),
            "candidate_products": len(candidates),
            "scale_candidates": sum(1 for c in candidates if c.decision == "SCALE" and c.status != "REJECTED"),
        },
        "channel_sales": channel_sales,
        "zone_counts": zone_counts,
        "candidate_pipeline": pipeline,
        "operating_os": analyze_portfolio(_portfolio_mix_items(db), _mix_policy),
        "ceo_decisions": [
            {
                "id": t.id,
                "agent": t.agent,
                "title": t.title,
                "priority": t.priority,
                "recommendation": t.recommendation,
                **talent_for_agent(t.agent),
            }
            for t in tasks
            if t.requires_ceo_approval and t.status == "OPEN"
        ],
        "agent_feed": [
            {
                "id": t.id,
                "agent": t.agent,
                "title": t.title,
                "priority": t.priority,
                "status": t.status,
                "requires_ceo_approval": t.requires_ceo_approval,
                "recommendation": t.recommendation,
                **talent_for_agent(t.agent),
            }
            for t in tasks
        ],
    }


@app.get("/api/products")
def products(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(MasterProduct).order_by(MasterProduct.opportunity_score.desc())).all()
    return [
        {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "target_market": p.target_market,
            "retail_price": p.retail_price,
            "landed_cost": p.landed_cost,
            "expected_margin_pct": p.expected_margin_pct,
            "zone": p.zone,
            "opportunity_score": p.opportunity_score,
            "decision": p.decision,
            "selection_reason": p.selection_reason,
            "product_unit": unit_api_dict(p, market=p.target_market),
        }
        for p in rows
    ]


@app.get("/api/opportunities")
def opportunity_center(db: Session = Depends(get_db)) -> dict:
    candidates = db.scalars(select(ProductCandidate).order_by(ProductCandidate.opportunity_score.desc())).all()
    signals = db.scalars(select(MarketSignal).order_by(MarketSignal.observed_at.desc())).all()
    market_pulse = {}
    for s in signals:
        key = f"{s.market}:{s.channel}"
        bucket = market_pulse.setdefault(key, {"market": s.market, "channel": s.channel, "demand": [], "growth": [], "competition": []})
        bucket["demand"].append(s.demand_score)
        bucket["growth"].append(s.growth_score)
        bucket["competition"].append(s.competition_score)

    pulse = []
    for value in market_pulse.values():
        pulse.append({
            "market": value["market"],
            "channel": value["channel"],
            "demand_score": round(sum(value["demand"]) / len(value["demand"]), 1),
            "growth_score": round(sum(value["growth"]) / len(value["growth"]), 1),
            "competition_score": round(sum(value["competition"]) / len(value["competition"]), 1),
        })

    return {
        "market_pulse": sorted(pulse, key=lambda x: x["growth_score"], reverse=True),
        "candidates": [_candidate_dict(c) for c in candidates],
        "summary": {
            "signals": len(signals),
            "candidates": len(candidates),
            "scale": sum(c.decision == "SCALE" and c.status != "REJECTED" for c in candidates),
            "test": sum(c.decision == "TEST" and c.status != "REJECTED" for c in candidates),
            "exclusive": sum(c.zone == "EXCLUSIVE" and c.status != "REJECTED" for c in candidates),
        },
    }


@app.get("/api/market-signals")
def market_signals(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(MarketSignal).order_by(MarketSignal.id.desc())).all()
    return [
        {
            "id": s.id,
            "source": s.source,
            "market": s.market,
            "channel": s.channel,
            "keyword": s.keyword,
            "demand_score": s.demand_score,
            "growth_score": s.growth_score,
            "social_velocity": s.social_velocity,
            "competition_score": s.competition_score,
            "median_price": s.median_price,
            "confidence": s.confidence,
        }
        for s in rows
    ]


@app.post("/api/market-signals")
def create_market_signal(payload: MarketSignalCreate, db: Session = Depends(get_db)) -> dict:
    row = MarketSignal(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": "created"}


@app.get("/api/candidates")
def candidates(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(ProductCandidate).order_by(ProductCandidate.opportunity_score.desc())).all()
    return [_candidate_dict(c) for c in rows]


@app.post("/api/candidates")
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db)) -> dict:
    code = f"CAND-{uuid4().hex[:8].upper()}"
    row = ProductCandidate(candidate_code=code, **candidate_orm_kwargs(payload.model_dump()))
    db.add(row)
    db.flush()
    _evaluate_candidate(db, row)
    db.commit()
    db.refresh(row)
    return _candidate_dict(row)


@app.post("/api/candidates/{candidate_id}/evaluate")
def evaluate_candidate(candidate_id: int, db: Session = Depends(get_db)) -> dict:
    candidate = db.get(ProductCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    _evaluate_candidate(db, candidate)
    db.commit()
    db.refresh(candidate)
    return _candidate_dict(candidate)


@app.post("/api/candidates/{candidate_id}/decision")
def decide_candidate(candidate_id: int, payload: CandidateDecision, db: Session = Depends(get_db)) -> dict:
    candidate = db.get(ProductCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    if payload.action == "REEVALUATE":
        _evaluate_candidate(db, candidate)
    elif payload.action == "REJECT":
        candidate.status = "REJECTED"
        play = implementation_play(candidate.zone, diagnose_sku(
            SelectionInput(
                product_name=candidate.product_name,
                exclusive_rights=candidate.exclusive_rights,
                uniqueness=candidate.uniqueness,
                channel_control=candidate.channel_control,
                cost_advantage=candidate.cost_advantage,
                supply_advantage=candidate.supply_advantage,
                content_advantage=candidate.content_advantage,
                brand_advantage=candidate.brand_advantage,
                market_demand=candidate.market_demand,
                competition_intensity=candidate.competition_intensity,
                expected_margin_pct=candidate.expected_margin_pct,
                compliance_risk=candidate.compliance_risk,
                return_risk=candidate.return_risk,
                cash_cycle_days=candidate.cash_cycle_days,
            ),
            zone=candidate.zone,
            decision="REJECT",
            risk_score=candidate.risk_score,
        ))
        db.add(AgentTask(
            agent=play["owner"],
            title=f"换局 · {candidate.product_name} 已淘汰",
            priority="MEDIUM",
            status="DONE",
            recommendation=payload.note or play["recommendation"],
        ))
    else:
        share, alert = _homogeneous_share(db)
        ph = diagnose_sku(
            SelectionInput(
                product_name=candidate.product_name,
                exclusive_rights=candidate.exclusive_rights,
                uniqueness=candidate.uniqueness,
                channel_control=candidate.channel_control,
                cost_advantage=candidate.cost_advantage,
                supply_advantage=candidate.supply_advantage,
                content_advantage=candidate.content_advantage,
                brand_advantage=candidate.brand_advantage,
                market_demand=candidate.market_demand,
                competition_intensity=candidate.competition_intensity,
                expected_margin_pct=candidate.expected_margin_pct,
                compliance_risk=candidate.compliance_risk,
                return_risk=candidate.return_risk,
                cash_cycle_days=candidate.cash_cycle_days,
            ),
            zone=candidate.zone,
            decision=candidate.decision,
            risk_score=candidate.risk_score,
        )
        gate = approve_management_gate(
            zone=candidate.zone,
            decision=candidate.decision,
            quality=ph.advantage_quality,
            homogeneous_share=share,
            homogeneous_alert=alert,
        )
        if gate["blocked"]:
            raise HTTPException(409, " ".join(gate["reasons"]))
        candidate.decision = gate["force_decision"]
        play = implementation_play(candidate.zone, ph)
        if candidate.promoted_master_product_id:
            candidate.status = "PROMOTED"
        else:
            master = MasterProduct(
                sku=f"JOY-{uuid4().hex[:8].upper()}",
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
            copy_unit(candidate, master)
            db.add(master)
            db.flush()

            supplier_name = candidate.supplier_name.strip() or "Unassigned Supplier"
            supplier = db.scalar(select(Supplier).where(Supplier.name == supplier_name))
            if supplier is None:
                supplier = Supplier(name=supplier_name, supports_dropship=False)
                db.add(supplier)
                db.flush()
            db.add(
                SupplierProduct(
                    supplier_id=supplier.id,
                    master_product_id=master.id,
                    supplier_sku=candidate.supplier_sku or candidate.candidate_code,
                    supplier_price=candidate.supplier_price,
                    moq=1,
                    lead_time_days=7,
                    exclusive_rights=candidate.exclusive_rights,
                    authorization_scope=f"{candidate.market} online channels" if candidate.exclusive_rights else "non-exclusive",
                )
            )
            db.add(
                ChannelListing(
                    master_product_id=master.id,
                    channel=candidate.recommended_channel,
                    market=candidate.market,
                    status="DRAFT",
                    selling_price=candidate.target_retail_price,
                )
            )
            candidate.promoted_master_product_id = master.id
            candidate.status = "PROMOTED"
            extra = "；".join(gate["reasons"])
            db.add(AgentTask(
                agent=play["owner"],
                title=f"{play['title']} · {candidate.product_name}",
                priority="HIGH",
                recommendation=f"{play['recommendation']} 已进入 Master Product / DRAFT Listing。{extra}".strip(),
            ))
    db.commit()
    db.refresh(candidate)
    return _candidate_dict(candidate)


@app.get("/api/operating-os")
def operating_os(db: Session = Depends(get_db)) -> dict:
    return analyze_portfolio(_portfolio_mix_items(db), _mix_policy)


@app.get("/api/crossborder-playbook")
def crossborder_playbook(db: Session = Depends(get_db)) -> dict:
    os_state = analyze_portfolio(_portfolio_mix_items(db), _mix_policy)
    return os_state.get("crossborder") or {}


@app.get("/api/selection/mix-policy", response_model=MixPolicy)
def get_mix_policy() -> MixPolicy:
    return _mix_policy


@app.put("/api/selection/mix-policy", response_model=MixPolicy)
def update_mix_policy(policy: MixPolicy) -> MixPolicy:
    global _mix_policy
    _mix_policy = policy
    return _mix_policy


@app.get("/api/selection/policy", response_model=SelectionPolicy)
def get_policy() -> SelectionPolicy:
    return _policy


@app.put("/api/selection/policy", response_model=SelectionPolicy)
def update_policy(policy: SelectionPolicy) -> SelectionPolicy:
    global _policy
    _policy = policy
    return _policy


@app.post("/api/selection/evaluate", response_model=SelectionResult)
def evaluate_selection(payload: SelectionInput) -> SelectionResult:
    return ProductZoneEngine(_policy).evaluate(payload)


@app.get("/api/agent-tasks")
def agent_tasks(db: Session = Depends(get_db)) -> list[dict]:
    tasks = db.scalars(select(AgentTask).order_by(AgentTask.id.desc())).all()
    return [
        {
            "id": t.id,
            "agent": t.agent,
            "title": t.title,
            "priority": t.priority,
            "status": t.status,
            "requires_ceo_approval": t.requires_ceo_approval,
            "recommendation": t.recommendation,
            **talent_for_agent(t.agent),
        }
        for t in tasks
    ]


@app.post("/api/agent-tasks/{task_id}/decision")
def decide_agent_task(task_id: int, payload: CandidateDecision, db: Session = Depends(get_db)) -> dict:
    task = db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(404, "Agent task not found")
    task.status = "APPROVED" if payload.action == "APPROVE" else "REJECTED" if payload.action == "REJECT" else "OPEN"
    db.commit()
    return {"id": task.id, "status": task.status}



def _safe_upload_name(filename: str) -> str:
    suffix = Path(filename or "upload.bin").suffix.lower()
    stem = "".join(ch for ch in Path(filename or "upload").stem if ch.isalnum() or ch in {"-", "_"})[:80] or "upload"
    return f"{stem}-{uuid4().hex[:10]}{suffix}"


def _save_upload(file: UploadFile, *, subdir: str) -> tuple[Path, str, int]:
    target_dir = UPLOAD_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _safe_upload_name(file.filename or "upload.bin")
    digest = hashlib.sha256()
    size = 0
    with target.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(413, f"File exceeds {MAX_UPLOAD_MB} MB limit")
            digest.update(chunk)
            out.write(chunk)
    return target, digest.hexdigest(), size


def _asset_type(filename: str, mime_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if (mime_type or "").startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "IMAGE"
    if mime_type == "application/pdf" or suffix == ".pdf":
        return "PDF"
    if (mime_type or "").startswith("text/") or suffix in {".txt", ".md"}:
        return "TEXT"
    return "OTHER"


@app.get("/api/data-pipeline")
def data_pipeline(db: Session = Depends(get_db)) -> dict:
    batches = db.scalars(select(IngestionBatch).order_by(IngestionBatch.id.desc()).limit(12)).all()
    assets = db.scalars(select(ProductAsset).order_by(ProductAsset.id.desc()).limit(12)).all()
    analyses = db.scalars(select(MultimodalAnalysis).order_by(MultimodalAnalysis.id.desc()).limit(12)).all()
    connector_runs = db.scalars(select(MarketConnectorRun).order_by(MarketConnectorRun.id.desc()).limit(12)).all()
    gateway = MultimodalGateway()
    return {
        "multimodal": gateway.status(),
        "counts": {
            "batches": db.query(IngestionBatch).count(),
            "assets": db.query(ProductAsset).count(),
            "analyses": db.query(MultimodalAnalysis).count(),
            "market_signals": db.query(MarketSignal).count(),
        },
        "batches": [{
            "id": x.id, "batch_type": x.batch_type, "filename": x.filename, "source": x.source,
            "status": x.status, "total_records": x.total_records, "accepted_records": x.accepted_records,
            "rejected_records": x.rejected_records, "error_message": x.error_message,
            "created_at": x.created_at.isoformat() if x.created_at else None,
        } for x in batches],
        "assets": [{
            "id": x.id, "candidate_id": x.candidate_id, "filename": x.filename, "asset_type": x.asset_type,
            "mime_type": x.mime_type, "byte_size": x.byte_size, "sha256": x.sha256,
        } for x in assets],
        "analyses": [{
            "id": x.id, "candidate_id": x.candidate_id, "provider": x.provider, "model": x.model,
            "status": x.status, "confidence": x.confidence, "applied_to_candidate": x.applied_to_candidate,
            "created_at": x.created_at.isoformat() if x.created_at else None,
        } for x in analyses],
        "connector_runs": [{
            "id": x.id, "connector": x.connector, "market": x.market, "status": x.status,
            "records_received": x.records_received, "error_message": x.error_message,
            "created_at": x.created_at.isoformat() if x.created_at else None,
        } for x in connector_runs],
    }


@app.post("/api/imports/supplier-catalog")
def import_supplier_catalog(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    filename = file.filename or "supplier.csv"
    batch = IngestionBatch(batch_type="SUPPLIER_CATALOG", filename=filename, source="UPLOAD", status="PROCESSING")
    db.add(batch)
    db.flush()
    try:
        path, _, _ = _save_upload(file, subdir=f"batch-{batch.id}")
        records = SupplierCatalogImporter().parse(path)
        batch.total_records = len(records)
        accepted = 0
        rejected = 0
        candidate_ids: list[int] = []
        for row_no, record in enumerate(records, start=2):
            try:
                normalized = record.normalized
                existing = None
                if normalized.get("supplier_sku"):
                    existing = db.scalar(select(ProductCandidate).where(
                        ProductCandidate.supplier_name == normalized["supplier_name"],
                        ProductCandidate.supplier_sku == normalized["supplier_sku"],
                    ))
                if existing:
                    candidate = existing
                else:
                    candidate = ProductCandidate(candidate_code=f"CAND-{uuid4().hex[:8].upper()}", **candidate_orm_kwargs(normalized))
                    db.add(candidate)
                    db.flush()
                _evaluate_candidate(db, candidate)
                candidate_ids.append(candidate.id)
                accepted += 1
                db.add(ImportedProductRecord(batch_id=batch.id, row_number=row_no, raw_json=json_dumps(record.raw), normalized_json=json_dumps(normalized), candidate_id=candidate.id, status="ACCEPTED"))
            except Exception as exc:
                rejected += 1
                db.add(ImportedProductRecord(batch_id=batch.id, row_number=row_no, raw_json=json_dumps(record.raw), normalized_json=json_dumps(record.normalized), status="REJECTED", error_message=str(exc)))
        batch.accepted_records = accepted
        batch.rejected_records = rejected
        batch.status = "COMPLETED" if rejected == 0 else "COMPLETED_WITH_ERRORS"
        batch.completed_at = datetime.utcnow()
        db.add(AgentTask(agent="Buyer AI", title=f"供应商货盘导入完成：{accepted} 个候选商品", priority="HIGH", recommendation="已自动进入三区评估；优先查看 SCALE / TEST 候选并补充图片/PDF做多模态分析"))
        db.commit()
        return {"batch_id": batch.id, "status": batch.status, "accepted": accepted, "rejected": rejected, "candidate_ids": candidate_ids}
    except Exception as exc:
        batch.status = "FAILED"
        batch.error_message = str(exc)
        batch.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(400, str(exc))


@app.post("/api/imports/market-signals")
def import_market_signals(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    filename = file.filename or "market.csv"
    batch = IngestionBatch(batch_type="MARKET_SIGNAL", filename=filename, source="UPLOAD", status="PROCESSING")
    db.add(batch)
    db.flush()
    try:
        path, _, _ = _save_upload(file, subdir=f"batch-{batch.id}")
        signals = MarketSignalFileImporter().parse(path)
        batch.total_records = len(signals)
        for signal in signals:
            db.add(MarketSignal(**signal))
        batch.accepted_records = len(signals)
        batch.status = "COMPLETED"
        batch.completed_at = datetime.utcnow()
        db.flush()
        # 新市场信号到来后，所有未结束候选商品自动重评。
        candidates = db.scalars(select(ProductCandidate).where(ProductCandidate.status.notin_(["PROMOTED", "REJECTED"]))).all()
        for candidate in candidates:
            _evaluate_candidate(db, candidate)
        db.add(AgentTask(agent="Market AI", title=f"真实市场数据已导入：{len(signals)} 条信号", priority="HIGH", recommendation=f"已触发 {len(candidates)} 个候选商品自动重评"))
        db.commit()
        return {"batch_id": batch.id, "status": batch.status, "signals": len(signals), "candidates_reevaluated": len(candidates)}
    except Exception as exc:
        batch.status = "FAILED"
        batch.error_message = str(exc)
        batch.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(400, str(exc))


@app.post("/api/market-signals/webhook")
def market_signal_webhook(payload: MarketSignalBatch, db: Session = Depends(get_db)) -> dict:
    for signal in payload.signals:
        db.add(MarketSignal(**signal.model_dump()))
    db.flush()
    candidates = db.scalars(select(ProductCandidate).where(ProductCandidate.status.notin_(["PROMOTED", "REJECTED"]))).all()
    for candidate in candidates:
        _evaluate_candidate(db, candidate)
    db.commit()
    return {"accepted": len(payload.signals), "candidates_reevaluated": len(candidates)}


@app.post("/api/market/google-trends/pull")
def pull_google_trends(payload: GoogleTrendsPull, db: Session = Depends(get_db)) -> dict:
    run = MarketConnectorRun(connector="GOOGLE_TRENDS", market=payload.market.upper(), request_json=json.dumps(payload.model_dump(), ensure_ascii=False), status="RUNNING")
    db.add(run)
    db.flush()
    try:
        signals = GoogleTrendsAdapter(market=payload.market).pull(payload.keywords)
        for signal in signals:
            db.add(MarketSignal(**signal))
        run.records_received = len(signals)
        run.status = "COMPLETED"
        run.completed_at = datetime.utcnow()
        db.flush()
        candidates = db.scalars(select(ProductCandidate).where(ProductCandidate.status.notin_(["PROMOTED", "REJECTED"]))).all()
        for candidate in candidates:
            _evaluate_candidate(db, candidate)
        db.commit()
        return {"run_id": run.id, "status": run.status, "signals": signals, "candidates_reevaluated": len(candidates)}
    except Exception as exc:
        run.status = "FAILED"
        run.error_message = str(exc)
        run.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(502, f"Google Trends connector failed: {exc}")


@app.post("/api/market/crawl")
def crawl_public_pages(payload: PublicPageCrawl, db: Session = Depends(get_db)) -> dict:
    run = MarketConnectorRun(
        connector="AISOUL_PAGE_CRAWLER",
        market=payload.market.upper(),
        request_json=json.dumps(payload.model_dump(), ensure_ascii=False),
        status="RUNNING",
    )
    db.add(run)
    db.flush()
    try:
        crawler = PublicPageCrawler(market=payload.market)
        signals = crawler.to_market_rows(crawler.collect(urls=payload.urls, keywords=payload.keywords))
        for signal in signals:
            db.add(MarketSignal(**signal))
        run.records_received = len(signals)
        run.status = "COMPLETED"
        run.completed_at = datetime.utcnow()
        db.flush()
        candidates = db.scalars(select(ProductCandidate).where(ProductCandidate.status.notin_(["PROMOTED", "REJECTED"]))).all()
        for candidate in candidates:
            _evaluate_candidate(db, candidate)
        db.add(AgentTask(
            agent="Market AI",
            title=f"公开页爬虫已写入 {len(signals)} 条弱市场信号",
            priority="MEDIUM",
            recommendation="爬虫信号仅修正需求/竞争，不能绕过三区规则；请在选品中心核对应选商品。",
        ))
        db.commit()
        return {
            "run_id": run.id,
            "status": run.status,
            "signal_grade": "inferred_external",
            "signals": signals,
            "candidates_reevaluated": len(candidates),
        }
    except CrawlError as exc:
        run.status = "FAILED"
        run.error_message = str(exc)
        run.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(400, f"Crawl refused (fail-fast): {exc}")
    except Exception as exc:
        run.status = "FAILED"
        run.error_message = str(exc)
        run.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(502, f"Page crawler failed: {exc}")


@app.post("/api/candidates/{candidate_id}/assets")
def upload_candidate_assets(candidate_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)) -> dict:
    candidate = db.get(ProductCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    uploaded = []
    for file in files:
        path, digest, size = _save_upload(file, subdir=f"candidate-{candidate_id}")
        mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
        row = ProductAsset(candidate_id=candidate_id, filename=file.filename or path.name, stored_path=str(path), mime_type=mime, asset_type=_asset_type(file.filename or path.name, mime), byte_size=size, sha256=digest)
        db.add(row)
        db.flush()
        uploaded.append({"id": row.id, "filename": row.filename, "asset_type": row.asset_type, "byte_size": row.byte_size, "sha256": row.sha256})
    db.commit()
    return {"candidate_id": candidate_id, "uploaded": uploaded}


@app.get("/api/candidates/{candidate_id}/intelligence")
def candidate_intelligence(candidate_id: int, db: Session = Depends(get_db)) -> dict:
    candidate = db.get(ProductCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    assets = db.scalars(select(ProductAsset).where(ProductAsset.candidate_id == candidate_id).order_by(ProductAsset.id)).all()
    analyses = db.scalars(select(MultimodalAnalysis).where(MultimodalAnalysis.candidate_id == candidate_id).order_by(MultimodalAnalysis.id.desc())).all()
    return {
        "candidate": _candidate_dict(candidate),
        "assets": [{"id": a.id, "filename": a.filename, "asset_type": a.asset_type, "mime_type": a.mime_type, "byte_size": a.byte_size} for a in assets],
        "analyses": [{"id": a.id, "provider": a.provider, "model": a.model, "status": a.status, "confidence": a.confidence, "applied_to_candidate": a.applied_to_candidate, "result": json.loads(a.result_json or "{}"), "error_message": a.error_message} for a in analyses],
    }


@app.post("/api/candidates/{candidate_id}/multimodal-analyze")
def multimodal_analyze(candidate_id: int, provider: str = "auto", apply: bool = True, db: Session = Depends(get_db)) -> dict:
    candidate = db.get(ProductCandidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    assets = db.scalars(select(ProductAsset).where(ProductAsset.candidate_id == candidate_id).order_by(ProductAsset.id)).all()
    if not assets:
        raise HTTPException(400, "Upload product images/PDF/text assets first")
    gateway = MultimodalGateway()
    try:
        active = gateway.provider(provider)
        contexts = [AssetContext(path=Path(a.stored_path), filename=a.filename, mime_type=a.mime_type, asset_type=a.asset_type) for a in assets]
        context = {
            "supplier_name": candidate.supplier_name, "supplier_sku": candidate.supplier_sku,
            "market": candidate.market, "supplier_price": candidate.supplier_price,
            "target_retail_price": candidate.target_retail_price, "uniqueness": candidate.uniqueness,
            "content_advantage": candidate.content_advantage, "compliance_risk": candidate.compliance_risk,
            "return_risk": candidate.return_risk,
        }
        result = active.analyze(candidate.product_name, contexts, context)
        applied = False
        if apply:
            scores = result.get("suggested_scores", {}) or {}
            for field in ["uniqueness", "content_advantage", "compliance_risk", "return_risk"]:
                if field in scores:
                    setattr(candidate, field, max(0, min(100, float(scores[field]))))
            _evaluate_candidate(db, candidate)
            applied = True
        row = MultimodalAnalysis(candidate_id=candidate_id, provider=result.get("provider", getattr(active, "name", provider)), model=result.get("model", ""), status="DONE", confidence=float(result.get("confidence", 0) or 0), result_json=json.dumps(result, ensure_ascii=False, default=str), applied_to_candidate=applied)
        db.add(row)
        db.add(AgentTask(agent="Product Intelligence AI", title=f"{candidate.product_name} 多模态商品分析完成", priority="HIGH", recommendation=f"Provider={row.provider}；已{'更新' if applied else '未更新'}三区参数并重新评估"))
        db.commit()
        db.refresh(row)
        return {"analysis_id": row.id, "provider": row.provider, "applied": applied, "result": result, "candidate": _candidate_dict(candidate)}
    except HTTPException:
        raise
    except Exception as exc:
        row = MultimodalAnalysis(candidate_id=candidate_id, provider=provider, status="FAILED", error_message=str(exc))
        db.add(row)
        db.commit()
        raise HTTPException(502, f"Multimodal analysis failed: {exc}")


@app.post("/api/demo/reset")
def reset_demo(db: Session = Depends(get_db)) -> dict:
    seed_demo(db, reset=True)
    return {"status": "reset"}


@app.get("/api/foundation")
async def foundation(db: Session = Depends(get_db)) -> dict:
    saleor = await SaleorAdapter().health()
    mcp = await saleor_mcp.health()
    accounts = db.scalars(select(ChannelAccount).order_by(ChannelAccount.id)).all()
    return {
        "kernel": saleor,
        "saleor_mcp": mcp,
        "channels": [account_dict(x) for x in accounts],
        "content_factory": {"inspired_by": content_factory.source, "status": "ready"},
        "opensource": opensource_catalog(),
        "rule": "JoyOPC composes official OSS. It does not fork Saleor or turn Shopify into the platform kernel.",
    }


@app.get("/api/products/{product_id}/fulfillment-source")
def product_fulfillment_source(product_id: int, strategy: str = "BALANCED", db: Session = Depends(get_db)) -> dict:
    product = db.get(MasterProduct, product_id)
    if not product:
        raise HTTPException(404, "Master product not found")
    return source_fulfillment(db, product, strategy)


@app.post("/api/sku/match")
def sku_match(payload: dict, db: Session = Depends(get_db)) -> dict:
    catalog = [(p.sku, p.name) for p in db.scalars(select(MasterProduct)).all()]
    return match_master_sku(str(payload.get("query") or ""), catalog)


@app.post("/api/integrations/saleor/webhooks")
async def saleor_webhook(request: Request, saleor_event: str | None = Header(default="", alias="Saleor-Event")) -> dict:
    payload = await request.json()
    return {"accepted": True, "event": saleor_event or "", "order_id": payload.get("id")}


@app.post("/api/content/listings")
def generate_listings(payload: dict) -> dict:
    return content_factory.generate(payload, str(payload.get("channel") or "all"))


@app.post("/api/content/listings/master/{product_id}")
def generate_master_listings(product_id: int, channel: str = "all", db: Session = Depends(get_db)) -> dict:
    product = db.get(MasterProduct, product_id)
    if product is None:
        raise HTTPException(404, "master product not found")
    return content_factory.generate(
        {"sku": product.sku, "name": product.name, "features": [product.selection_reason] if product.selection_reason else []},
        channel,
    )


@app.post("/api/content/pack/{product_id}")
def generate_listing_pack(product_id: int, db: Session = Depends(get_db)) -> dict:
    product = db.get(MasterProduct, product_id)
    if product is None:
        raise HTTPException(404, "master product not found")
    return build_listing_pack(db, product)


@app.get("/api/content/media/{sku}/{filename}")
def content_media(sku: str, filename: str) -> FileResponse:
    if "/" in sku or "\\" in sku or "/" in filename or "\\" in filename or ".." in sku or ".." in filename:
        raise HTTPException(400, "invalid media path")
    path = (MEDIA_DIR / sku / filename).resolve()
    media_root = MEDIA_DIR.resolve()
    if media_root not in path.parents and path != media_root:
        raise HTTPException(400, "invalid media path")
    if not path.is_file():
        raise HTTPException(404, "media not found")
    return FileResponse(path)


@app.get("/api/channels")
def channel_accounts(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(ChannelAccount).order_by(ChannelAccount.id)).all()
    return [account_dict(x) for x in rows]


@app.post("/api/channels/shopify/connect")
async def connect_shopify(payload: ShopifyConnectRequest, db: Session = Depends(get_db)) -> dict:
    domain = normalize_shop_domain(payload.shop_url)
    token = payload.access_token.strip()
    if not domain:
        raise HTTPException(400, "shop_url is required")
    if not looks_like_admin_token(token):
        raise HTTPException(400, "access_token must be a Shopify Admin API token (shpat_/shpca_/shpua_)")
    account = shopify_channel_account(db)
    if account is None:
        raise HTTPException(404, "Shopify channel account is missing; create one first")
    previous_token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
    previous_shop = os.environ.get("SHOPIFY_SHOP_URL", "")
    os.environ["SHOPIFY_ACCESS_TOKEN"] = token
    os.environ["SHOPIFY_SHOP_URL"] = domain
    account.store_domain = domain
    if payload.api_version:
        cfg = json.loads(account.config_json or "{}") if account.config_json else {}
        cfg["api_version"] = payload.api_version
        account.config_json = json.dumps(cfg, ensure_ascii=False)
    db.commit()
    probe = ShopifyAdapter(store_domain=domain, env_prefix=account.credential_env_prefix or "SHOPIFY", api_version=payload.api_version)
    check = await probe.check_connection()
    if check.get("status") != "CONNECTED":
        if previous_token:
            os.environ["SHOPIFY_ACCESS_TOKEN"] = previous_token
        else:
            os.environ.pop("SHOPIFY_ACCESS_TOKEN", None)
        if previous_shop:
            os.environ["SHOPIFY_SHOP_URL"] = previous_shop
        else:
            os.environ.pop("SHOPIFY_SHOP_URL", None)
        raise HTTPException(400, check.get("reason") or "Shopify connection failed")
    upsert_dotenv({"SHOPIFY_SHOP_URL": domain, "SHOPIFY_ACCESS_TOKEN": token, "SHOPIFY_API_VERSION": payload.api_version})
    live = await check_account(db, account)
    shop = live.get("shop") or check.get("shop") or {}
    return {"status": live.get("status"), "store_domain": domain, "shop": shop, "channel_account_id": account.id}


@app.post("/api/channels/shopify/publish-first-master")
async def publish_first_shopify_master(db: Session = Depends(get_db)) -> dict:
    account = shopify_channel_account(db)
    product = first_publishable_master_product(db)
    if not account:
        raise HTTPException(404, "Shopify channel account not found")
    if not product:
        raise HTTPException(409, "没有可发布的 Master Product（HOLD/REJECT 已排除）")
    return await publish_master_product(db, account=account, product=product, publish_as_draft=True, channel_payload={})


@app.post("/api/channels/shopify/publish_master/{product_id}")
async def publish_shopify_master(product_id: int, db: Session = Depends(get_db)) -> dict:
    account = shopify_channel_account(db)
    product = db.get(MasterProduct, product_id)
    if not account:
        raise HTTPException(404, "Shopify channel account not found")
    if not product:
        raise HTTPException(404, "Master product not found")
    if product.decision in {"HOLD", "REJECT"}:
        raise HTTPException(409, f"三区决策为 {product.decision}，不允许直接发布")
    _assert_publish_management(db, product)
    return await publish_master_product(db, account=account, product=product, publish_as_draft=True, channel_payload={})


@app.post("/api/channels/shopify/publish_product")
async def publish_shopify_product_payload(payload: dict, db: Session = Depends(get_db)) -> dict:
    account = shopify_channel_account(db)
    if not account:
        raise HTTPException(404, "Shopify channel account not found")
    adapter = ShopifyAdapter(
        store_domain=account.store_domain,
        env_prefix=account.credential_env_prefix or "SHOPIFY",
    )
    body = {
        "sku": payload.get("sku") or "UNKNOWN",
        "name": payload.get("name") or "Untitled",
        "category": payload.get("category") or "AI Toy",
        "selling_price": payload.get("retail_price") or payload.get("price") or 0,
        "publish_as_draft": True,
        "description_html": payload.get("description_html") or "",
    }
    return await adapter.publish_product(body)


@app.post("/api/channels")
def create_channel_account(payload: ChannelAccountCreate, db: Session = Depends(get_db)) -> dict:
    row = ChannelAccount(
        channel=payload.channel,
        market=payload.market,
        account_name=payload.account_name,
        credential_env_prefix=payload.credential_env_prefix,
        store_domain=payload.store_domain,
        seller_id=payload.seller_id,
        marketplace_id=payload.marketplace_id,
        shop_cipher=payload.shop_cipher,
        config_json=json.dumps(payload.config, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return account_dict(row)


@app.post("/api/channels/{account_id}/check")
async def check_channel_account(account_id: int, db: Session = Depends(get_db)) -> dict:
    account = db.get(ChannelAccount, account_id)
    if not account:
        raise HTTPException(404, "Channel account not found")
    return await check_account(db, account)


@app.post("/api/channels/publish")
async def publish_channel_product(payload: ChannelPublishRequest, db: Session = Depends(get_db)) -> dict:
    account = db.get(ChannelAccount, payload.channel_account_id)
    product = db.get(MasterProduct, payload.master_product_id)
    if not account:
        raise HTTPException(404, "Channel account not found")
    if not product:
        raise HTTPException(404, "Master product not found")
    _assert_publish_management(db, product)
    return await publish_master_product(
        db,
        account=account,
        product=product,
        publish_as_draft=payload.publish_as_draft,
        channel_payload=payload.channel_payload,
    )


@app.post("/api/channels/{account_id}/orders/sync")
async def sync_channel_orders(account_id: int, payload: ChannelOrderSyncRequest, db: Session = Depends(get_db)) -> dict:
    account = db.get(ChannelAccount, account_id)
    if not account:
        raise HTTPException(404, "Channel account not found")
    since = datetime.utcnow() - timedelta(hours=payload.since_hours)
    result = await sync_orders(db, account=account, since_iso=since.isoformat(timespec="seconds") + "Z")
    if result.get("status") == "DONE":
        result["fulfillment"] = allocate_unallocated_orders(db, channel_account_id=account.id)
    return result


@app.get("/api/channel-sync-runs")
def channel_sync_runs(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(ChannelSyncRun).order_by(ChannelSyncRun.id.desc()).limit(50)).all()
    return [
        {
            "id": r.id,
            "channel_account_id": r.channel_account_id,
            "operation": r.operation,
            "status": r.status,
            "records_received": r.records_received,
            "records_written": r.records_written,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in rows
    ]


@app.get("/api/orders")
def commerce_orders(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(CommerceOrder).order_by(CommerceOrder.id.desc())).all()
    links = {x.commerce_order_id: x for x in db.scalars(select(ChannelOrderLink)).all()}
    output = []
    for order in rows:
        items = db.scalars(select(CommerceOrderItem).where(CommerceOrderItem.commerce_order_id == order.id)).all()
        link = links.get(order.id)
        output.append({
            "id": order.id,
            "order_no": order.order_no,
            "external_order_id": link.external_order_id if link else "",
            "channel": order.channel,
            "market": order.market,
            "status": link.status if link else "DEMO",
            "currency": link.currency if link else "USD",
            "gross_sales": order.gross_sales,
            "product_cost": order.product_cost,
            "shipping_cost": order.shipping_cost,
            "platform_fee": order.platform_fee,
            "ad_cost": order.ad_cost,
            "refund_cost": order.refund_cost,
            "contribution_profit": order.contribution_profit,
            "items": [
                {
                    "sku": i.sku,
                    "title": i.title,
                    "quantity": i.quantity,
                    "net_sales": i.net_sales,
                    "product_cost": i.product_cost,
                    "platform_fee": i.platform_fee,
                    "shipping_cost": i.shipping_cost,
                    "ad_cost": i.ad_cost,
                    "refund_cost": i.refund_cost,
                    "contribution_profit": i.contribution_profit,
                }
                for i in items
            ],
        })
    return output


@app.post("/api/costs")
def add_cost_entry(payload: CostEntryCreate, db: Session = Depends(get_db)) -> dict:
    row = ChannelCostEntry(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    result = reconcile_profit(db)
    return {"id": row.id, "status": "created", "reconciliation": result}


@app.post("/api/costs/import")
def import_cost_entries(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    suffix = Path(file.filename or "costs.csv").suffix.lower()
    if suffix != ".csv":
        raise HTTPException(400, "V0.4 cost import accepts CSV. Use UTF-8 columns from sample_data/channel_costs.csv")
    raw = file.file.read()
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, "File too large")
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    accepted = 0
    errors = []
    for idx, r in enumerate(reader, start=2):
        try:
            amount = float(r.get("amount") or 0)
            cost_type = str(r.get("cost_type") or "OTHER").upper()
            if cost_type not in {"PLATFORM_FEE", "AD_SPEND", "SHIPPING", "REFUND", "OTHER"}:
                raise ValueError(f"unsupported cost_type {cost_type}")
            channel = str(r.get("channel") or "")
            external_order_id = str(r.get("external_order_id") or "")
            order_no = str(r.get("order_no") or "")
            sku = str(r.get("sku") or "")
            source_ref = str(r.get("source_ref") or file.filename or "")
            duplicate = db.scalar(select(ChannelCostEntry.id).where(
                ChannelCostEntry.channel == channel,
                ChannelCostEntry.cost_type == cost_type,
                ChannelCostEntry.amount == amount,
                ChannelCostEntry.external_order_id == external_order_id,
                ChannelCostEntry.order_no == order_no,
                ChannelCostEntry.sku == sku,
                ChannelCostEntry.source_ref == source_ref,
            ))
            if duplicate is not None:
                continue
            row = ChannelCostEntry(
                channel=channel,
                market=str(r.get("market") or "US"),
                cost_type=cost_type,
                amount=amount,
                currency=str(r.get("currency") or "USD"),
                external_order_id=external_order_id,
                order_no=order_no,
                sku=sku,
                source=str(r.get("source") or "CSV_IMPORT"),
                source_ref=source_ref,
            )
            db.add(row)
            accepted += 1
        except Exception as exc:
            errors.append({"row": idx, "error": str(exc)})
    db.commit()
    reconciliation = reconcile_profit(db)
    return {"status": "DONE", "accepted": accepted, "rejected": len(errors), "errors": errors[:20], "reconciliation": reconciliation}


@app.post("/api/profit/reconcile")
def reconcile_sku_profit(db: Session = Depends(get_db)) -> dict:
    return reconcile_profit(db)


@app.get("/api/profit/sku")
def sku_profitability(db: Session = Depends(get_db)) -> list[dict]:
    return sku_profit(db)


@app.get("/api/commerce-control-center")
def commerce_control_center(db: Session = Depends(get_db)) -> dict:
    accounts = db.scalars(select(ChannelAccount)).all()
    listings = db.scalars(select(ChannelListing)).all()
    orders = db.scalars(select(CommerceOrder)).all()
    profit_rows = sku_profit(db)
    sync_runs = db.scalars(select(ChannelSyncRun).order_by(ChannelSyncRun.id.desc()).limit(10)).all()
    return {
        "accounts": [account_dict(x) for x in accounts],
        "summary": {
            "channel_accounts": len(accounts),
            "connected_accounts": sum(x.status == "CONNECTED" for x in accounts),
            "active_or_submitted_listings": sum(x.status in {"ACTIVE", "SUBMITTED"} for x in listings),
            "orders": len(orders),
            "gmv": round(sum(x.gross_sales for x in orders), 2),
            "contribution_profit": round(sum(x.contribution_profit for x in orders), 2),
            "reconciled_skus": sum(x["profit_quality"] == "RECONCILED" for x in profit_rows),
        },
        "sku_profit": profit_rows,
        "sync_runs": [
            {
                "id": x.id,
                "account_id": x.channel_account_id,
                "operation": x.operation,
                "status": x.status,
                "received": x.records_received,
                "written": x.records_written,
                "error": x.error_message,
            }
            for x in sync_runs
        ],
    }


if WEB_DIR.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.get("/")
def web_root():
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "JoyOPC web UI not found")
    return FileResponse(index)
