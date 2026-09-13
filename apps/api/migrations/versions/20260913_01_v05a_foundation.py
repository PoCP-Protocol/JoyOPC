"""V0.5A tenant discriminator, DB idempotency and event/financial foundation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20260913_01"
down_revision = "20260913_00"
branch_labels = None
depends_on = None

TENANT_ROOT_TABLES = (
    "suppliers",
    "master_products",
    "commerce_orders",
    "agent_tasks",
    "market_signals",
    "product_candidates",
    "ingestion_batches",
    "channel_accounts",
    "channel_cost_entries",
)


def _default_company_id(bind) -> int:
    company_id = bind.execute(text("SELECT id FROM opc_companies ORDER BY id LIMIT 1")).scalar()
    if company_id is None:
        bind.execute(
            text(
                "INSERT INTO opc_companies (name, base_currency, created_at) "
                "VALUES ('JoyOPC Default OPC', 'USD', CURRENT_TIMESTAMP)"
            )
        )
        company_id = bind.execute(text("SELECT id FROM opc_companies ORDER BY id LIMIT 1")).scalar_one()
    return int(company_id)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    company_id = _default_company_id(bind)

    for table in TENANT_ROOT_TABLES:
        if table not in inspector.get_table_names():
            continue
        columns = {c["name"] for c in inspect(bind).get_columns(table)}
        if "company_id" not in columns:
            op.add_column(
                table,
                sa.Column(
                    "company_id",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text(str(company_id)),
                ),
            )
            op.create_index(f"ix_{table}_company_id", table, ["company_id"])

    duplicate = bind.execute(
        text(
            "SELECT channel_account_id, external_order_id, COUNT(*) c "
            "FROM channel_order_links "
            "GROUP BY channel_account_id, external_order_id "
            "HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot add order idempotency constraint: duplicate external order exists "
            f"for account={duplicate[0]} external_order_id={duplicate[1]}"
        )
    op.create_index(
        "uq_channel_order_account_external",
        "channel_order_links",
        ["channel_account_id", "external_order_id"],
        unique=True,
    )

    from app.foundation_models import FinancialAllocation, FinancialTransaction, OutboxEvent, WebhookInbox

    for table in (
        WebhookInbox.__table__,
        OutboxEvent.__table__,
        FinancialTransaction.__table__,
        FinancialAllocation.__table__,
    ):
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    from app.foundation_models import FinancialAllocation, FinancialTransaction, OutboxEvent, WebhookInbox

    for table in (
        FinancialAllocation.__table__,
        FinancialTransaction.__table__,
        OutboxEvent.__table__,
        WebhookInbox.__table__,
    ):
        table.drop(bind=bind, checkfirst=True)

    inspector = inspect(bind)
    if "channel_order_links" in inspector.get_table_names():
        indexes = {x["name"] for x in inspector.get_indexes("channel_order_links")}
        if "uq_channel_order_account_external" in indexes:
            op.drop_index("uq_channel_order_account_external", table_name="channel_order_links")

    for table in reversed(TENANT_ROOT_TABLES):
        if table not in inspect(bind).get_table_names():
            continue
        columns = {c["name"] for c in inspect(bind).get_columns(table)}
        if "company_id" in columns:
            with op.batch_alter_table(table) as batch:
                batch.drop_column("company_id")
