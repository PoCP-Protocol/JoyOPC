from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.fulfillment_runtime import (
    acknowledge_supplier_request,
    adjust_inventory,
    allocate_order,
    allocate_unallocated_orders,
    cancel_fulfillment,
    fulfillment_list,
    inventory_snapshot,
    operations_overview,
    ship_fulfillment,
)
from app.models import CommerceOrder, MasterProduct
from app.operations_models import FulfillmentOrder, SupplierFulfillmentRequest

router = APIRouter(prefix="/api/ops", tags=["operations-v05b"])


class InventoryAdjustRequest(BaseModel):
    master_product_id: int
    quantity_delta: int
    location_code: str = "OWN-DEFAULT"
    location_type: str = "OWN_STOCK"
    safety_stock: int | None = Field(default=None, ge=0)
    reorder_point: int | None = Field(default=None, ge=0)
    idempotency_key: str = Field(min_length=3, max_length=220)
    note: str = ""


class SupplierAckRequest(BaseModel):
    external_request_id: str = ""
    note: str = ""


class ShipRequest(BaseModel):
    carrier: str
    tracking_number: str
    tracking_url: str = ""


class CancelRequest(BaseModel):
    reason: str = ""


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    return operations_overview(db)


@router.get("/inventory")
def inventory(db: Session = Depends(get_db)) -> list[dict]:
    return inventory_snapshot(db)


@router.post("/inventory/adjust")
def inventory_adjust(payload: InventoryAdjustRequest, db: Session = Depends(get_db)) -> dict:
    if db.get(MasterProduct, payload.master_product_id) is None:
        raise HTTPException(404, "master product not found")
    try:
        row = adjust_inventory(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "status": "DONE",
        "balance_id": row.id,
        "on_hand": row.on_hand,
        "reserved": row.reserved,
        "available_to_promise": max(row.on_hand - row.reserved - row.safety_stock, 0),
    }


@router.post("/orders/{order_id}/allocate")
def allocate(order_id: int, db: Session = Depends(get_db)) -> dict:
    order = db.get(CommerceOrder, order_id)
    if order is None:
        raise HTTPException(404, "order not found")
    row = allocate_order(db, order)
    return {"id": row.id, "status": row.status, "mode_summary": row.mode_summary, "exception_reason": row.exception_reason}


@router.post("/orders/allocate-pending")
def allocate_pending(db: Session = Depends(get_db)) -> dict:
    return allocate_unallocated_orders(db)


@router.get("/fulfillments")
def fulfillments(db: Session = Depends(get_db)) -> list[dict]:
    return fulfillment_list(db)


@router.post("/supplier-requests/{request_id}/ack")
def supplier_ack(request_id: int, payload: SupplierAckRequest, db: Session = Depends(get_db)) -> dict:
    row = db.get(SupplierFulfillmentRequest, request_id)
    if row is None:
        raise HTTPException(404, "supplier fulfillment request not found")
    row = acknowledge_supplier_request(db, row, **payload.model_dump())
    return {"id": row.id, "status": row.status, "external_request_id": row.external_request_id}


@router.post("/fulfillments/{fulfillment_id}/ship")
async def ship(fulfillment_id: int, payload: ShipRequest, db: Session = Depends(get_db)) -> dict:
    row = db.get(FulfillmentOrder, fulfillment_id)
    if row is None:
        raise HTTPException(404, "fulfillment not found")
    try:
        return await ship_fulfillment(db, row, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/fulfillments/{fulfillment_id}/cancel")
def cancel(fulfillment_id: int, payload: CancelRequest, db: Session = Depends(get_db)) -> dict:
    row = db.get(FulfillmentOrder, fulfillment_id)
    if row is None:
        raise HTTPException(404, "fulfillment not found")
    try:
        return cancel_fulfillment(db, row, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
