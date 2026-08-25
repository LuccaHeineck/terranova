# Terranova — Working Plan

This tracks the actual incremental build order we're following for the flood simulator, as agreed in session. For the underlying academic context (why the CA transition rule works the way it does, what data sources exist, etc.), see `docs/tcc-summary.md`. For high-level stack/repo conventions the user set, see `plan.md` at the repo root.

## Development philosophy

Build slowly, validate every part before moving to the next. Start with the simulation core on small artificial (fake) grids, using arbitrary units — no real geographic data, no web framework, no Docker — until the core physics/math is trustworthy. Only then layer in real DEM data, then the API, then the frontend, then containerization. This deliberately front-loads the highest-risk piece (the CA transition rule) instead of following the TCC's own Quadro 7 timeline literally (which starts with Docker/infra setup) — see the note at the end of `docs/tcc-summary.md`.

## Current status

**Step 1 done.** The core CA engine (`backend/simulation/engine.py`) and the synthetic-grid proof of concept (`backend/examples/poc_grid.py`) are implemented and validated: mass is conserved exactly across 100 steps (400.0000 in, 400.0000 out), depth never goes negative, and the resulting flood shape visually matches the TCC's Figure 11 behavior — water pools in the low-lying basin and a hill deforms the patch into a crescent instead of a circle.

