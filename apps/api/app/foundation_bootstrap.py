from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


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


def ensure_v05a_bootstrap_schema(engine: Engine) -> dict:
    """Compatibility bridge for local/demo databases.

    Production should use `alembic upgrade head` with JOYOPC_SCHEMA_MODE=migrate.
    Bootstrap mode deliberately adds the tenant discriminator and the critical
    order idempotency index without replacing the full migration system.
    """
    changed: list[str] = []
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        if "opc_companies" not in tables:
            return {"changed": changed, "warning": "opc_companies missing"}

        company_id = conn.execute(text("SELECT id FROM opc_companies ORDER BY id LIMIT 1")).scalar()
        if company_id is None:
            conn.execute(
                text(
                    "INSERT INTO opc_companies (name, base_currency, created_at) "
                    "VALUES ('JoyOPC Default OPC', 'USD', CURRENT_TIMESTAMP)"
                )
            )
            company_id = conn.execute(text("SELECT id FROM opc_companies ORDER BY id LIMIT 1")).scalar_one()

        for table in TENANT_ROOT_TABLES:
            if table not in tables:
                continue
            columns = {col["name"] for col in inspect(conn).get_columns(table)}
            if "company_id" not in columns:
                conn.execute(
                    text(
                        f"ALTER TABLE {table} ADD COLUMN company_id INTEGER "
                        f"NOT NULL DEFAULT {int(company_id)}"
                    )
                )
                changed.append(f"{table}.company_id")
            conn.execute(
                text(f"CREATE INDEX IF NOT EXISTS ix_{table}_company_id ON {table}(company_id)")
            )

        if "channel_order_links" in tables:
            duplicate = conn.execute(
                text(
                    "SELECT channel_account_id, external_order_id, COUNT(*) c "
                    "FROM channel_order_links "
                    "GROUP BY channel_account_id, external_order_id "
                    "HAVING COUNT(*) > 1 LIMIT 1"
                )
            ).first()
            if duplicate is not None:
                raise RuntimeError(
                    "Cannot create order idempotency index: duplicate external order exists "
                    f"for account={duplicate[0]} external_order_id={duplicate[1]}"
                )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_order_account_external "
                    "ON channel_order_links(channel_account_id, external_order_id)"
                )
            )
        changed.extend(_ensure_product_unit_columns(conn, inspector))
    return {"changed": changed, "status": "ok"}


PRODUCT_UNIT_COLUMNS = (
    ("soul_recipe_id", "VARCHAR(80) DEFAULT ''"),
    ("has_persona", "BOOLEAN DEFAULT 0"),
    ("memory_enabled", "BOOLEAN DEFAULT 0"),
    ("skills_json", "TEXT DEFAULT '[]'"),
    ("hw_gen", "INTEGER DEFAULT 1"),
    ("module_tier", "VARCHAR(24) DEFAULT 'Mini'"),
    ("shell", "VARCHAR(80) DEFAULT ''"),
    ("claimed_features_json", "TEXT DEFAULT '[]'"),
    ("certs_held_json", "TEXT DEFAULT '[]'"),
    ("cert_gap_json", "TEXT DEFAULT '[]'"),
    ("needs_hardware_gate", "BOOLEAN DEFAULT 0"),
)


def _ensure_product_unit_columns(conn, inspector) -> list[str]:
    from sqlalchemy import inspect as inspect_mod
    from sqlalchemy import text

    changed: list[str] = []
    tables = set(inspector.get_table_names())
    for table in ("master_products", "product_candidates"):
        if table not in tables:
            continue
        existing = {col["name"] for col in inspect_mod(conn).get_columns(table)}
        for name, ddl in PRODUCT_UNIT_COLUMNS:
            if name in existing:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
            changed.append(f"{table}.{name}")
    return changed
