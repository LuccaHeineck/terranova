# api

Has code since roadmap step 5: a FastAPI app wrapping `simulation.engine.step` for the real
Lajeado/Estrela grid — no synthetic-grid option, since `api/` may never import `examples/` (see
`docs/ARCHITECTURE.md`'s dependency rules), and by this step there's already a real, ingested dataset
to serve.

## Structure

```
api/
  main.py            # FastAPI() app, lifespan loads Z/N once, includes routers
  state.py            # holds the loaded Z/N, exposed as overridable FastAPI dependencies
  routers/
    health.py         # GET /health -> {"status": "ok"}
    simulations.py     # POST /simulations, WS /simulations/{run_id}/stream
```

## Run locally

From `backend/`, using the existing venv (real DEM/land-cover data must already be downloaded — see
`docs/project-plan.md`'s steps 3-4):

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api.main:app --reload
```

Create a run, then stream it:

```bash
curl -X POST localhost:8000/simulations -H 'content-type: application/json' \
  -d '{"steps": 20, "frame_interval": 5}'
# -> {"run_id": "...", "grid_shape": [183, 192]}
```

Connect a WebSocket client (e.g. the `websockets` Python package, already installed via
`uvicorn[standard]`) to `ws://localhost:8000/simulations/{run_id}/stream` to receive one JSON frame
(`{"step": t, "depth": [[...]], "volume": ...}`) every `frame_interval` steps, ending in `{"done": true}`.
A run can only be streamed once — there's no persistence layer for this project (see
`docs/project-plan.md`), so reconnecting with the same `run_id` closes immediately.

Frames are plain JSON numeric arrays, not the base64-PNG format `docs/tcc-summary.md`'s planned
architecture describes — simpler to test without a frontend; re-encoding as an image is deferred to
whenever the Leaflet frontend (step 6) actually needs one.

**Known limitation**: `docker-compose.yml`'s `backend` service builds from `./backend` as the Docker
context and has no access to (or volume mount for) the repo-root `data/` directory, so
`docker-compose up` currently fails once the lifespan tries to load real DEM/land-cover data. Not fixed
at this step — Docker Compose itself is step 7's concern; run the API locally via `uvicorn` for now.

Run from `backend/` (not `backend/api/`) so the `api` package resolves, mirroring how
`examples/poc_grid.py` is run as `-m examples.poc_grid` from `backend/`.

This is the orchestration layer — it wires together `config/` (settings), `ingestion/` (loading real
data), `simulation/` (running steps), and `validation/` (computing metrics), and exposes the result over
HTTP/WebSocket. Nothing else in the backend imports `api/`; the frontend only ever talks to it over the
network, never by importing backend code directly.
