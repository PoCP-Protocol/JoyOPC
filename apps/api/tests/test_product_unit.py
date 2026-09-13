import asyncio

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.channel_runtime import publish_master_product
from app.database import Base
from app.models import ChannelAccount, MasterProduct
from app.product_unit import apply_unit_to_orm, companion_passport
from app.seed import seed_demo


def fresh_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    db = Session(engine)
    seed_demo(db)
    return db


def test_live_publish_blocked_without_certs():
    db = fresh_db()
    account = db.scalar(select(ChannelAccount).where(ChannelAccount.channel == "Mock"))
    product = db.scalar(select(MasterProduct).where(MasterProduct.sku == "JOY-AI-001"))
    apply_unit_to_orm(product, companion_passport(soul_recipe_id="js-story-teddy-v1", shell="plush", certs_held=[]))
    db.commit()

    live = asyncio.run(
        publish_master_product(db, account=account, product=product, publish_as_draft=False, channel_payload={})
    )
    assert live["status"] == "REQUIRES_CERT"

    draft = asyncio.run(
        publish_master_product(db, account=account, product=product, publish_as_draft=True, channel_payload={})
    )
    assert draft["status"] == "PUBLISHED"
