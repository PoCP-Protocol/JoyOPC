"""JoyOPC V0.4 baseline for Alembic-managed databases."""
from alembic import op

revision = "20260913_00"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Transitional baseline: create any V0.4 tables missing from a fresh DB.
    # Existing V0.4 databases are left untouched.
    from app.database import Base
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    # Baseline downgrade intentionally does not destroy an existing V0.4 database.
    pass
