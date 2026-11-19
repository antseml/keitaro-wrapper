import pytest
from fastapi import HTTPException

from app.models import DraftOffer, StreamDraft
from app.service import rebalance


def stream(*offers: DraftOffer) -> StreamDraft:
    row = StreamDraft(id=101, campaign_id=10, name="Offers", type="default", editable=True)
    row.offers = list(offers)
    return row


def offer(offer_id: int, *, share: int = 0, pinned: bool = False, removed: bool = False) -> DraftOffer:
    return DraftOffer(offer_id=offer_id, name=f"Offer {offer_id}", share=share,
                      pinned=pinned, removed=removed)


def test_unpinned_shares_are_deterministic_and_total_100():
    row = stream(offer(30), offer(10), offer(20))

    rebalance(row)

    assert {item.offer_id: item.share for item in row.offers} == {10: 34, 20: 33, 30: 33}
    assert row.dirty is True


def test_pinned_share_survives_rebalance_and_removed_offer_stays_at_zero():
    row = stream(offer(30), offer(10, share=25, pinned=True),
                 offer(20), offer(40, share=0, removed=True))

    rebalance(row)

    assert {item.offer_id: item.share for item in row.offers} == {
        10: 25, 20: 38, 30: 37, 40: 0,
    }


def test_empty_route_and_overallocated_pins():
    row = stream(offer(10, removed=True))
    rebalance(row)
    assert row.dirty is True
    assert row.offers[0].share == 0

    with pytest.raises(HTTPException) as overallocated:
        rebalance(stream(offer(10, share=80, pinned=True),
                         offer(20, share=30, pinned=True)))
    assert overallocated.value.status_code == 422
