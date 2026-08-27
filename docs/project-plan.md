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

**Step 3 done.** Real DEM ingestion for a small (~6km) test box straddling the Taquari river between
Lajeado and Estrela:
- **Acquisition**: SRTMGL1 via the OpenTopography REST API (`backend/scripts/download_dem.py`) rather
  than TOPODATA's manual, non-HTTPS, click-through portal — same underlying SRTM data the TCC names, but
  scriptable and reproducible, and already clipped server-side to the ROI bounding box (no separate
  clipping step needed). Requires a free `OPENTOPOGRAPHY_API_KEY` (see `backend/config/settings.py`),
  read from `backend/.env` (gitignored, never committed).
- **`backend/ingestion/dem.py`** implements: (1) reproject the raw EPSG:4326 GeoTIFF to a projected,
  metric CRS (SIRGAS 2000 / UTM 22S, `EPSG:31982`) with square 30m pixels — required because the engine
  hardcodes square-cell distance assumptions (`MOORE_OFFSETS`/`hypot` in `engine.py`), which only hold in
  a projected CRS, not raw lat/lon degrees; (2) crop the thin nodata slivers reprojection leaves at the
  raster's corners (a rotation artifact between geographic and UTM grid axes — a greedy border trim
  clears them); (3) sink-fill the result with a hand-rolled priority-flood algorithm (Barnes et al. 2014,
  `heapq`-based, stdlib only) rather than a hydrology library — `pysheds`/`richdem` were tried first, but
  `pysheds`'s `numba` JIT step currently fails to compile on this project's Python 3.14 (a numba/CPython
  version-compatibility bug unrelated to the DEM itself), and priority-flood is simple enough to implement
  directly in ~30 lines. On the real 183×192-cell test tile, filling changed ~11% of cells by up to 10m
  (plausible SRTM radar noise, concentrated in the river channel).
- **`backend/examples/poc_real_dem.py`** (mirrors `poc_grid.py`): loads the real processed `Z`, uses a
  synthetic uniform Manning `N` (real roughness-from-data is step 4) and seeds a water pool at the
  terrain's lowest point (the river channel). Verified: exact mass conservation over 100 steps
  (400.0000 in, 400.0000 out), non-negative depth throughout, and the flood visibly spreads along the
  real river channel rather than an arbitrary synthetic basin.
- **`backend/tests/test_ingestion.py`** (5 new tests, all network-free): sink filling removes an
  artificial pit and leaves already-monotonic terrain unchanged, nodata-border cropping removes corner
  slivers (and raises if it would consume the whole raster), and reprojection produces square pixels in
  the target CRS. Full suite: `.venv/bin/pytest tests/` from `backend/` — 10/10 passing (5 from step 2 +
  5 new), confirming no regression to `simulation/`'s dependency-free contract.
- New dependencies: `rasterio`, `requests`, `python-dotenv` (added to `requirements.txt`).

The ROI is intentionally small for this first real-terrain pass — it's just four bounding-box constants
in `config/settings.py`, so widening it later (e.g. once step 8's real flood-extent ground truth narrows
down the area that actually matters) is a one-line change + re-running `download_dem.py`, no other code
changes needed.

