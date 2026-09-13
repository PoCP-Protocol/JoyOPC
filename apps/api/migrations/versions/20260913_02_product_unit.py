"""ProductUnit passport on master products and candidates."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260913_02"
down_revision = "20260913_01"
branch_labels = None
depends_on = None

COLUMNS = (
    ("soul_recipe_id", sa.String(80), ""),
    ("has_persona", sa.Boolean(), False),
    ("memory_enabled", sa.Boolean(), False),
    ("skills_json", sa.Text(), "[]"),
    ("hw_gen", sa.Integer(), 1),
    ("module_tier", sa.String(24), "Mini"),
    ("shell", sa.String(80), ""),
    ("claimed_features_json", sa.Text(), "[]"),
    ("certs_held_json", sa.Text(), "[]"),
    ("cert_gap_json", sa.Text(), "[]"),
    ("needs_hardware_gate", sa.Boolean(), False),
)


def _server_default(default):
    if isinstance(default, bool):
        return sa.text("1" if default else "0")
    if isinstance(default, int):
        return sa.text(str(default))
    return sa.text("'" + str(default).replace("'", "''") + "'")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    for table in ("master_products", "product_candidates"):
        if table not in tables:
            continue
        existing = {c["name"] for c in inspect(bind).get_columns(table)}
        for name, col_type, default in COLUMNS:
            if name in existing:
                continue
            op.add_column(
                table,
                sa.Column(name, col_type, nullable=False, server_default=_server_default(default)),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    for table in ("master_products", "product_candidates"):
        if table not in tables:
            continue
        existing = {c["name"] for c in inspect(bind).get_columns(table)}
        for name, _, _ in reversed(COLUMNS):
            if name in existing:
                op.drop_column(table, name)
