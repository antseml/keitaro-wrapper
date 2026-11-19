"""Create campaign cache and editable stream drafts."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "campaign_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain_id", sa.Integer(), nullable=False),
        sa.Column("domain_name", sa.String(255), nullable=False),
    )
    op.create_table(
        "stream_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("editable", sa.Boolean(), nullable=False),
        sa.Column("dirty", sa.Boolean(), nullable=False),
        sa.Column("remote_signature", sa.JSON(), nullable=False),
    )
    op.create_index("ix_stream_drafts_campaign_id", "stream_drafts", ["campaign_id"])
    op.create_table(
        "draft_offers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stream_id", sa.Integer(), sa.ForeignKey("stream_drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("share", sa.Integer(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("removed", sa.Boolean(), nullable=False),
        sa.Column("baseline_share", sa.Integer(), nullable=True),
        sa.Column("baseline_pinned", sa.Boolean(), nullable=False),
        sa.Column("baseline_removed", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("stream_id", "offer_id"),
    )
    op.create_index("ix_draft_offers_stream_id", "draft_offers", ["stream_id"])


def downgrade():
    op.drop_index("ix_draft_offers_stream_id", table_name="draft_offers")
    op.drop_table("draft_offers")
    op.drop_index("ix_stream_drafts_campaign_id", table_name="stream_drafts")
    op.drop_table("stream_drafts")
    op.drop_table("campaign_records")