**Step 4 done.** Real land-cover/roughness data replaces the uniform synthetic `N` `poc_real_dem.py`
used to rely on:
- **Acquisition**: MapBiomas Collection 10 (1985–2024) publishes the whole-Brazil land-cover
  classification as a single public, unauthenticated, tiled Cloud-Optimized GeoTIFF per year on Google
  Cloud Storage (~800 MB for all of Brazil). `backend/scripts/download_landcover.py` opens it via
  `rasterio`'s `/vsicurl/` HTTP driver and reads only the window covering the ROI bbox (already defined
  in `config/settings.py`) — confirmed in practice this pulls a ~40 KB clip, not the 800 MB file, and
  needs no API key (simpler than step 3's OpenTopography key). Year **2024** was chosen deliberately
  (not just "whatever's newest") to match the May 2024 flood event step 8 will validate against — the
  DEM itself stays SRTM-era (~2000), a known, accepted data-vintage mismatch not addressed at this step.
- **`backend/ingestion/landcover.py`** implements: (1) `align_to_reference_grid` — reprojects the raw
  class-ID raster onto the processed DEM's *exact* transform/CRS/shape (not a freshly computed one like
  `dem.py`'s `reproject_to_target_crs`), using **nearest-neighbor** resampling rather than the DEM's
  bilinear, since class IDs are categorical labels — bilinear would blend e.g. Pasture (15) and Urban
  Area (24) into a meaningless fractional class; (2) `classes_to_roughness` — a static
  `MANNING_N_BY_CLASS` lookup table mapping MapBiomas class IDs to Manning's n, cross-walked to the
  nearest NLCD analog in a citable NRCS-Kansas table (adopted for HEC-RAS 2D dam-breach modeling,
  itself rooted in Chow 1959 *Open-Channel Hydraulics*) — MapBiomas has no roughness table of its own.
  The table is deliberately scoped to classes plausible for the Vale do Taquari region (the 10 actually
  observed in the ROI — Forest Formation, Forest Plantation, Grassland, Pasture, Mosaic of Uses, Urban
  Area, Other non-Vegetated Areas, water, Soybean, Other Temporary Crops — plus a few floodplain-adjacent
  extras) rather than MapBiomas's full ~29-class national legend (mangrove, cerrado/savanna, salt flat,
  restinga, etc. don't occur here); any class ID outside the table raises a `ValueError` rather than
  guessing, so widening the ROI into new terrain means deliberately extending the table, not silently
  defaulting. Two documented simplifications: Forest Plantation is treated identically to natural Forest
  Formation, and Mosaic of Uses is treated as generic Cultivated Crops. (3) `build_roughness_matrix` —
  runs the above and persists the result as a GeoTIFF, mirroring `build_elevation_matrix`.
- **`poc_real_dem.py`** now calls `build_roughness_matrix()` instead of filling `N` with a uniform
  value. Verified: still exact mass conservation over 100 steps (400.0000 in, 400.0000 out on the real
  183×192 grid), non-negative depth throughout, and the flood still visibly follows the real river
  channel with the real roughness field in place.
- **`backend/tests/test_landcover.py`** (4 new tests, all network-free): known classes map to their
  expected n values, an unmapped class ID raises `ValueError`, nearest-neighbor resampling preserves
  discrete class values across a resolution change (regression for the bilinear-vs-nearest decision),
  and `build_roughness_matrix`'s output shape matches a given reference grid. Full suite: 14/14 passing
  (10 from steps 2–3 + 4 new).
- No new dependencies — `rasterio`'s bundled GDAL already handles `/vsicurl/` HTTP range reads.

Next up is **step 5**: wrap the engine in FastAPI (REST endpoint(s) for simulation parameters, a
WebSocket channel streaming frames every N iterations).

To run it: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m examples.poc_grid` (must be run as a module, from the `backend/` directory, so `simulation` resolves as a package). Prints step-by-step conservation checks and saves `backend/poc_grid_result.png` (gitignored, regenerate anytime).

**Note (out of order):** at the user's explicit request, a minimal FastAPI skeleton
(`backend/api/main.py`, a single `GET /health` route) was added ahead of schedule — normally step 5.
This is skeleton only, not real step 5 work: no config loading, no wiring to `simulation/`, no
WebSocket streaming yet. Steps 2–4 (Manning roughness, real DEM ingestion, real land-cover data) are
now done — real step 5 work (wiring `api/` to `simulation/`/`ingestion/`, WebSocket streaming) is next.

**Note (out of order):** also at the user's explicit request, a minimal `backend/Dockerfile` and a
root `docker-compose.yml` (single `backend` service, port 8000) were added ahead of schedule —
normally step 7. There's no frontend service yet since `frontend/` is still an empty stub (step 6).

## Structure so far

The full target folder structure (including the folders scaffolded ahead of need, each with a README
explaining its purpose and which roadmap step activates it) is documented in `docs/ARCHITECTURE.md` —
read that for the whole picture. What actually has code in it today:

```
backend/
  requirements.txt   # numpy, matplotlib, fastapi, uvicorn, pytest, rasterio, requests, python-dotenv
  simulation/
    __init__.py
    engine.py         # core CA step function — pure NumPy, no I/O, no geodata
  examples/
    __init__.py
    poc_grid.py        # small artificial-grid demo: fake terrain, pool of water, run N steps, plot/check
    poc_real_dem.py     # same idea, on the real Lajeado/Estrela elevation matrix (step 3)
  ingestion/
    __init__.py
    dem.py              # raw GeoTIFF -> reproject -> crop -> sink-fill -> Z array (step 3)
    landcover.py         # raw MapBiomas GeoTIFF -> align to Z's grid -> Manning's-n lookup -> N array (step 4)
  config/
    __init__.py
    settings.py         # ROI bbox, DEM/land-cover source/CRS/resolution, data paths, API key loading
  scripts/
    __init__.py
    download_dem.py      # CLI: fetch the raw DEM tile from OpenTopography into data/raw/
    download_landcover.py # CLI: fetch the raw MapBiomas land-cover clip into data/raw/
  tests/
    __init__.py
    test_engine.py
    test_ingestion.py
    test_landcover.py
```

`api/` and `validation/` still exist as empty, README-documented placeholders — no code yet, added in
later steps once each preceding core is validated. `data/raw/` and `data/processed/` now hold real
(gitignored) files once `download_dem.py` and the ingestion pipeline have been run locally.

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
3. **Real DEM ingestion** *(done)* — `rasterio` + a hand-rolled priority-flood sink filler; downloaded/clipped a real SRTMGL1 tile (via OpenTopography) for a small Lajeado/Estrela test box, reprojected to a metric CRS with square pixels, sink-filled it, and ran the validated engine on real terrain (still no roughness-from-data or historical validation yet).
4. **Real land-cover / roughness data** *(done)* — MapBiomas Collection 10 raster → Manning's n lookup table → real `N` matrix, replacing the synthetic uniform one `poc_real_dem.py` previously used.
5. **Wrap in FastAPI** *(current step)* — REST endpoint(s) for simulation parameters, WebSocket channel streaming frames every N iterations. Still no frontend — test with a simple script/client or `curl`/websocket CLI.
6. **React + Vite + Leaflet frontend** — config panel, live map overlay fed by the WebSocket stream, log/metrics panel (loosely following the Figure 12 mockup from the TCC).
7. **Docker Compose** — containerize backend + frontend + static data volume.
8. **Validation against real events** — HWM and SWOT data for the 2023/2024 floods, CSI (spatial) and RMSE (depth) metrics, performance benchmarking (vectorized NumPy vs. loops, exploratory CuPy/GPU).

Update the "Current status" section above as steps complete — this file is meant to be read at the start of future sessions instead of re-deriving the plan from scratch.
