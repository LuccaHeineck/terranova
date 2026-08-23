# api

Minimal FastAPI skeleton, added ahead of schedule at the user's explicit request (roadmap step 5
normally activates this folder — see `docs/project-plan.md`). Currently only a `/health` route;
real orchestration (config loading, ingestion, running `simulation/`, WebSocket streaming) is still
future work.

## Structure

```
api/
  main.py            # FastAPI() app, includes routers
  routers/
    health.py         # GET /health -> {"status": "ok"}
```

## Run locally

From `backend/`, using the existing venv:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api.main:app --reload
```

Run from `backend/` (not `backend/api/`) so the `api` package resolves, mirroring how
`examples/poc_grid.py` is run as `-m examples.poc_grid` from `backend/`.

This is the orchestration layer — it wires together `config/` (settings), `ingestion/` (loading real
data), `simulation/` (running steps), and `validation/` (computing metrics), and exposes the result over
HTTP/WebSocket. Nothing else in the backend imports `api/`; the frontend only ever talks to it over the
network, never by importing backend code directly.
