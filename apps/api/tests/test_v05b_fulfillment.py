import asyncio

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.channel_runtime import sync_orders
from app.database import Base
from app.fulfillment_runtime import (
    acknowledge_supplier_request,
    adjust_inventory,
    allocate_order,
    cancel_fulfillment,
    inventory_snapshot,
    ship_fulfillment,
)
from app.models import ChannelAccount, CommerceOrder, MasterProduct
from app.operations_models import FulfillmentOrder, SupplierFulfillmentRequest
from app.seed import seed_demo


def fresh_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    db = Session(engine)
    seed_demo(db)
    return db


def _mock_order(db: Session):
    account = db.scalar(select(ChannelAccount).where(ChannelAccount.channel == "Mock"))
    asyncio.run(sync_orders(db, account=account, since_iso=None))
    order = db.scalar(select(CommerceOrder).where(CommerceOrder.channel == "Mock"))
    return account, order


def test_dropship_path_closes_order_to_shipment():
    db = fresh_db()
    account, order = _mock_order(db)
    fulfillment = allocate_order(db, order, channel_account_id=account.id)
    assert fulfillment.status == "AWAITING_SUPPLIER"
    assert "SUPPLIER_DROPSHIP" in fulfillment.mode_summary

    request = db.scalar(select(SupplierFulfillmentRequest).where(
        SupplierFulfillmentRequest.fulfillment_order_id == fulfillment.id))
    assert request is not None
    acknowledge_supplier_request(db, request, external_request_id="SUP-1001")
    db.refresh(fulfillment)
    assert fulfillment.status == "READY_TO_SHIP"

    result = asyncio.run(ship_fulfillment(db, fulfillment, carrier="4PX", tracking_number="4PXTEST1001"))
    assert result["status"] == "SHIPPED"
    assert result["channel_result"]["status"] == "SHIPPED"
    db.refresh(fulfillment)
    assert fulfillment.status == "SHIPPED"


def test_own_stock_reserves_then_consumes_once():
    db = fresh_db()
    account, order = _mock_order(db)
    product = db.scalar(select(MasterProduct).where(MasterProduct.sku == "JOY-AI-001"))
    adjust_inventory(db, master_product_id=product.id, quantity_delta=10,
                     idempotency_key="initial-stock", safety_stock=1, reorder_point=3)
    fulfillment = allocate_order(db, order, channel_account_id=account.id)
    assert fulfillment.status == "READY_TO_SHIP"
    assert "OWN_STOCK" in fulfillment.mode_summary
    before = next(x for x in inventory_snapshot(db) if x["sku"] == "JOY-AI-001")
    assert before["on_hand"] == 10
    assert before["reserved"] == 2
    assert before["available_to_promise"] == 7

    result = asyncio.run(ship_fulfillment(db, fulfillment, carrier="UPS", tracking_number="1ZJOY001"))
    assert result["status"] == "SHIPPED"
    after = next(x for x in inventory_snapshot(db) if x["sku"] == "JOY-AI-001")
    assert after["on_hand"] == 8
    assert after["reserved"] == 0
    assert after["available_to_promise"] == 7

    duplicate = asyncio.run(ship_fulfillment(db, fulfillment, carrier="UPS", tracking_number="1ZJOY001"))
    assert duplicate["status"] == "DUPLICATE"
    again = next(x for x in inventory_snapshot(db) if x["sku"] == "JOY-AI-001")
    assert again["on_hand"] == 8 and again["reserved"] == 0


def test_cancel_releases_reserved_inventory():
    db = fresh_db()
    account, order = _mock_order(db)
    product = db.scalar(select(MasterProduct).where(MasterProduct.sku == "JOY-AI-001"))
    adjust_inventory(db, master_product_id=product.id, quantity_delta=5, idempotency_key="stock-cancel")
    fulfillment = allocate_order(db, order, channel_account_id=account.id)
    before = next(x for x in inventory_snapshot(db) if x["sku"] == "JOY-AI-001")
    assert before["reserved"] == 2

    result = cancel_fulfillment(db, fulfillment, reason="customer cancelled")
    assert result["status"] == "CANCELLED"
    after = next(x for x in inventory_snapshot(db) if x["sku"] == "JOY-AI-001")
    assert after["on_hand"] == 5
    assert after["reserved"] == 0


def test_inventory_adjustment_is_idempotent():
    db = fresh_db()
    product = db.scalar(select(MasterProduct).where(MasterProduct.sku == "JOY-AI-001"))
    first = adjust_inventory(db, master_product_id=product.id, quantity_delta=10, idempotency_key="same-receipt")
    second = adjust_inventory(db, master_product_id=product.id, quantity_delta=10, idempotency_key="same-receipt")
    assert first.id == second.id
    snapshot = next(x for x in inventory_snapshot(db) if x["sku"] == "JOY-AI-001")
    assert snapshot["on_hand"] == 10
