import httpx
from fastapi import HTTPException

from .config import settings

ADMIN_API_PATH = "/admin_api/v1"


class KeitaroClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.keitaro_base_url).rstrip("/").removesuffix(ADMIN_API_PATH)
        self.api_key = api_key if api_key is not None else settings.keitaro_api_key
        if not self.api_key:
            raise HTTPException(503, "Keitaro API key is not configured")
        self.http = httpx.Client(
            base_url=self.base_url,
            headers={"Api-Key": self.api_key, "Accept": "application/json"},
            timeout=20,
        )

    def close(self):
        self.http.close()

    def request(self, method: str, path: str, **kwargs):
        try:
            response = self.http.request(method, f"{ADMIN_API_PATH}/{path.lstrip('/')}", **kwargs)
        except httpx.RequestError as exc:
            raise HTTPException(502, "Keitaro is temporarily unreachable") from exc
        if response.is_error:
            # Avoid propagating HTML or untrusted API details to the browser.
            code = response.status_code
            if code in (401, 403):
                raise HTTPException(502, "Keitaro API authentication failed")
            if code == 404:
                raise HTTPException(404, "Keitaro resource not found")
            raise HTTPException(502, f"Keitaro rejected the request (HTTP {code})")
        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(502, "Keitaro returned invalid JSON") from exc

    def campaigns(self):
        limit = 100
        offset = 0
        while True:
            page = self.request("GET", "campaigns", params={"offset": offset, "limit": limit})
            yield from page
            if len(page) < limit:
                return
            offset += len(page)

    def campaign_editor_url(self, campaign_id: int) -> str:
        return f"{self.base_url}/admin/#!/campaign.editor/{campaign_id}"

    def campaign(self, campaign_id: int):
        return self.request("GET", f"campaigns/{campaign_id}")

    def create_campaign(self, body: dict):
        return self.request("POST", "campaigns", json=body)

    def update_campaign(self, campaign_id: int, body: dict):
        return self.request("PUT", f"campaigns/{campaign_id}", json=body)

    def create_stream(self, body: dict):
        return self.request("POST", "streams", json=body)

    def streams(self, campaign_id: int):
        return self.request("GET", f"campaigns/{campaign_id}/streams")

    def update_stream(self, stream_id: int, body: dict):
        return self.request("PUT", f"streams/{stream_id}", json=body)

    def offers(self):
        return self.request("GET", "offers")

    def offer(self, offer_id: int):
        return self.request("GET", f"offers/{offer_id}")

    def domains(self):
        return self.request("GET", "domains")

    def groups(self):
        return self.request("GET", "groups", params={"type": "campaigns"})

    def sources(self):
        return self.request("GET", "traffic_sources")


def get_keitaro():
    client = KeitaroClient()
    try:
        yield client
    finally:
        client.close()
