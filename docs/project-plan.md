# Terranova — Working Plan

This tracks the actual incremental build order we're following for the flood simulator, as agreed in session. For the underlying academic context (why the CA transition rule works the way it does, what data sources exist, etc.), see `docs/tcc-summary.md`. For high-level stack/repo conventions the user set, see `plan.md` at the repo root.

## Development philosophy

Build slowly, validate every part before moving to the next. Start with the simulation core on small artificial (fake) grids, using arbitrary units — no real geographic data, no web framework, no Docker — until the core physics/math is trustworthy. Only then layer in real DEM data, then the API, then the frontend, then containerization. This deliberately front-loads the highest-risk piece (the CA transition rule) instead of following the TCC's own Quadro 7 timeline literally (which starts with Docker/infra setup) — see the note at the end of `docs/tcc-summary.md`.

## Current status

**Step 1 done.** The core CA engine (`backend/simulation/engine.py`) and the synthetic-grid proof of concept (`backend/examples/poc_grid.py`) are implemented and validated: mass is conserved exactly across 100 steps (400.0000 in, 400.0000 out), depth never goes negative, and the resulting flood shape visually matches the TCC's Figure 11 behavior — water pools in the low-lying basin and a hill deforms the patch into a crescent instead of a circle. Next up is **step 2**: introduce a synthetic Manning roughness matrix and extend the transition rule to match the TCC's full documented equation.

To run it: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m examples.poc_grid` (must be run as a module, from the `backend/` directory, so `simulation` resolves as a package). Prints step-by-step conservation checks and saves `backend/poc_grid_result.png` (gitignored, regenerate anytime).

## Structure so far

The full target folder structure (including the folders scaffolded ahead of need, each with a README
explaining its purpose and which roadmap step activates it) is documented in `docs/ARCHITECTURE.md` —
read that for the whole picture. What actually has code in it today:

```
backend/
  requirements.txt   # numpy, matplotlib (matplotlib is PoC-only, for the sanity-check plot)
  simulation/
    __init__.py
    engine.py         # core CA step function — pure NumPy, no I/O, no geodata
  examples/
    __init__.py
    poc_grid.py        # small artificial-grid demo: fake terrain, pool of water, run N steps, plot/check
```

Everything else (`ingestion/`, `api/`, `validation/`, `config/`, `scripts/`, `tests/`, top-level `data/`)
exists as an empty, README-documented placeholder — no code yet, added in later steps once each
preceding core is validated.

## Engine design notes (step 1)

`step(Z, H, outflow_fraction=0.5)` in `engine.py`: water surface elevation is `Z + H`; each cell releases at most `outflow_fraction` of its current depth per step (this cap is what keeps the explicit scheme stable and guarantees `H` never goes negative — not part of the TCC's documented equation, it's an engineering choice for this first version), split among its downhill Moore neighbors in proportion to slope (`elevation drop / distance`, so diagonal neighbors count less than orthogonal ones per the TCC's note on geometric distortion). Grid boundaries are treated as infinitely high walls (via padding with `+inf`/`0`), so the domain is a closed system — no water ever leaves the grid, which is what makes the conservation check exact rather than approximate. Manning roughness is not yet part of the weighting — that's step 2.

## The core component: the CA engine

The transition rule is the one piece everything else (API, sockets, map rendering, real DEM ingestion) will eventually wrap. It's a pure function over two 2D NumPy arrays:
- `Z`: terrain elevation (static)
- `H`: water depth (evolves each step)

First version (deliberately simpler than the TCC's full documented model): redistribute each cell's water to its 8 Moore neighbors **proportionally to head difference** (`WSE = Z + H`, flow only to neighbors with lower WSE), with **no Manning roughness weighting yet** — roughness needs a real land-cover matrix, which is a separate later increment. This mirrors what the TCC's own informal PoC (section 4.3.1) did before Manning weighting was introduced in the full model description.

## Roadmap (incremental, each step validated before the next)

1. **Core CA engine + synthetic proof of concept** *(current step)* — `engine.py` with the step function; `poc_grid.py` builds a small synthetic terrain (e.g. two Gaussian bumps — one hill, one basin), places a concentrated pool of water in the center, runs N iterations in a closed system (no rain/infiltration). Validate: total volume stays constant (mass conservation), depth never goes negative, water visually spreads toward the basin while the hill acts as a barrier — same qualitative result as the TCC's Figure 11.
2. **Add Manning roughness weighting** — introduce a synthetic roughness matrix `N`, extend the transition rule to match the TCC's full documented equation (`Q_i = (1/n_i) h_i^(5/3) sqrt(S_i)`), still on artificial grids.
3. **Real DEM ingestion** — bring in `rasterio`, download/clip a real SRTM/TOPODATA tile for the Lajeado/Estrela area, apply sink filling, and run the validated engine on real terrain (still no roughness-from-data or historical validation yet).
4. **Real land-cover / roughness data** — MapBiomas raster → Manning's n lookup table → real `N` matrix, replacing the synthetic one from step 2.
5. **Wrap in FastAPI** — REST endpoint(s) for simulation parameters, WebSocket channel streaming frames every N iterations. Still no frontend — test with a simple script/client or `curl`/websocket CLI.
6. **React + Vite + Leaflet frontend** — config panel, live map overlay fed by the WebSocket stream, log/metrics panel (loosely following the Figure 12 mockup from the TCC).
7. **Docker Compose** — containerize backend + frontend + static data volume.
8. **Validation against real events** — HWM and SWOT data for the 2023/2024 floods, CSI (spatial) and RMSE (depth) metrics, performance benchmarking (vectorized NumPy vs. loops, exploratory CuPy/GPU).

Update the "Current status" section above as steps complete — this file is meant to be read at the start of future sessions instead of re-deriving the plan from scratch.
