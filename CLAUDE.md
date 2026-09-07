# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Terranova is a flood simulation system for the Vale do Taquari (RS, Brazil), based on macroscopic
cellular automata (CA). It's the user's TCC (undergraduate thesis, Engenharia de Software, Univates).
Monorepo (`backend/` + `frontend/`), everything in English (code, comments, commit messages), eventually
containerized with Docker Compose. See `plan.md` (repo root) for the original stack decision.

**Before doing any work in this repo, read these four docs in order:**
1. `docs/project-plan.md` — the source of truth for current build step and full roadmap (steps 1–8).
   Update its "Current status" section whenever a step is completed.
2. `docs/tcc-summary.md` — condensed academic context: the transition rule the engine must implement,
   validation metrics, data sources. Fall back to `TCC1LuccaHeineck.pdf` only if this is insufficient.
3. `docs/ARCHITECTURE.md` — the folder structure (including empty, README-documented placeholder
   folders scaffolded ahead of need), what belongs where, and dependency directions between components.
4. `plan.md` — original high-level stack decision.

(A `terranova-context` skill wraps this same reading list — invoke it at the start of a session instead
of re-reading these files manually if the skill is available.)

## Development philosophy — read this before adding scope

This project is being built **deliberately incrementally, in the order in `docs/project-plan.md`**, not
in the order the TCC's own timeline suggests (which starts with Docker/infra). Each step is validated on
synthetic/small data before the next is started:

1. Core CA engine + synthetic proof of concept (small artificial grids, arbitrary units, no geodata) — **current step is past this, see project-plan.md for the live status**
2. Manning roughness weighting (still synthetic grids)
3. Real DEM ingestion (`rasterio`, SRTM/TOPODATA, sink filling)
4. Real land-cover/roughness data (MapBiomas → Manning's n lookup)
5. FastAPI + WebSocket backend
6. React + Vite + Leaflet frontend
7. Docker Compose
8. Validation against real 2023/2024 flood events (CSI, RMSE)

Do not jump ahead — e.g. don't add rasterio/DEM handling, FastAPI, or frontend code while the project is
still on the synthetic-grid engine steps, unless the user explicitly asks to skip ahead. Always check
`docs/project-plan.md`'s "Current status" section first to know what step is actually active.

## Commands

Backend (from `backend/`, using the existing venv):
```bash
cd backend
python3 -m venv .venv                          # first time only
.venv/bin/pip install -r requirements.txt       # first time only / after requirements.txt changes
.venv/bin/python -m examples.poc_grid           # run the synthetic-grid PoC
```
`poc_grid.py` must be run as a module (`-m examples.poc_grid`) from the `backend/` directory so that
`simulation` resolves as a package (there's no package install/`pyproject.toml` yet). It prints
step-by-step mass-conservation checks to stdout and writes `backend/poc_grid_result.png` (gitignored —
regenerate anytime, don't hand-edit).

There are no tests, linter, frontend, or Docker setup yet — those are added in later roadmap steps.
Don't invent commands for tooling that doesn't exist yet in the current step.

## Architecture

See `docs/ARCHITECTURE.md` for the full folder structure, what belongs in each part, dependency
directions, and a "where should I put this?" guide — read it before adding new files or folders.
Read this alongside it for the engine's specific design rationale.

**The CA engine (`backend/simulation/engine.py`) is the one piece everything else will eventually wrap** —
API layer, WebSocket streaming, map rendering, real DEM ingestion all sit around this pure function. Keep
it dependency-free (no I/O, no geodata, no framework imports) so it stays testable on plain NumPy arrays
in isolation.

Core model, per the TCC's transition rule (`docs/tcc-summary.md` has the full equation):
- Two 2D NumPy arrays per cell: `Z` (static terrain elevation) and `H` (water depth, evolves each step).
- Water Surface Elevation `WSE = Z + H`; flow only moves from higher WSE to lower WSE (gravity), across
  the 8-cell **Moore neighborhood** (not von Neumann).
- Flow is distributed to downhill neighbors proportionally to slope (`elevation drop / distance`) —
  diagonal neighbors are weighted by a longer distance than orthogonal ones, per the TCC's note on
  avoiding geometric distortion.
- Mass conservation is the primary correctness check throughout the project: total volume in a closed
  system (no rain/infiltration) must stay constant to numerical precision across arbitrarily many steps.
  `step()` also accepts an optional `inflow` source term (a per-cell array added to `H` once per step,
  e.g. a boundary inflow standing in for upstream river discharge) that makes the grid an open system —
  in that case the checkable invariant becomes `final volume == initial + cumulative inflow`, still
  exact, not approximate.
- The current engine caps each cell's release at `outflow_fraction` of its depth per step — this is an
  engineering stability choice for the explicit scheme (keeps `H` from going negative), not part of the
  TCC's documented equation. Manning roughness weighting (`Q_i = (1/n_i) * h_i^(5/3) * sqrt(S_i)`) is
  implemented, weighting outflow direction by `sqrt(slope) / n` (roadmap step 2).
- Grid boundaries are treated as walls (padded with `+inf`/`0`); combined with the closed-by-default
  system above, this is why exact mass conservation (or exact conservation-plus-inflow) is testable
  rather than approximate.

Planned full architecture (not yet built beyond the engine + PoC — see roadmap above for when each part
gets added): a Python backend loads preprocessed static rasters from disk (no DB/external calls during
simulation), runs the CA engine vectorized with NumPy (kept CuPy-compatible for future GPU use), exposes
FastAPI REST + WebSocket (broadcasting simulation frames every N iterations), and computes CSI/RMSE
validation metrics server-side. A React + TypeScript + Vite frontend renders a Leaflet map (OSM base
layer) with flood overlays fed live via WebSocket, plus a config panel and log/metrics panel.
