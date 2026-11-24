"""Forget removed offers after their removal is published."""

from alembic import op
import sqlalchemy as sa

revision = "0003_purged_offers"
down_revision = "0002_stream_state"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("draft_offers", sa.Column("purged", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("draft_offers", "purged")
