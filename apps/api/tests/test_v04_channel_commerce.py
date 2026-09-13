import asyncio

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.channel_runtime import check_account, publish_master_product, reconcile_profit, sku_profit, sync_orders
from app.database import Base
from app.models import ChannelAccount, ChannelCostEntry, ChannelListing, ChannelObjectRef, ChannelOrderLink, CommerceOrder, CommerceOrderItem, MasterProduct
from app.seed import seed_demo


def fresh_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    db = Session(engine)
    seed_demo(db)
    return db


def test_mock_channel_publish_order_return_and_idempotency():
    db = fresh_db()
    account = db.scalar(select(ChannelAccount).where(ChannelAccount.channel == "Mock"))
    product = db.scalar(select(MasterProduct).where(MasterProduct.sku == "JOY-AI-001"))

    connection = asyncio.run(check_account(db, account))
    assert connection["status"] == "CONNECTED"

    result = asyncio.run(
        publish_master_product(
            db,
            account=account,
            product=product,
            publish_as_draft=True,
            channel_payload={},
        )
    )
    assert result["status"] == "PUBLISHED"
    listing = db.scalar(select(ChannelListing).where(ChannelListing.master_product_id == product.id, ChannelListing.channel == "Mock"))
    assert listing is not None
    assert db.scalar(select(ChannelObjectRef).where(ChannelObjectRef.channel_listing_id == listing.id)) is not None

    first = asyncio.run(sync_orders(db, account=account, since_iso=None))
    assert first == {"status": "DONE", "received": 1, "written": 1}
    links_before = db.scalars(select(ChannelOrderLink).where(ChannelOrderLink.channel_account_id == account.id)).all()
    assert len(links_before) == 1

    second = asyncio.run(sync_orders(db, account=account, since_iso=None))
    assert second["written"] == 1
    links_after = db.scalars(select(ChannelOrderLink).where(ChannelOrderLink.channel_account_id == account.id)).all()
    assert len(links_after) == 1  # retry/update must not duplicate the external order
    order = db.get(CommerceOrder, links_after[0].commerce_order_id)
    items = db.scalars(select(CommerceOrderItem).where(CommerceOrderItem.commerce_order_id == order.id)).all()
    assert len(items) == 1
    assert items[0].sku == "JOY-AI-001"
    assert items[0].product_cost == 50.0


def test_cost_ledger_reconciles_to_sku_profit():
    db = fresh_db()
    account = db.scalar(select(ChannelAccount).where(ChannelAccount.channel == "Mock"))
    asyncio.run(sync_orders(db, account=account, since_iso=None))
    link = db.scalar(select(ChannelOrderLink).where(ChannelOrderLink.channel_account_id == account.id))
    order = db.get(CommerceOrder, link.commerce_order_id)

    db.add_all(
        [
            ChannelCostEntry(channel="Mock", cost_type="SHIPPING", amount=10, external_order_id=link.external_order_id, sku="JOY-AI-001", source="TEST"),
            ChannelCostEntry(channel="Mock", cost_type="PLATFORM_FEE", amount=15, external_order_id=link.external_order_id, sku="JOY-AI-001", source="TEST"),
            ChannelCostEntry(channel="Mock", cost_type="AD_SPEND", amount=20, external_order_id=link.external_order_id, sku="JOY-AI-001", source="TEST"),
        ]
    )
    db.commit()
    reconcile_profit(db)

    db.refresh(order)
    assert order.gross_sales == 138.0
    assert order.product_cost == 50.0
    assert order.shipping_cost == 10.0
    assert order.platform_fee == 15.0
    assert order.ad_cost == 20.0
    assert order.contribution_profit == 43.0

    row = next(x for x in sku_profit(db) if x["sku"] == "JOY-AI-001")
    assert row["contribution_profit"] >= 43.0  # includes the seeded demo order for the same SKU
    assert row["profit_quality"] == "RECONCILED"
