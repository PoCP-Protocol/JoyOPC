from __future__ import annotations

from datetime import datetime, timedelta
import csv
import os
import hashlib
import io
import json
import mimetypes
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from .adapters.saleor import SaleorAdapter
from .config import MAX_UPLOAD_MB, UPLOAD_DIR, WEB_DIR, upsert_dotenv
from .content_factory import content_factory
from .database import Base, engine, get_db
from .discovery_engine import CandidateIntelligenceEngine
from .ingestion import MarketSignalFileImporter, SupplierCatalogImporter, json_dumps
from .adapters.market.crawler import CrawlError, PublicPageCrawler
from .market_data import GoogleTrendsAdapter
from .multimodal import AssetContext, MultimodalGateway
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
    SelectionInput,
    SelectionPolicy,
    SelectionResult,
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
    sync_orders,
)
from .adapters.channels.shopify import ShopifyAdapter, looks_like_admin_token, normalize_shop_domain

app = FastAPI(title="JoyOPC API", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_policy = SelectionPolicy()


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with next(get_db()) as db:
        seed_demo(db)
        reconcile_profit(db)


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
    return candidate


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "product": "JoyOPC", "version": "0.4.0"}


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
        "ceo_decisions": [
            {
                "id": t.id,
                "agent": t.agent,
                "title": t.title,
                "priority": t.priority,
                "recommendation": t.recommendation,
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
    row = ProductCandidate(candidate_code=code, **payload.model_dump())
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
        db.add(AgentTask(agent="Buyer AI", title=f"{candidate.product_name} 已被 CEO 淘汰", priority="MEDIUM", status="DONE", recommendation=payload.note or "停止后续投放与上架准备"))
    else:
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
            db.add(AgentTask(agent="Merchandiser AI", title=f"{candidate.product_name} 已进入正式商品池", priority="HIGH", recommendation="已生成供应商映射和渠道 DRAFT Listing；下一步生成内容资产与首轮测试计划"))
    db.commit()
    db.refresh(candidate)
    return _candidate_dict(candidate)


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
                    candidate = ProductCandidate(candidate_code=f"CAND-{uuid4().hex[:8].upper()}", **normalized)
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
    accounts = db.scalars(select(ChannelAccount).order_by(ChannelAccount.id)).all()
    return {
        "kernel": saleor,
        "channels": [account_dict(x) for x in accounts],
        "content_factory": {"inspired_by": content_factory.source, "status": "ready"},
        "rule": "JoyOPC composes official OSS. It does not fork Saleor or turn Shopify into the platform kernel.",
    }


@app.post("/api/integrations/saleor/webhooks")
async def saleor_webhook(request: Request, saleor_event: str | None = Header(default="", alias="Saleor-Event")) -> dict:
    payload = await request.json()
    return {"accepted": True, "event": saleor_event or "", "order_id": payload.get("id")}


@app.post("/api/content/listings")
def generate_listings(payload: dict) -> dict:
    return content_factory.generate(payload, str(payload.get("channel") or "all"))


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
    if product.decision in {"HOLD", "REJECT"}:
        raise HTTPException(409, f"三区决策为 {product.decision}，不允许直接发布")
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
    return await sync_orders(db, account=account, since_iso=since.isoformat(timespec="seconds") + "Z")


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
