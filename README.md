# Terranova

Flood simulation for the Vale do Taquari (RS, Brazil), based on a macroscopic cellular automaton
(CA). This is a TCC (undergraduate thesis, Engenharia de Software, Univates) project.

A grid of cells, each holding a static terrain elevation (`Z`) and a water depth (`H`), exchanges
volume with its 8 neighbors (the Moore neighborhood) every discrete time step, flowing only downhill
and conserving mass exactly. The goal is to simulate real 2023/2024 flood events in the region using
public topographic and land-cover data, fast enough to be useful for rapid-response scenarios.

Monorepo: `backend/` (Python/NumPy simulation core + FastAPI) and `frontend/` (React + Leaflet,
not built yet), eventually run together with Docker Compose.

## Project status

Built incrementally, one validated step at a time, rather than all at once — see
[`docs/project-plan.md`](docs/project-plan.md) for the full 8-step roadmap and the current status.
As of now: the core CA engine, Manning roughness weighting, and a synthetic-grid proof of concept are
done and validated (exact mass conservation, no negative depth, smooth physically-sensible flood
shape, roughness correctly steering flow toward smoother terrain). A minimal FastAPI skeleton and
Docker setup also exist, added ahead of their normal roadmap step at the user's request — see
`docs/project-plan.md` for details on what's real vs. skeleton.

**Read before working on this repo:** [`CLAUDE.md`](CLAUDE.md) lists the required reading order
(`docs/project-plan.md`, `docs/tcc-summary.md`, `docs/ARCHITECTURE.md`, `plan.md`) and the
incremental development philosophy this project follows.

## Repo layout

```
backend/
  simulation/   # the CA engine — pure NumPy, no I/O (backend/simulation/engine.py)
  examples/     # poc_grid.py — synthetic-grid demo that exercises the engine end-to-end
  api/          # FastAPI app (currently just a health check)
  ingestion/, validation/, config/, scripts/, tests/   # scaffolded, empty until their roadmap step
frontend/       # empty stub, filled starting roadmap step 6
docs/           # project-plan.md, tcc-summary.md, ARCHITECTURE.md
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for what belongs where and why.

## Commands

All backend commands run from the `backend/` directory, using its venv.

**First-time setup:**
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Run the synthetic-grid CA engine demo** (prints mass-conservation checks, saves
`backend/poc_grid_result.png`, gitignored):
```bash
.venv/bin/python -m examples.poc_grid
```

**Run the API locally** (currently just `GET /health`):
```bash
.venv/bin/uvicorn api.main:app --reload
# then: curl http://127.0.0.1:8000/health
```

**Run the backend in Docker** (from the repo root, not `backend/`):
```bash
docker compose up --build
```

**Run the backend test suite:**
```bash
.venv/bin/pytest tests/
```

There's no linter or frontend yet — those are added in later roadmap steps. Don't invent commands for
tooling that doesn't exist yet in the current step.
