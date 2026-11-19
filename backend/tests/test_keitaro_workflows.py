from copy import deepcopy

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.main import add_offer, cancel, pin_offer, publish, remove_offer, restore_offer
from app.models import StreamDraft
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
        return {"id": 7, "name": "test_antipov_campaign1"}

    def streams(self, campaign_id):
        assert campaign_id == 7
        return deepcopy(self.remote_streams)

    def offers(self):
        return [{"id": 101, "name": "Alpha"}, {"id": 102, "name": "Beta"},
                {"id": 103, "name": "Gamma"}]

    def domains(self):
        return [{"id": 1, "name": "tracker.example", "state": "active"}]

    def stream_actions(self):
        return self.actions

    def groups(self):
        return [{"id": 2, "name": "FORTESTS"}]

    def sources(self):
        return [{"id": 3, "name": "FORTESTS"}]

    def offer(self, offer_id):
        assert offer_id in (101, 102, 103)
        return {"id": offer_id, "name": {101: "Alpha", 102: "Beta", 103: "Gamma"}[offer_id],
                "state": "active"}

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
    assert google["type"] == "forced"
    assert google["schema"] == "redirect"
    assert google["action_payload"] == "https://google.com"
    assert google["filters"] == [{"name": "country", "mode": "accept", "payload": ["AU"]}]
    assert fallback["type"] == "default"
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


def test_last_offer_guard_and_pinned_share_after_restore(session):
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
    with pytest.raises(HTTPException) as last:
        remove_offer(32, 101, session, client)
    assert last.value.status_code == 409


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
