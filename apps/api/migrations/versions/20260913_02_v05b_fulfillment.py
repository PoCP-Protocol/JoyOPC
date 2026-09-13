"""V0.5B inventory, fulfillment and supplier dropship loop."""
from alembic import op

revision = "20260913_02"
down_revision = "20260913_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    from app.operations_models import (
        FulfillmentItem,
        FulfillmentOrder,
        InventoryBalance,
        InventoryLocation,
        InventoryMovement,
        InventoryReservation,
        Shipment,
        SupplierFulfillmentRequest,
    )
    for table in (
        InventoryLocation.__table__,
        InventoryBalance.__table__,
        InventoryMovement.__table__,
        InventoryReservation.__table__,
        FulfillmentOrder.__table__,
        FulfillmentItem.__table__,
        SupplierFulfillmentRequest.__table__,
        Shipment.__table__,
    ):
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    from app.operations_models import (
        FulfillmentItem,
        FulfillmentOrder,
        InventoryBalance,
        InventoryLocation,
        InventoryMovement,
        InventoryReservation,
        Shipment,
        SupplierFulfillmentRequest,
    )
    for table in (
        Shipment.__table__,
        SupplierFulfillmentRequest.__table__,
        FulfillmentItem.__table__,
        FulfillmentOrder.__table__,
        InventoryReservation.__table__,
        InventoryMovement.__table__,
        InventoryBalance.__table__,
        InventoryLocation.__table__,
    ):
        table.drop(bind=bind, checkfirst=True)
