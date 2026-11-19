"""Track stream state and streams disabled by the offer editor."""

from alembic import op
import sqlalchemy as sa

revision = "0002_stream_state"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("stream_drafts", sa.Column("state", sa.String(30), nullable=False, server_default="active"))
    op.add_column("stream_drafts", sa.Column("auto_disabled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("stream_drafts", "auto_disabled")
    op.drop_column("stream_drafts", "state")
