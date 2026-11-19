from copy import deepcopy

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.keitaro import get_keitaro
from app.main import add_offer, app, cancel, pin_offer, publish, remove_offer, restore_offer
from app.models import CampaignRecord, StreamDraft
from app.schemas import AddOffer, CampaignCreate, PinOffer
from app.service import create_campaign, sync_campaign


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


class FakeKeitaro:
    def __init__(self):
        self.calls = []
        self.actions = [{"key": "http"}]
        self.remote_campaign = {"id": 7, "name": "test_antipov_campaign1", "alias": "campaign-one"}
        self.remote_offers = [
            {"id": 101, "name": "Alpha", "state": "active"},
            {"id": 102, "name": "Beta", "state": "active"},
            {"id": 103, "name": "Gamma", "state": "active"},
        ]
        self.remote_streams = [
            {"id": 31, "campaign_id": 7, "name": "Google", "type": "forced",
             "schema": "redirect", "offers": []},
            {"id": 32, "campaign_id": 7, "name": "Offers", "type": "default",
             "schema": "landings", "offers": [
                 {"offer_id": 101, "share": 50, "state": "active"},
                 {"offer_id": 102, "share": 50, "state": "active"},
             ]},
        ]

    def campaign(self, campaign_id):
        assert campaign_id == 7
        return self.remote_campaign.copy()

    def campaigns(self):
        return [self.campaign(7)]

    def streams(self, campaign_id):
        assert campaign_id == 7
        return deepcopy(self.remote_streams)

    def offers(self):
        return deepcopy(self.remote_offers)

    def domains(self):
        return [{"id": 1, "name": "tracker.example", "state": "active"}]

    def stream_actions(self):
        return self.actions

    def groups(self):
        return [{"id": 2, "name": "FORTESTS"}]

    def sources(self):
        return [{"id": 3, "name": "FORTESTS"}]

    def offer(self, offer_id):
        for offer in self.remote_offers:
            if offer["id"] == offer_id:
                return offer.copy()
        raise HTTPException(404, "Keitaro resource not found")

    def create_campaign(self, body):
        self.calls.append(("create_campaign", body))
        return {"id": 7, "alias": body["alias"]}

    def create_stream(self, body):
        self.calls.append(("create_stream", body))
        return {"id": 31 + sum(kind == "create_stream" for kind, _ in self.calls)}

    def update_campaign(self, campaign_id, body):
        self.calls.append(("update_campaign", campaign_id, body))

    def update_stream(self, stream_id, body):
        self.calls.append(("update_stream", stream_id, deepcopy(body)))
        assert stream_id == 32
        self.remote_streams[1]["offers"] = deepcopy(body["offers"])


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    keitaro = FakeKeitaro()

    def request_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_session] = request_session
    app.dependency_overrides[get_keitaro] = lambda: keitaro
    try:
        with TestClient(app) as client:
            yield client, keitaro, engine
    finally:
        app.dependency_overrides.pop(get_session)
        app.dependency_overrides.pop(get_keitaro)
        engine.dispose()


def test_creator_configures_two_routes_before_enabling_campaign(session):
    client = FakeKeitaro()
    result = create_campaign(session, client, CampaignCreate(
        name="campaign1", geo="AU", offer_id=101, domain_id=1, group_id=2, source_id=3))

    assert result["name"] == "test_antipov_campaign1"
    assert result["url"].startswith("https://tracker.example/")
    assert [call[0] for call in client.calls] == [
        "create_campaign", "create_stream", "create_stream", "update_campaign",
    ]
    campaign = client.calls[0][1]
    assert (campaign["domain_id"], campaign["group_id"], campaign["traffic_source_id"]) == (1, 2, 3)
    assert campaign["state"] == "disabled"
    google, fallback = client.calls[1][1], client.calls[2][1]
    assert (google["campaign_id"], google["position"]) == (7, 1)
    assert google["type"] == "forced"
    assert google["schema"] == "redirect"
    assert google["action_type"] == "http"
    assert google["action_payload"] == "https://google.com"
    assert google["filters"] == [{"name": "country", "mode": "accept", "payload": ["AU"]}]
    assert (fallback["campaign_id"], fallback["position"]) == (7, 2)
    assert fallback["type"] == "default"
    assert fallback["schema"] == "landings"
    assert not fallback.get("filters")
    assert fallback["offers"] == [{"offer_id": 101, "share": 100, "state": "active"}]
    assert client.calls[3] == ("update_campaign", 7, {"state": "active"})


def test_creator_rejects_missing_http_action_before_mutating_keitaro(session):
    client = FakeKeitaro()
    client.actions = [{"key": "other_action"}]

    with pytest.raises(HTTPException) as error:
        create_campaign(session, client, CampaignCreate(
            name="campaign1", geo="AU", offer_id=101,
            domain_id=1, group_id=2, source_id=3))

    assert error.value.status_code == 422
    assert client.calls == []


