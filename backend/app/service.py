import re
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .config import settings
from .keitaro import KeitaroClient
from .models import CampaignRecord, DraftOffer, StreamDraft
from .schemas import CampaignCreate


def _active_remote_offers(stream: dict) -> list[dict]:
    return [o for o in stream.get("offers", []) if o.get("state", "active") == "active"]


def signature(stream: dict) -> list[dict]:
    return sorted(
        [{"offer_id": int(o["offer_id"]), "share": int(o["share"])}
         for o in _active_remote_offers(stream)],
        key=lambda item: item["offer_id"],
    )


def as_stream(row: StreamDraft) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "editable": row.editable,
        "dirty": row.dirty,
        "offers": [
            {"id": offer.offer_id, "name": offer.name,
             "share": 0 if offer.removed else offer.share,
             "pinned": offer.pinned, "removed": offer.removed}
            for offer in row.offers
        ],
    }


def _offer_name(offer_id: int, names: dict[int, str]) -> str:
    return names.get(offer_id, f"Offer #{offer_id}")


def _names(client: KeitaroClient) -> dict[int, str]:
    return {int(o["id"]): o["name"] for o in client.offers()}


def ensure_campaign(client: KeitaroClient, campaign_id: int) -> dict:
    campaign = client.campaign(campaign_id)
    if not campaign.get("name", "").startswith(settings.campaign_prefix):
        raise HTTPException(403, "Only test_antipov_ campaigns can be edited")
    return campaign


def _sync_one(session: Session, remote: dict, names: dict[int, str]):
    stream_id = int(remote["id"])
    row = session.get(StreamDraft, stream_id)
    if row is None:
        row = StreamDraft(id=stream_id, campaign_id=int(remote["campaign_id"]),
                          name=remote["name"], type=remote["type"])
        session.add(row)
        session.flush()
    if row.dirty:
        raise HTTPException(409, f"Stream {stream_id} has unpublished changes")
    row.name = remote["name"]
    row.type = remote["type"]
    row.editable = remote.get("schema") == "landings" and (
        bool(_active_remote_offers(remote)) or bool(row.offers)
    )
    row.remote_signature = signature(remote)
    by_id = {o.offer_id: o for o in row.offers}
    seen = set()
    for item in _active_remote_offers(remote):
        offer_id = int(item["offer_id"])
        seen.add(offer_id)
        offer = by_id.get(offer_id)
        if offer is None:
            offer = DraftOffer(stream_id=stream_id, offer_id=offer_id,
                               name=_offer_name(offer_id, names))
            row.offers.append(offer)
        offer.name = _offer_name(offer_id, names)
        offer.share = int(item["share"])
        offer.removed = False
        offer.baseline_share = offer.share
        offer.baseline_removed = False
        offer.baseline_pinned = offer.pinned
    for offer in row.offers:
        if offer.offer_id not in seen:
            offer.removed = True
            offer.share = 0
            offer.pinned = False
            offer.baseline_removed = True
            offer.baseline_share = 0
            offer.baseline_pinned = False
    session.flush()
    return row


def sync_campaign(session: Session, client: KeitaroClient, campaign_id: int, *, force: bool = False):
    ensure_campaign(client, campaign_id)
    remote_streams = client.streams(campaign_id)
    cached = session.query(StreamDraft).filter_by(campaign_id=campaign_id).all()
    if force and any(s.dirty for s in cached):
        raise HTTPException(409, "Cancel or publish draft changes before fetching streams")
    remote_ids = {int(s["id"]) for s in remote_streams}
    # A disappeared remote stream must not be silently published later.
    if force:
        for row in cached:
            if row.id not in remote_ids:
                session.delete(row)
    names = _names(client)
    for remote in remote_streams:
        row = session.get(StreamDraft, int(remote["id"]))
        if row is None or force:
            _sync_one(session, remote, names)
    session.commit()
    return {"campaign_id": campaign_id, "streams": [as_stream(r) for r in
            session.query(StreamDraft).filter_by(campaign_id=campaign_id)
            .order_by(StreamDraft.id).all()]}