**Step 2 done.** `step()` now takes a Manning roughness matrix `N` and weights outflow by
`sqrt(slope) / n` instead of bare slope (also correcting a step-1 simplification that used bare
slope, not `sqrt(slope)` as the TCC's equation actually specifies). Key design decisions (see
`backend/simulation/engine.py`'s docstrings for the in-code version):
- **Distribution-only scope**, confirmed with the user: since the TCC's `h_i` term is the same in
  all 8 directions leaving a cell, it cancels out of the normalized transport-factor ratio — so `N`
  can only affect *which direction* the already-`outflow_fraction`-capped release prefers, not *how
  much* leaves the cell. A magnitude-throttling extension was considered and deferred: it would need
  a new, physically-ungrounded scaling constant, since there's no real cell size (`dx`) or timestep
  (`dt`) yet to make a genuine discharge-rate cap meaningful (arrives with real DEM data in step 3).
- **`n_i` = the destination neighbor's roughness** (the surface water is entering), not the source
  cell's — the TCC summary doesn't pin this down explicitly, so this is a documented modeling
  assumption, not a literal transcription.
- **Important finding from testing this**: in a closed system given enough steps to fully settle,
  the final equilibrium shape converges to be *identical* regardless of roughness (verified: two runs
  with uniform vs. spatially-varying `N`, everything else equal, produced bit-for-bit identical
  flooded-extent statistics by step 50) — which makes physical sense given the distribution-only
  scope: friction/roughness affects the *path and speed* water takes, not *where a closed system with
  fixed volume eventually settles*, since a resting water surface has no more slope anywhere for `N`
  to act on. The measurable effect is only visible mid-transient, before settling (confirmed via a
  direct array diff at step 10: mean abs depth difference ~0.0075 between uniform and channel-N
  runs, vanishing to exactly zero by step 50) — the dedicated `test_manning_roughness_steers_flow_toward_smoother_neighbor`
  regression test isolates and proves the direction-steering mechanism unambiguously (a 4:1 roughness
  ratio between two equal-slope neighbors produces a 4:1 outflow ratio), independent of this
  equilibrium-convergence nuance.
- `backend/tests/` is now active (`test_engine.py`, 5 tests: mass conservation, non-negative depth,
  `N`/`outflow_fraction` validation, the directional-steering proof above, and a checkerboard-artifact
  regression using the neighbor-roughness metric from the step-1 stability fix). Run with
  `.venv/bin/pytest tests/` from `backend/`.

Next up is **step 3**: real DEM ingestion (`rasterio`, SRTM/TOPODATA, sink filling) — the first step
using real geodata instead of synthetic grids.

To run it: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m examples.poc_grid` (must be run as a module, from the `backend/` directory, so `simulation` resolves as a package). Prints step-by-step conservation checks and saves `backend/poc_grid_result.png` (gitignored, regenerate anytime).

**Note (out of order):** at the user's explicit request, a minimal FastAPI skeleton
(`backend/api/main.py`, a single `GET /health` route) was added ahead of schedule — normally step 5.
This is skeleton only, not real step 5 work: no config loading, no wiring to `simulation/`, no
WebSocket streaming yet. Steps 2–4 (Manning roughness, real DEM ingestion, real land-cover data) are
still the actual next work before `api/` does anything beyond the health check.

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

## Engine design notes (steps 1-2)

`step(Z, H, N, outflow_fraction=0.5)` in `engine.py`: water surface elevation is `Z + H`; each cell releases at most `outflow_fraction` of its current depth per step (this cap is what keeps the explicit scheme stable and guarantees `H` never goes negative — not part of the TCC's documented equation, it's an engineering choice), split among its downhill Moore neighbors weighted by `sqrt(slope) / n` — slope is `elevation drop / distance` (diagonal neighbors count less than orthogonal ones per the TCC's note on geometric distortion), and `n` is the receiving neighbor's Manning roughness from `N` (step 2 — see "Current status" above for the full design rationale). Grid boundaries are treated as infinitely high walls (via padding with `+inf`/`0`), so the domain is a closed system — no water ever leaves the grid, which is what makes the conservation check exact rather than approximate.

**Fixed (post-step-1): checkerboard/speckle artifact.** Releasing the full `outflow_fraction` in one synchronous (Jacobi-style) pass caused neighboring cells to overshoot past each other step to step — the same family of instability as violating a CFL condition in explicit diffusion schemes — producing a visible speckled texture instead of a smooth flood front. Confirmed via a flat-water-everywhere test (the artifact appeared even with zero initial asymmetry) and a fraction sweep (artifact magnitude scaled linearly with `outflow_fraction`), ruling out a seeding or logic bug in favor of a step-size stability issue. Fix: `step` now internally decomposes the requested `outflow_fraction` into several smaller synchronous sub-updates that compound to the same total release (`_MAX_STABLE_SUBSTEP_FRACTION = 0.01` in `engine.py`), keeping the external `step(Z, H, outflow_fraction)` signature and per-call physical meaning unchanged. Verified: same flooded extent as before (~1380 cells), exact mass conservation, non-negative depth, and a visually smooth crescent at every snapshot; a small residual grain (~1.4% relative to local depth) remains and is inherent Moore-neighborhood lattice anisotropy, not further reducible via this parameter.

## The core component: the CA engine

The transition rule is the one piece everything else (API, sockets, map rendering, real DEM ingestion) will eventually wrap. It's a pure function over two 2D NumPy arrays:
- `Z`: terrain elevation (static)
- `H`: water depth (evolves each step)

First version (deliberately simpler than the TCC's full documented model): redistribute each cell's water to its 8 Moore neighbors **proportionally to head difference** (`WSE = Z + H`, flow only to neighbors with lower WSE), with **no Manning roughness weighting yet** — roughness needs a real land-cover matrix, which is a separate later increment. This mirrors what the TCC's own informal PoC (section 4.3.1) did before Manning weighting was introduced in the full model description. Step 2 (done) closed most of this gap — see "Current status" above.

## Roadmap (incremental, each step validated before the next)

1. **Core CA engine + synthetic proof of concept** *(done)* — `engine.py` with the step function; `poc_grid.py` builds a small synthetic terrain (e.g. two Gaussian bumps — one hill, one basin), places a concentrated pool of water in the center, runs N iterations in a closed system (no rain/infiltration). Validate: total volume stays constant (mass conservation), depth never goes negative, water visually spreads toward the basin while the hill acts as a barrier — same qualitative result as the TCC's Figure 11.
2. **Add Manning roughness weighting** *(done — current step)* — introduce a synthetic roughness matrix `N`, extend the transition rule to match the TCC's full documented equation (`Q_i = (1/n_i) h_i^(5/3) sqrt(S_i)`), still on artificial grids.
3. **Real DEM ingestion** — bring in `rasterio`, download/clip a real SRTM/TOPODATA tile for the Lajeado/Estrela area, apply sink filling, and run the validated engine on real terrain (still no roughness-from-data or historical validation yet).
4. **Real land-cover / roughness data** — MapBiomas raster → Manning's n lookup table → real `N` matrix, replacing the synthetic one from step 2.
5. **Wrap in FastAPI** — REST endpoint(s) for simulation parameters, WebSocket channel streaming frames every N iterations. Still no frontend — test with a simple script/client or `curl`/websocket CLI.
6. **React + Vite + Leaflet frontend** — config panel, live map overlay fed by the WebSocket stream, log/metrics panel (loosely following the Figure 12 mockup from the TCC).
7. **Docker Compose** — containerize backend + frontend + static data volume.
8. **Validation against real events** — HWM and SWOT data for the 2023/2024 floods, CSI (spatial) and RMSE (depth) metrics, performance benchmarking (vectorized NumPy vs. loops, exploratory CuPy/GPU).

Update the "Current status" section above as steps complete — this file is meant to be read at the start of future sessions instead of re-deriving the plan from scratch.