def test_sync_preserves_plain_flow_and_archives_offer_removed_in_keitaro(session):
    client = FakeKeitaro()
    first = sync_campaign(session, client, 7, force=True)
    assert first["streams"][0]["offers"] == []
    assert first["streams"][0]["editable"] is False
    assert {offer["id"] for offer in first["streams"][1]["offers"]} == {101, 102}

    client.remote_streams[1]["offers"] = [{"offer_id": 101, "share": 100, "state": "active"}]
    second = sync_campaign(session, client, 7, force=True)
    offers = {item["id"]: item for item in second["streams"][1]["offers"]}
    assert offers[101]["share"] == 100
    assert offers[102]["removed"] is True
    assert offers[102]["share"] == 0


def test_draft_is_local_until_publish_and_cancel_discards_new_offer(session):
    client = FakeKeitaro()
    sync_campaign(session, client, 7, force=True)

    draft = add_offer(32, AddOffer(offer_id=103), session, client)
    assert draft["dirty"] is True
    assert {item["id"]: item["share"] for item in draft["offers"]} == {
        101: 34, 102: 33, 103: 33,
    }
    assert [item["offer_id"] for item in client.remote_streams[1]["offers"]] == [101, 102]

    discarded = cancel(32, session, client)
    assert discarded["dirty"] is False
    assert {item["id"] for item in discarded["offers"]} == {101, 102}

    add_offer(32, AddOffer(offer_id=103), session, client)
    published = publish(32, session, client)
    assert published["dirty"] is False
    assert {item["offer_id"] for item in client.remote_streams[1]["offers"]} == {101, 102, 103}
    assert sum(item["share"] for item in client.remote_streams[1]["offers"]) == 100


def test_removed_offer_is_archived_and_can_be_restored(session):
    client = FakeKeitaro()
    sync_campaign(session, client, 7, force=True)

    removed = remove_offer(32, 102, session, client)
    assert removed["dirty"] is True
    assert next(item for item in removed["offers"] if item["id"] == 102)["share"] == 0
    assert len(client.remote_streams[1]["offers"]) == 2
    published = publish(32, session, client)
    assert len(client.remote_streams[1]["offers"]) == 1
    assert next(item for item in published["offers"] if item["id"] == 102)["removed"] is True

    restored = restore_offer(32, 102, session, client)
    assert restored["dirty"] is True
    assert {item["id"]: item["share"] for item in restored["offers"]} == {101: 50, 102: 50}
    publish(32, session, client)
    assert {item["offer_id"] for item in client.remote_streams[1]["offers"]} == {101, 102}


def test_last_offer_removal_and_pinned_share_after_restore(session):
    client = FakeKeitaro()
    sync_campaign(session, client, 7, force=True)
    pinned = pin_offer(32, 101, PinOffer(pinned=True, share=25), session, client)
    assert {item["id"]: item["share"] for item in pinned["offers"]} == {101: 25, 102: 75}
    with pytest.raises(HTTPException) as conflict:
        sync_campaign(session, client, 7, force=True)
    assert conflict.value.status_code == 409
    add_offer(32, AddOffer(offer_id=103), session, client)
    shares = {item.offer_id: item.share for item in session.get(StreamDraft, 32).offers}
    assert shares == {101: 25, 102: 38, 103: 37}
    remove_offer(32, 102, session, client)
    pin_offer(32, 101, PinOffer(pinned=False), session, client)
    remove_offer(32, 103, session, client)
    empty = remove_offer(32, 101, session, client)
    assert empty["dirty"] is True
    assert all(offer["removed"] and offer["share"] == 0 for offer in empty["offers"])
    published = publish(32, session, client)
    assert published["dirty"] is False
    assert client.remote_streams[1]["offers"] == []
    assert any(call == ("update_stream", 32, {"offers": []}) for call in client.calls)
    assert sync_campaign(session, client, 7, force=True)["streams"][1]["editable"] is True
    restored = restore_offer(32, 101, session, client)
    assert next(offer for offer in restored["offers"] if offer["id"] == 101)["share"] == 100
    publish(32, session, client)
    assert client.remote_streams[1]["offers"] == [
        {"offer_id": 101, "share": 100, "state": "active"},
    ]


def test_publish_rejects_remote_change_without_overwriting_it(session):
    client = FakeKeitaro()
    sync_campaign(session, client, 7, force=True)
    add_offer(32, AddOffer(offer_id=103), session, client)
    client.remote_streams[1]["offers"] = [
        {"offer_id": 101, "share": 100, "state": "active"},
    ]

    with pytest.raises(HTTPException) as conflict:
        publish(32, session, client)

    assert conflict.value.status_code == 409
    assert not any(call[0] == "update_stream" for call in client.calls)