def get_draft(session: Session, client: KeitaroClient, stream_id: int):
    row = session.get(StreamDraft, stream_id)
    if row is None:
        raise HTTPException(404, "Fetch this campaign's streams first")
    ensure_campaign(client, row.campaign_id)
    if not row.editable:
        raise HTTPException(409, "This stream has no editable offer scheme")
    return row


def rebalance(row: StreamDraft):
    active = sorted((o for o in row.offers if not o.removed), key=lambda o: o.offer_id)
    if not active:
        raise HTTPException(409, "A stream must keep at least one active offer")
    pinned = [o for o in active if o.pinned]
    unpinned = [o for o in active if not o.pinned]
    remaining = 100 - sum(o.share for o in pinned)
    if remaining < 0 or (unpinned and remaining < len(unpinned)) or (not unpinned and remaining != 0):
        raise HTTPException(422, "Pinned shares leave no valid allocation for other offers")
    if unpinned:
        base, extra = divmod(remaining, len(unpinned))
        for index, offer in enumerate(unpinned):
            offer.share = base + (index < extra)
    row.dirty = True


def create_campaign(session: Session, client: KeitaroClient, data: CampaignCreate):
    full_name = data.name if data.name.startswith(settings.campaign_prefix) else settings.campaign_prefix + data.name
    actions = client.stream_actions()
    if not isinstance(actions, list) or not all(isinstance(item, dict) and isinstance(item.get("key"), str) for item in actions):
        raise HTTPException(502, "Keitaro returned an unexpected list of stream actions")
    if "http" not in {item["key"] for item in actions}:
        raise HTTPException(422, "HTTP redirect action is unavailable in this Keitaro; check Streams actions in the Admin API")
    domains = {int(x["id"]): x for x in client.domains() if x.get("state", "active") == "active"}
    groups = {int(x["id"]): x for x in client.groups()}
    sources = {int(x["id"]): x for x in client.sources()}
    if data.domain_id not in domains or data.group_id not in groups or data.source_id not in sources:
        raise HTTPException(422, "Select an existing domain, campaign group, and traffic source")
    offer = client.offer(data.offer_id)
    if offer.get("state") != "active":
        raise HTTPException(422, "Select an active offer")
    slug = re.sub(r"[^a-z0-9]+", "-", full_name.lower()).strip("-")[:35] or "test-antipov"
    alias = f"{slug}-{uuid4().hex[:8]}"
    campaign = client.create_campaign({
        "name": full_name, "alias": alias, "type": "position", "state": "disabled",
        "domain_id": data.domain_id, "group_id": data.group_id,
        "traffic_source_id": data.source_id,
    })
    campaign_id = int(campaign["id"])
    try:
        client.create_stream({
            "campaign_id": campaign_id, "name": "Google · " + data.geo.upper(),
            "type": "forced", "position": 1, "schema": "redirect",
            "action_type": "http", "action_payload": "https://google.com",
            "collect_clicks": True,
            "filters": [{"name": "country", "mode": "accept", "payload": [data.geo.upper()]}],
        })
        client.create_stream({
            "campaign_id": campaign_id, "name": "Offers", "type": "default",
            "position": 2, "schema": "landings", "action_type": "http",
            "collect_clicks": True,
            "offers": [{"offer_id": data.offer_id, "share": 100, "state": "active"}],
        })
        client.update_campaign(campaign_id, {"state": "active"})
    except Exception:
        # Campaign remains disabled for inspection/retry; never delete a partially created resource silently.
        raise HTTPException(502, f"Campaign {campaign_id} was left disabled because stream creation failed")
    domain_name = domains[data.domain_id]["name"]
    domain_url = domain_name if domain_name.startswith(("https://", "http://")) else "https://" + domain_name
    url = domain_url.rstrip("/") + "/" + alias
    session.merge(CampaignRecord(id=campaign_id, name=full_name,
                                 domain_id=data.domain_id, domain_name=domain_name))
    session.commit()
    return {"id": campaign_id, "name": full_name, "alias": alias, "url": url}
