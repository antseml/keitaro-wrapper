# Keitaro campaign wrapper

FastAPI + SQLAlchemy backend and React + TypeScript frontend for creating a two-flow Keitaro campaign and editing offer shares through a local draft. The API key stays on the server.

## What it does

- Creates a `test_antipov_` campaign using an existing domain, campaign group, traffic source and offer. A country-filtered flow redirects to Google; a fallback flow sends the remaining traffic to the selected offer.
- Fetches existing campaign streams. Streams without offers are displayed without attempting to edit their routing rules.
- Adds, removes, restores and pins offers in an editable stream. Changes remain local until **Publish**; **Cancel** discards the draft. Removed offers remain visible in the local archive at 0%.
- On refresh, reconciles offers removed directly in Keitaro. Publishing checks that Keitaro's offer list and shares have not changed since the draft was loaded.
- Distributes the remaining integer percentage points among unpinned active offers in stable offer-ID order, so the total is exactly 100%.

## Requirements

- Python 3.12 or newer, Node.js 20 or newer
- A Keitaro account with an Admin API key and permission to read campaigns, offers, domains, groups and traffic sources and to write campaigns and streams

## Backend and migrations

From `backend/`:

```sh
python -m venv .venv
```

Activate the environment (`.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on macOS/Linux), then:

```sh
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`. Set `KEITARO_BASE_URL` to the tracker origin, `KEITARO_API_KEY` to a key from the Keitaro account's API keys page, and `DATABASE_URL` to the local SQLAlchemy database URL. The `.env` file is ignored by Git. No tracker login or API key is required in the browser.

```sh
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The default SQLite database is created in `backend/`. To roll back the initial migration, run `alembic downgrade base`. API documentation is at `http://127.0.0.1:8000/docs`; the frontend contract is documented in [`backend/API_CONTRACT.md`](backend/API_CONTRACT.md).

## Frontend

From `frontend/` in a second terminal:

```sh
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to FastAPI. Run `npm run build` to check the production bundle. The backend has no user authentication and is intended to run on localhost for this test; do not expose its API publicly without adding an authentication layer.

## Verification

```sh
cd backend
python -m pytest
cd ../frontend
npm run build
```

For a live check, create a campaign through the UI with a test offer and inspect both flows in Keitaro. Add another offer and check that Keitaro still shows the original state before Publish; then publish and compare the active offers and their shares. Repeat for Cancel, Remove, Bring back and a pinned share. The creator initially keeps a partially created campaign disabled if stream creation fails, so it can be inspected safely.

Never commit `.env`, access tokens or credentials. This is a test instance tool; the editor lists existing Keitaro campaigns and publishes changes only when you press **Publish**.
