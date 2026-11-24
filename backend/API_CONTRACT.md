# HTTP contract (v1)

All endpoints are under `/api`. Errors return `{ "detail": "Description" }` with a 4xx/5xx status. The browser never receives the Keitaro API key or calls the Keitaro Admin API directly.

| Method and path | Request | Response |
| --- | --- | --- |
| `GET /api/meta` | None | `{ "domains": [{ "id": 1, "name": "tracker.example" }], "groups": [{ "id": 2, "name": "FORTESTS" }], "sources": [{ "id": 3, "name": "FORTESTS" }] }` |
| `GET /api/offers?q=sample` | `q` matches a name substring or ID; blank returns first 50 active offers | `[{ "id": 3749, "name": "Sample offer" }]` |
| `GET /api/campaigns?q=campaign` | Name substring or campaign ID | Campaigns with `id`, `name`, `alias`, and an admin editor `url` |
| `POST /api/campaigns` | `{ "name": "campaign1", "geo": "AU", "offer_id": 18001, "domain_id": 1813, "group_id": 10332, "source_id": 836 }` | Status 201 with the same campaign fields |
| `GET /api/campaigns/{campaign_id}/streams` | None | Campaign stream collection; see example below |
| `POST /api/campaigns/{campaign_id}/sync` | None | Same collection; fetches remote state; rejects dirty drafts with 409 |
| `POST /api/streams/{stream_id}/offers` | `{ "offer_id": 3749 }` | Updated stream draft |
| `DELETE /api/streams/{stream_id}/offers/{offer_id}` | None | Updated draft with removed offer at 0%; the last active offer may also be removed |
| `POST /api/streams/{stream_id}/offers/{offer_id}/restore` | None | Updated stream draft |
| `PUT /api/streams/{stream_id}/offers/{offer_id}/pin` | `{ "pinned": true, "share": 25 }` or `{ "pinned": false }` | Updated stream draft; impossible allocations yield 422 |
| `POST /api/streams/{stream_id}/publish` | None | Publishes active offers; disables the stream if empty, re-enables it when offers return if the editor disabled it; external changes yield 409 |
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
      "state": "active",
      "offers": [
        { "id": 3749, "name": "Sample offer", "share": 100, "pinned": false, "removed": false }
      ]
    }
  ]
}
```

An empty default offer stream remains editable after a sync, including when its local archive is lost. A direct-redirect stream is not editable. Shares are integer percentages. Unpinned offers divide the remainder evenly; surplus percentage points are assigned in ascending offer-ID order. A removed offer stays in the local archive at 0%. `dirty` marks changes not yet published to Keitaro. Publishing an empty offer list disables the stream; adding or restoring offers re-enables it only if this editor disabled it. `sync` reconciles externally removed offers to the archive.

The editor lists the API key owner's campaigns and reads upstream pages with `offset` and `limit`. The campaign `url` points to the admin editor at `/admin/#!/campaign.editor/<id>`, including for campaigns without a tracking domain. On create, the backend prefixes the name if needed, creates a disabled campaign, adds a `regular` redirect stream with a country filter and a `default` offer stream, then enables the campaign. Publishing sends the complete active offer list because the stand replaces the list on update.