def test_creator_http_preserves_prefix_normalizes_geo_and_checks_offer_id(api):
    client, keitaro, _ = api
    payload = {
        "name": "  test_antipov_new  ", "geo": "au", "offer_id": 103,
        "domain_id": 1, "group_id": 2, "source_id": 3,
    }

    assert client.get("/api/offers", params={"q": "103"}).json() == [
        {"id": 103, "name": "Gamma"},
    ]
    response = client.post("/api/campaigns", json=payload)

    assert response.status_code == 201
    result = response.json()
    assert result["name"] == "test_antipov_new"
    assert result["url"] == f'https://tracker.example/{result["alias"]}'
    assert keitaro.calls[1][1]["filters"][0]["payload"] == ["AU"]
    assert keitaro.calls[2][1]["offers"][0]["offer_id"] == 103


@pytest.mark.parametrize(
    ("invalid_data", "expected_status"),
    [
        ({"name": " "}, 422),
        ({"geo": "A1"}, 422),
        ({"offer_id": 0}, 422),
        ({"offer_id": 999}, 404),
        ({"offer_id": 103}, 422),
        ({"domain_id": 999}, 422),
        ({"group_id": 999}, 422),
        ({"source_id": 999}, 422),
    ],
)
def test_creator_invalid_requests_do_not_write_to_keitaro(api, invalid_data, expected_status):
    client, keitaro, _ = api
    keitaro.remote_offers[2]["state"] = "disabled"
    payload = {
        "name": "new", "geo": "AU", "offer_id": 101,
        "domain_id": 1, "group_id": 2, "source_id": 3,
    }

    assert client.post("/api/campaigns", json=payload | invalid_data).status_code == expected_status
    assert keitaro.calls == []


def test_creator_keeps_incomplete_campaign_disabled_and_out_of_cache(session, monkeypatch):
    keitaro = FakeKeitaro()
    create_stream = keitaro.create_stream

    def reject_fallback(body):
        if body["type"] == "default":
            raise HTTPException(502, "Upstream rejected fallback")
        return create_stream(body)

    monkeypatch.setattr(keitaro, "create_stream", reject_fallback)

    with pytest.raises(HTTPException) as error:
        create_campaign(session, keitaro, CampaignCreate(
            name="partial", geo="AU", offer_id=101, domain_id=1, group_id=2, source_id=3,
        ))

    assert error.value.status_code == 502
    assert [call[0] for call in keitaro.calls] == ["create_campaign", "create_stream"]
    assert keitaro.calls[0][1]["state"] == "disabled"
    assert session.get(CampaignRecord, 7) is None


def test_existing_campaign_uses_current_domain_instead_of_cached_domain(api):
    client, keitaro, engine = api
    keitaro.remote_campaign.update(name="Existing campaign", domain_id=1)
    with Session(engine) as db:
        db.add(CampaignRecord(id=7, name="Old name", domain_id=99, domain_name="old.example"))
        db.commit()

    response = client.get("/api/campaigns", params={"q": "existing"})
    assert response.status_code == 200
    assert response.json() == [{
        "id": 7, "name": "Existing campaign", "alias": "campaign-one",
        "url": "https://tracker.example/campaign-one",
    }]

    del keitaro.remote_campaign["domain_id"]
    assert client.get("/api/campaigns").json()[0]["url"] == "https://old.example/campaign-one"
    with Session(engine) as db:
        db.delete(db.get(CampaignRecord, 7))
        db.commit()
    assert client.get("/api/campaigns").json()[0]["url"] is None


def test_editor_http_updates_existing_campaign_and_rolls_back_invalid_drafts(api):
    client, keitaro, _ = api
    keitaro.remote_campaign["name"] = "Existing campaign"
    streams_url = "/api/campaigns/7/streams"
    offers_url = "/api/streams/32/offers"

    def shares(response):
        assert response.status_code == 200
        return {item["id"]: item["share"] for item in response.json()["offers"]}

    response = client.get(streams_url)
    assert response.status_code == 200
    assert response.json()["streams"][0]["editable"] is False
    assert client.post("/api/streams/31/offers", json={"offer_id": 103}).status_code == 409
    assert client.post(offers_url, json={"offer_id": 101}).status_code == 409
    assert client.put(offers_url + "/101/pin", json={"pinned": True, "share": 100}).status_code == 422
    assert client.get(streams_url).json() == response.json()

    assert shares(client.post(offers_url, json={"offer_id": 103})) == {101: 34, 102: 33, 103: 33}
    assert shares(client.put(offers_url + "/101/pin", json={"pinned": True, "share": 25})) == {
        101: 25, 102: 38, 103: 37,
    }
    assert shares(client.delete(offers_url + "/102")) == {101: 25, 102: 0, 103: 75}
    assert keitaro.calls == []
    assert shares(client.post("/api/streams/32/publish")) == {101: 25, 102: 0, 103: 75}
    assert keitaro.calls == [("update_stream", 32, {"offers": [
        {"offer_id": 101, "share": 25, "state": "active"},
        {"offer_id": 103, "share": 75, "state": "active"},
    ]})]
    assert shares(client.post(offers_url + "/102/restore")) == {101: 25, 102: 38, 103: 37}
    assert shares(client.post("/api/streams/32/cancel")) == {101: 25, 102: 0, 103: 75}
