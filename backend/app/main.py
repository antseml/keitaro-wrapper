from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .config import settings
from .database import get_session
from .keitaro import KeitaroClient, get_keitaro
from .models import CampaignRecord, DraftOffer, StreamDraft
from .schemas import AddOffer, CampaignCreate, PinOffer
from .service import (
    _names, _sync_one, as_stream, create_campaign, ensure_campaign,
    get_draft, rebalance, signature, sync_campaign,
)

app = FastAPI(title="Keitaro campaign wrapper", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=[settings.frontend_origin],
    allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta(client: KeitaroClient = Depends(get_keitaro)):
    def values(items):
        return [{"id": int(item["id"]), "name": item["name"]}
                for item in items if item.get("state", "active") == "active"]

    return {"domains": values(client.domains()), "groups": values(client.groups()),
            "sources": values(client.sources())}


@app.get("/api/offers")
def offers(q: str = Query(default="", max_length=150), client: KeitaroClient = Depends(get_keitaro)):
    term = q.strip().casefold()
    return [{"id": int(item["id"]), "name": item["name"]} for item in client.offers()
            if item.get("state") == "active" and
            (not term or term in item["name"].casefold() or term in str(item["id"]))][:50]


@app.get("/api/campaigns")
def campaigns(q: str = Query(default="", max_length=150),
              session: Session = Depends(get_session), client: KeitaroClient = Depends(get_keitaro)):
    term = q.strip().casefold()
    records = {record.id: record for record in session.query(CampaignRecord).all()}
    domains = {int(domain["id"]): domain["name"] for domain in client.domains()}
    result = []
    for item in client.campaigns():
        campaign_id = int(item["id"])
        name = item.get("name", "")
        if item.get("state") == "deleted":
            continue
        if term and term not in name.casefold() and term not in str(campaign_id):
            continue
        record = records.get(campaign_id)
        domain_id = item.get("domain_id")
        domain_name = domains.get(int(domain_id)) if domain_id is not None else None
        if domain_id is None and record is not None:
            domain_name = record.domain_name
        url = None
        if domain_name:
            base = domain_name if domain_name.startswith(("http://", "https://")) else "https://" + domain_name
            url = base.rstrip("/") + "/" + item.get("alias", "")
        result.append({"id": campaign_id, "name": name,
                       "alias": item.get("alias", ""), "url": url})
    return result


@app.post("/api/campaigns", status_code=201)
def create(data: CampaignCreate, session: Session = Depends(get_session),
           client: KeitaroClient = Depends(get_keitaro)):
    return create_campaign(session, client, data)


@app.get("/api/campaigns/{campaign_id}/streams")
def streams(campaign_id: int, session: Session = Depends(get_session),
            client: KeitaroClient = Depends(get_keitaro)):
    return sync_campaign(session, client, campaign_id)


@app.post("/api/campaigns/{campaign_id}/sync")
def sync(campaign_id: int, session: Session = Depends(get_session),
         client: KeitaroClient = Depends(get_keitaro)):
    return sync_campaign(session, client, campaign_id, force=True)


@app.post("/api/streams/{stream_id}/offers")
def add_offer(stream_id: int, payload: AddOffer, session: Session = Depends(get_session),
              client: KeitaroClient = Depends(get_keitaro)):
    row = get_draft(session, client, stream_id)
    offer = next((item for item in row.offers if item.offer_id == payload.offer_id), None)
    if offer and not offer.removed:
        raise HTTPException(409, "Offer is already active in this stream")
    remote_offer = client.offer(payload.offer_id)
    if remote_offer.get("state") != "active":
        raise HTTPException(422, "Offer is not active in Keitaro")
    if offer is None:
        offer = DraftOffer(offer_id=payload.offer_id, name=remote_offer["name"],
                           baseline_share=None, removed=False)
        row.offers.append(offer)
    else:
        offer.removed = False
        offer.pinned = False
        offer.name = remote_offer["name"]
    rebalance(row)
    session.commit()
    return as_stream(row)


@app.delete("/api/streams/{stream_id}/offers/{offer_id}")
def remove_offer(stream_id: int, offer_id: int, session: Session = Depends(get_session),
                 client: KeitaroClient = Depends(get_keitaro)):
    row = get_draft(session, client, stream_id)
    offer = next((o for o in row.offers if o.offer_id == offer_id and not o.removed), None)
    if offer is None:
        raise HTTPException(404, "Active offer not found in this stream")
    offer.removed = True
    offer.pinned = False
    offer.share = 0
    rebalance(row)
    session.commit()
    return as_stream(row)


@app.post("/api/streams/{stream_id}/offers/{offer_id}/restore")
def restore_offer(stream_id: int, offer_id: int, session: Session = Depends(get_session),
                  client: KeitaroClient = Depends(get_keitaro)):
    row = get_draft(session, client, stream_id)
    offer = next((o for o in row.offers if o.offer_id == offer_id and o.removed), None)
    if offer is None:
        raise HTTPException(404, "Archived offer not found in this stream")
    remote_offer = client.offer(offer_id)
    if remote_offer.get("state") != "active":
        raise HTTPException(422, "Offer is not active in Keitaro")
    offer.removed = False
    offer.pinned = False
    rebalance(row)
    session.commit()
    return as_stream(row)


@app.put("/api/streams/{stream_id}/offers/{offer_id}/pin")
def pin_offer(stream_id: int, offer_id: int, payload: PinOffer,
              session: Session = Depends(get_session), client: KeitaroClient = Depends(get_keitaro)):
    row = get_draft(session, client, stream_id)
    offer = next((o for o in row.offers if o.offer_id == offer_id and not o.removed), None)
    if offer is None:
        raise HTTPException(404, "Active offer not found in this stream")
    if payload.pinned and payload.share is None:
        raise HTTPException(422, "Pinned offer needs a share")
    offer.pinned = payload.pinned
    if payload.pinned:
        offer.share = payload.share
    rebalance(row)
    session.commit()
    return as_stream(row)


@app.post("/api/streams/{stream_id}/cancel")
def cancel(stream_id: int, session: Session = Depends(get_session),
           client: KeitaroClient = Depends(get_keitaro)):
    row = get_draft(session, client, stream_id)
    for offer in list(row.offers):
        if offer.baseline_share is None:
            row.offers.remove(offer)
        else:
            offer.share = offer.baseline_share
            offer.pinned = offer.baseline_pinned
            offer.removed = offer.baseline_removed
    row.dirty = False
    session.commit()
    return as_stream(row)


@app.post("/api/streams/{stream_id}/publish")
def publish(stream_id: int, session: Session = Depends(get_session),
            client: KeitaroClient = Depends(get_keitaro)):
    row = get_draft(session, client, stream_id)
    if not row.dirty:
        return as_stream(row)
    remote = next((s for s in client.streams(row.campaign_id) if int(s["id"]) == stream_id), None)
    if remote is None:
        raise HTTPException(409, "Stream was removed from Keitaro")
    if remote.get("schema") != "landings" or int(remote.get("campaign_id", -1)) != row.campaign_id:
        raise HTTPException(409, "The remote stream scheme changed; fetch streams again")
    if signature(remote) != row.remote_signature:
        raise HTTPException(409, "Stream changed in Keitaro; cancel and fetch streams again")
    active = [o for o in row.offers if not o.removed]
    if active and sum(o.share for o in active) != 100:
        raise HTTPException(422, "Active offer shares must add up to 100%")
    client.update_stream(stream_id, {"offers": [
        {"offer_id": o.offer_id, "share": o.share, "state": "active"} for o in active
    ]})
    updated = next((s for s in client.streams(row.campaign_id) if int(s["id"]) == stream_id), None)
    if updated is None or signature(updated) != sorted(
        [{"offer_id": o.offer_id, "share": o.share} for o in active],
        key=lambda value: value["offer_id"],
    ):
        raise HTTPException(502, "Keitaro did not confirm the published shares; fetch streams before retrying")
    row.dirty = False
    _sync_one(session, updated, _names(client))
    session.commit()
    return as_stream(row)
