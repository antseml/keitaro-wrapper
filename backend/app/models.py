from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class CampaignRecord(Base):
    __tablename__ = "campaign_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    domain_id: Mapped[int] = mapped_column(Integer)
    domain_name: Mapped[str] = mapped_column(String(255))


class StreamDraft(Base):
    __tablename__ = "stream_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(30))
    editable: Mapped[bool] = mapped_column(Boolean, default=False)
    dirty: Mapped[bool] = mapped_column(Boolean, default=False)
    remote_signature: Mapped[list] = mapped_column(JSON, default=list)
    offers: Mapped[list["DraftOffer"]] = relationship(
        back_populates="stream", cascade="all, delete-orphan", order_by="DraftOffer.offer_id"
    )


class DraftOffer(Base):
    __tablename__ = "draft_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("stream_drafts.id", ondelete="CASCADE"), index=True)
    offer_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    share: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    removed: Mapped[bool] = mapped_column(Boolean, default=False)
    baseline_share: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baseline_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    baseline_removed: Mapped[bool] = mapped_column(Boolean, default=False)
    stream: Mapped[StreamDraft] = relationship(back_populates="offers")
