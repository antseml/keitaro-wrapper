# HTTP contract (v1)

All endpoints are under `/api`. Errors return `{ "detail": "Description" }` with a 4xx/5xx status. The browser never receives the Keitaro API key or calls the Keitaro Admin API directly.

| Method and path | Request | Response |
| --- | --- | --- |
| `GET /api/meta` | None | `{ "domains": [{ "id": 1, "name": "tracker.example" }], "groups": [{ "id": 2, "name": "FORTESTS" }], "sources": [{ "id": 3, "name": "FORTESTS" }] }` |
| `GET /api/offers?q=sample` | `q` matches a name substring or ID; blank returns first 50 active offers | `[{ "id": 3749, "name": "Sample offer" }]` |
| `GET /api/campaigns?q=campaign` | Name substring or campaign ID | `[{ "id": 123, "name": "test_antipov_campaign1", "alias": "test-antipov-campaign1-a1b2c3d4", "url": "https://tracker.example/test-antipov-campaign1-a1b2c3d4" }]` |
| `POST /api/campaigns` | `{ "name": "campaign1", "geo": "AU", "offer_id": 3749, "domain_id": 1, "group_id": 2, "source_id": 3 }` | Status 201; `{ "id": 123, "name": "test_antipov_campaign1", "alias": "test-antipov-campaign1-a1b2c3d4", "url": "https://tracker.example/test-antipov-campaign1-a1b2c3d4" }` |
| `GET /api/campaigns/{campaign_id}/streams` | None | Campaign stream collection; see example below |
| `POST /api/campaigns/{campaign_id}/sync` | None | Same collection; fetches remote state; rejects dirty drafts with 409 |
| `POST /api/streams/{stream_id}/offers` | `{ "offer_id": 3749 }` | Updated stream draft |
| `DELETE /api/streams/{stream_id}/offers/{offer_id}` | None | Updated draft with removed offer at 0%; rejects last active offer with 409 |
| `POST /api/streams/{stream_id}/offers/{offer_id}/restore` | None | Updated stream draft |
| `PUT /api/streams/{stream_id}/offers/{offer_id}/pin` | `{ "pinned": true, "share": 25 }` or `{ "pinned": false }` | Updated stream draft; impossible allocations yield 422 |
| `POST /api/streams/{stream_id}/publish` | None | Publishes active offers to Keitaro, rereads remote values and returns stream; external changes yield 409 |
| `POST /api/streams/{stream_id}/cancel` | None | Discards unpublished changes and returns stream |

Stream collection example:

```json
{
  "campaign_id": 123,
  "streams": [
    {
      "id": 45,
      "name": "Offers",
      "type": "default",
      "editable": true,
      "dirty": false,
      "offers": [
        { "id": 3749, "name": "Sample offer", "share": 100, "pinned": false, "removed": false }
      ]
    }
  ]
}
```

An offer-free stream still appears with `offers: []` and `editable: false` unless it has locally archived offers that can be restored. Shares are integer percentages. Unpinned offers divide the remainder evenly; surplus percentage points are assigned in ascending offer-ID order. A removed offer stays in the local archive at 0%. `dirty` marks changes not yet published to Keitaro. `sync` reconciles externally removed offers to the archive.

The editor lists and accepts existing Keitaro campaigns. `GET /api/campaigns` uses the current Keitaro campaign domain where available, falls back to a locally stored domain for campaigns created by this application, and can return `url: null` when the domain is unknown. On create, the name is prefixed if needed. Before creating any remote resource, the backend checks `GET /admin_api/v1/streams_actions` for the `http` action key; missing key yields 422 and malformed metadata yields 502.
