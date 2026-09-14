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

**Step 5 done.** The engine is now wrapped in a real FastAPI service, serving the real Lajeado/Estrela
grid built in steps 3–4:
- **`POST /simulations`** validates parameters (`steps`, `frame_interval`, `outflow_fraction` — pydantic
  `Field` constraints give free 422s on bad input) and registers a run in an in-memory dict, returning a
  `run_id` and the real `grid_shape`. **`WS /simulations/{run_id}/stream`** pops that run (so each one
  streams exactly once — no persistence layer, matching the project's "no DB" decision), seeds a pool at
  the terrain's lowest point, and runs `simulation.engine.step` in a loop, sending one JSON frame
  (`{"step", "depth", "volume"}`) every `frame_interval` steps plus a final `{"done": true}`. Mass
  conservation is asserted every step, same as the example scripts.
- **Two design decisions**: frames are plain JSON numeric arrays, not the base64-PNG format
  `docs/tcc-summary.md`'s planned architecture describes — simpler and directly testable without a
  frontend; PNG (or another binary format) can replace this once Leaflet (step 6) actually needs an
  image. And the API serves only the real grid, no synthetic-grid option — `api/` may only depend on
  `config/`/`ingestion/`/`simulation/`/`validation/` (never `examples/`, which nothing else imports per
  `docs/ARCHITECTURE.md`), and there's already real ingested data worth serving by this step.
- **`backend/api/state.py`** holds the loaded `Z`/`N` (built once at startup via a FastAPI `lifespan`,
  not per-request — the ingestion functions do real raster I/O), exposed as FastAPI dependencies rather
  than read directly off `app.state` so tests can swap in tiny synthetic arrays via
  `app.dependency_overrides` instead of needing the real downloaded files.
- **Shared seeding helper**: `seed_pool_at_lowest_point` moved from `examples/poc_real_dem.py` into
  `simulation/engine.py` so both it and the new API route share one implementation — the refactor
  `docs/ARCHITECTURE.md` already flagged as reasonable "once a second caller exists."
- **`backend/tests/test_api.py`** (7 new tests): REST validation (valid/invalid params), WebSocket
  streaming (frame shape/interval, final `done`, mass conservation mid-stream), unknown-`run_id`
  rejection, and single-use run consumption. Uses `TestClient` *without* the `with` context manager, so
  the app's real data-loading lifespan never runs — combined with `dependency_overrides`, this keeps the
  suite network- and file-free like every other step. Needed a new dependency, `httpx2` (the package
  this environment's `starlette.testclient` requires). Full suite: 22/22 passing.
- **Known limitation, not fixed now**: `docker-compose.yml`'s `backend` service builds from `./backend`
  as its Docker context and has no access to (or volume mount for) the repo-root `data/` directory, so
  `docker-compose up` currently fails once the lifespan tries to load real data. Docker Compose itself is
  step 7's concern (it was added ahead of schedule) — verified locally via `uvicorn` instead (REST +
  WebSocket both confirmed end-to-end against the real grid: `grid_shape: [183, 192]`, frames arriving at
  the requested interval, volume conserved to floating-point precision, ending in `done`).

**Step 6 done.** The React + Vite + Leaflet frontend now drives the real backend end-to-end:
- **Two small backend additions the frontend needed**: `CORSMiddleware` in `backend/api/main.py`
  (explicit `localhost:5173`/`127.0.0.1:5173` dev origins, not a wildcard), and a new
  `bounds: {west, south, east, north}` field on `POST /simulations`'s response. `bounds` is *not*
  derived from the raw `ROI_*` constants in `config/settings.py` — those describe the pre-crop
  download box — but from a new `ingestion/dem.py::get_geographic_bounds()`, which reads the
  *processed* GeoTIFF's own transform via `rasterio.warp.transform_bounds`, since
  `crop_nodata_border` trims the served grid slightly smaller than the raw ROI. Wired through
  `api/state.py::BOUNDS`/`get_bounds()` alongside the existing `Z`/`N` pattern. `test_api.py`
  updated to override/assert it; 22/22 tests still pass.
- **`frontend/`** (npm, Tailwind CSS v4, no test framework — deferred per user decision): a
  three-column layout (`ConfigPanel` | `FloodMap` | `LogPanel`). `useSimulationRun` is the
  orchestration hook (`idle -> starting -> streaming -> done | error`) wrapping `POST /simulations`
  then the WebSocket stream. `FloodMap` uses plain Leaflet (not `react-leaflet`) with OSM tiles and
  a single `L.ImageOverlay` updated via `setUrl()` each frame, positioned with the real `bounds`
  from the API (`map.fitBounds()` on run start). Each `{step, depth, volume}` frame is rasterized
  client-side (`rendering/depthToImage.ts`) — no backend PNG encoding added, matching step 5's
  documented "add PNG only when the frontend actually needs it" decision. `LogPanel` shows
  status/grid_shape/bounds and a scrolling `step N: volume=...` log; the WebSocket wrapper
  (`api/stream.ts`) explicitly handles the unknown/consumed-`run_id` case (server closes with
  `code=4004` *before* `accept()`, so it only ever surfaces via `onclose`, never a JSON message) and
  any mid-stream disconnect, both shown as a visible error banner rather than a frozen UI.
- **Verified live in a browser** (Playwright driving real Chromium against the real running
  backend + `npm run dev`, not just `tsc`): a 100-step run against the real 183×192 Lajeado/Estrela
  grid streamed 20 frames, volume held at exactly `400.0000` throughout, and the rendered flood
  overlay traced the real river channel's meander shape (confirmed by extracting the raw overlay
  PNG and comparing its shape directly against the OSM basemap's river geometry) — including
  catching and fixing a real UX bug this way: the initial blue-tinted color ramp was visually
  invisible against OSM's own blue river tiles, so the ramp was changed to high-contrast
  orange-red. Also verified the error path by force-killing the backend mid-stream: the UI
  correctly transitions to a visible "Stream closed unexpectedly (code 1006)" error state instead
  of hanging.
- **Deferred, not done in this step**: Docker Compose wiring for `frontend/` and the `data/`-volume-
  mount gap for `backend` (both done in step 7 — see "Step 7 done" below); Vitest/RTL frontend
  tests; CSI/RMSE validation UI (step 8); CORS-origin configurability beyond the hardcoded localhost
  list (also done in step 7).

**Step 7 done.** `docker compose up --build` now brings up both services end-to-end:
- **`frontend/Dockerfile`** (new): multi-stage build — `node:22-alpine` runs `npm ci` + `npm run
  build`, then the built `dist/` is copied into an `nginx:alpine` stage that serves it as static
  files on port 80 (published as host port 5173, matching the old dev-server port). No SPA-fallback
  nginx config was needed — `App.tsx` has a single fixed layout, no client-side routing.
  `VITE_API_BASE_URL` is passed as a build `ARG` (Vite inlines `import.meta.env.VITE_*` at `vite
  build` time, so it can't be a runtime container env var); its default already matches the
  backend's host-published port, so the common case needs no override.
- **Fixed the `data/`-mount gap** (the known limitation from step 5/6): `backend/config/settings.py`
  now derives `RAW_DIR`/`PROCESSED_DIR` from a `TERRANOVA_DATA_DIR` env var (defaulting to the old
  bare-metal `REPO_ROOT/data` path when unset), and `docker-compose.yml` bind-mounts
  `./data:/app/data` read-write with `TERRANOVA_DATA_DIR=/app/data` set on the `backend` service.
  Read-write, not read-only, because the FastAPI `lifespan` unconditionally re-derives and
  overwrites `data/processed/*.tif` on every startup — verified this actually happens inside the
  container (host-side mtimes on `data/processed/*.tif` update on each `docker compose up`).
  **Side effect worth knowing**: since the backend container runs as root (no `USER` directive) and
  the mount is a host bind mount, the container's writes leave `data/processed/*.tif` root-owned on
  the host afterwards. This self-heals the next time the backend runs bare-metal as `lucca` (it
  overwrites the same files unconditionally), so it hasn't been treated as a bug worth adding a
  non-root `USER`/UID-mapping for at this step — noted here in case a "permission denied" surprises
  a future bare-metal run right after a Docker one.
- **CORS origins are now configurable**: `CORS_ALLOWED_ORIGINS` env var (comma-separated), read in
  `backend/config/settings.py` and used by `backend/api/main.py`; defaults to the same
  `localhost:5173`/`127.0.0.1:5173` list as before, so bare-metal `uvicorn` behavior is unchanged.
  `docker-compose.yml` sets it explicitly on the `backend` service for documentation purposes (the
  value doesn't actually need to differ, since the frontend container is published on the same
  `5173` host port the dev server used).
- **`backend/.dockerignore`** now excludes `.env`, so the gitignored `OPENTOPOGRAPHY_API_KEY` secret
  doesn't get baked into the image (it's only needed by the offline `scripts/download_*.py`, never
  by the running FastAPI app).
- **`backend/Dockerfile`** also needed one more fix, found while first bringing the containers up:
  `python:3.12-slim` doesn't ship `libexpat.so.1`, which rasterio's manylinux wheel dynamically
  links against — `apt-get install -y libexpat1` was added as a build step.
- **Verified end-to-end**: `docker compose up --build` starts both containers; the backend's
  lifespan loads the real Lajeado/Estrela DEM/land-cover from the mounted volume with no
  `FileNotFoundError`; `curl http://localhost:8000/health` succeeds; the frontend serves at
  `http://localhost:5173` with `VITE_API_BASE_URL` correctly baked into the bundle as
  `http://localhost:8000`; a CORS preflight (`OPTIONS /simulations` with `Origin:
  http://localhost:5173`) returns `access-control-allow-origin: http://localhost:5173`; a real
  simulation run was created via `POST /simulations` and its `WS /simulations/{run_id}/stream`
  delivered a real frame (`step`/`depth`/`volume` keys) over the container's published port; and
  `docker compose down` followed by `docker compose up` (no `--build`) came back up cleanly against
  the already-processed `data/processed/*.tif`, confirming the startup re-derivation is idempotent,
  not just first-run-lucky.

**Boundary inflow added (ahead of step 8, deliberately out of numbered order).** Investigating how
step 8 validation would actually work surfaced a real gap: the engine was a strictly closed system
(one seeded pool at t=0), but a real event like May 2024 is driven by the river rising continuously
over ~72 hours — no closed-system run can represent that. `step()` (`backend/simulation/engine.py`)
now takes an optional `inflow` parameter: a per-cell external source array added to `H` once after
each step's redistribution pass (not split across substeps — a documented simplification, the same
kind of engineering choice `_MAX_STABLE_SUBSTEP_FRACTION` already is). With `inflow`, the conserved
quantity becomes `final volume == initial + cumulative injected volume`, still exactly checkable,
not just approximate. Deliberately general (a per-cell array, not "boundary"-specific) so the same
mechanism can serve rain input too, if that's added later. Validated on synthetic grids only, per the
project's incremental philosophy (same pattern step 2's Manning weighting followed) — see the new
`test_inflow_*` tests in `backend/tests/test_engine.py` and the second (open-system) scenario added to
`backend/examples/poc_grid.py`.

**Important scope note, caught in review**: this is an engine-level capability only. `inflow` is not
referenced anywhere in `backend/api/` or `frontend/src/` — `POST /simulations` and the WebSocket
streaming loop still call `step()` with no `inflow` argument. Running the actual app (API + frontend)
today behaves identically to before this change; there is no way for a user to trigger an open-system
run yet. Wiring `inflow` through the API/frontend is folded into step 9 below, alongside the real
driving hydrograph, rather than done as a separate throwaway manual-control step — deriving a real
`dt` (still no elapsed-time mapping, only a real cell size from step 3) is also needed first (step 8)
for the hydrograph's 15-minute cadence to mean anything in simulation steps. The real, directly-usable
driving signal for step 9 was already found: ANA/SGB gauge station `86879300` at Porto Fluvial de
Estrela (inside this project's own 6 km ROI) recorded 15-minute river level throughout the May 2024
event (peak 33.66 m), downloadable via ANA's Hidroweb API; SGB/CPRM also already published
flood-extent shapefiles indexed by stage (19–36 m), used in step 10 as the CSI comparison target.

**Step 8 done.** The engine now has a way to derive a real elapsed timestep from Manning flow
velocities under a CFL-style stability condition, using the real `dx = 30 m` cell size established
in step 3 — closing the gap step 5/6/7's "boundary inflow" note flagged above ("still no
elapsed-time mapping, only a real cell size from step 3").
- **`compute_stable_dt(Z, H, N, dx, courant_number=1.0)`** (new function in
  `backend/simulation/engine.py`, dependency-free like `step()` — `dx` is passed in by the caller,
  never imported from `config/`): for each cell, estimates Manning overland-flow velocity via the
  standard wide-channel simplification (hydraulic radius `R ≈ h`), `v = (1/n) * h^(2/3) * sqrt(S)`
  (SI form, coefficient 1, not the US customary 1.49 — everything here is metric), where `S` is the
  cell's steepest real downhill slope over its 8 Moore neighbors, `S = drop / (distance_cells * dx)`
  — `drop` is a water-surface-elevation (`WSE = Z + H`) difference, matching `_single_update`'s own
  head-driven convention, not bare terrain elevation. Takes `v_max` across the whole grid and returns
  `dt = courant_number * dx / v_max` (the textbook CFL bound, `courant_number` as an optional safety
  margin, default `1.0`).
- **Deliberate deviation, documented in the function's docstring**: unlike `_single_update`'s
  direction-weighting (which uses the *destination neighbor's* `N`, an arbitrary documented modeling
  choice for that unrelated purpose), `compute_stable_dt` uses the *source cell's own* `H` and `N`
  for the velocity magnitude — a physical quantity that must have `n` and `h` co-located at the same
  cell, not mixed across cells. A future reader should not try to reconcile the two conventions; they
  answer different questions.
- **Adaptive, not a one-time constant**: `dt` is recomputed fresh from whatever `H` currently is on
  every call, not cached — real flow velocity (and thus the physically meaningful `dt`) changes
  throughout an event as depths rise and fall. A caller builds a real elapsed-time timeline by calling
  this once per simulation step and accumulating `elapsed_time += dt`. This matches
  `docs/tcc-summary.md`'s framing: Jahanbazi & Egger 2017's *adaptive-beyond-CFL* timestep is
  explicitly deprioritized as future work in this project, so a literal, recomputed CFL bound is
  exactly what's in scope here — not a fixed value, and not going further than CFL either.
- **Exact derived property, not just an empirical trend**: holding `Z`/`H`/`N` fixed, slope `S` is
  inversely proportional to `dx`, so velocity `v ∝ dx^(-1/2)`, making `dt ∝ dx^(3/2)` — a clean
  algebraic identity, verified directly in `test_compute_stable_dt_scales_as_dx_to_the_three_halves`.
- **Zero-velocity fallback**: a dry grid, or water present but the surface perfectly flat, makes
  `v_max == 0` (would divide by zero). Falls back to a private module-level constant,
  `_NO_FLOW_FALLBACK_DT_SECONDS = 3600.0` — a finite sentinel, not `math.inf`, since a caller
  accumulating `elapsed_time += dt` needs a usable number, not a poison value, the moment it's hit.
- **Known limitation, flagged for step 9/10 to revisit**: `compute_stable_dt` is fully decoupled from
  `step()`'s `outflow_fraction`/substep decomposition — that machinery is a separate, already-solved
  numerical-stability hack for the synchronous Jacobi update. Nothing yet enforces that the depth
  fraction `step()` actually releases per call is consistent with the real-world `dt` just computed
  for that call. Also, `courant_number=1.0`'s theoretical-edge default is not empirically
  stress-tested in this step (unlike `_MAX_STABLE_SUBSTEP_FRACTION`, which *was* tuned after observing
  real speckling) — revisit once step 9 depends on it for something consequential.
- **`backend/tests/test_engine.py`** (9 new tests): a hand-derived value check (independently computed
  via the textbook Manning/CFL formulas, not by calling the function's own internals) proving the
  formula is wired correctly end-to-end; `dt` shrinks as slope steepens and as depth increases (two
  independent physical drivers, tested separately); the exact `dx^(3/2)` scaling identity; linear
  scaling with `courant_number`; the zero-velocity fallback (both a fully dry grid and a flat-WSE-
  with-water-present case); and input validation (`dx`, `courant_number`, `N`) mirroring `step()`'s
  existing style. Full suite: 35/35 passing (26 from steps 1–7 + 9 new).
- **`backend/examples/poc_real_dem.py`** now calls `compute_stable_dt` once per step (using
  `config.settings.TARGET_RESOLUTION_METERS = 30.0` as the real `dx`), accumulates elapsed real time,
  and prints it alongside the existing mass-conservation checks. Observed on the real 183×192
  Lajeado/Estrela grid: `dt` ranged 0.22s–18.23s across the 100-step closed-pool run (shorter while the
  pool is actively draining down the steep river channel, longer as it settles), totalling ~17.2
  simulated minutes — mass conservation unaffected (`400.0000` in/out, unchanged from step 3/4).
  `backend/examples/poc_grid.py` (synthetic, arbitrary units) is deliberately untouched — the roadmap
  text calls for demonstrating this with the *real* `dx = 30 m`, which only exists in the real-DEM
  script; attaching a fake `dx` to the synthetic PoC would blur the "arbitrary units, no real geodata"
  boundary that script has maintained since step 1.
- No changes to `backend/api/` or `frontend/src/` — wiring a real hydrograph through the API/WebSocket/
  UI is step 9's job, not this one; `POST /simulations` and the WebSocket streaming loop still call
  `step()` with no `dt`/`inflow` argument, exactly as before this step.

To run the CA-engine PoC directly (bare-metal, unrelated to Docker): `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m examples.poc_grid` (must be run as a module, from the `backend/` directory, so `simulation` resolves as a package). Prints step-by-step conservation checks and saves `backend/poc_grid_result.png` (gitignored, regenerate anytime).

To run the full containerized stack: `docker compose up --build` from the repo root, then open `http://localhost:5173`.

## Structure so far

The full target folder structure (including the folders scaffolded ahead of need, each with a README
explaining its purpose and which roadmap step activates it) is documented in `docs/ARCHITECTURE.md` —
read that for the whole picture. What actually has code in it today:

```
backend/
  requirements.txt   # numpy, matplotlib, fastapi, uvicorn, pytest, httpx2, rasterio, requests, python-dotenv
  simulation/
    __init__.py
    engine.py         # core CA step function + seed_pool_at_lowest_point — pure NumPy, no I/O, no geodata
  examples/
    __init__.py
    poc_grid.py        # small artificial-grid demo: fake terrain, pool of water, run N steps, plot/check
    poc_real_dem.py     # same idea, on the real Lajeado/Estrela elevation matrix (step 3)
  api/
    __init__.py
    main.py             # FastAPI() app, lifespan loads Z/N once, includes routers (step 5)
    state.py            # holds loaded Z/N, exposed as overridable FastAPI dependencies (step 5)
    routers/
      __init__.py
      health.py         # GET /health -> {"status": "ok"}
      simulations.py    # POST /simulations, WS /simulations/{run_id}/stream (step 5)
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
    test_api.py
frontend/
  package.json        # react, react-dom, leaflet, tailwindcss/@tailwindcss/vite (npm, TypeScript, Vite)
  vite.config.ts        # @vitejs/plugin-react + @tailwindcss/vite
  src/
    main.tsx              # imports leaflet.css + index.css (Tailwind), renders <App/>
    App.tsx                # 3-column layout: ConfigPanel | FloodMap | LogPanel
    index.css                # @import "tailwindcss";
    types/simulation.ts        # TS mirror of the backend JSON contract (incl. Bounds)
    api/
      config.ts                 # API_BASE_URL / WS_BASE_URL (VITE_API_BASE_URL, default localhost:8000)
      client.ts                  # createSimulation() -> POST /simulations
      stream.ts                   # openSimulationStream() -> WebSocket wrapper (handles code 4004, disconnects)
    hooks/
      useSimulationRun.ts          # orchestration state machine: idle -> starting -> streaming -> done|error
    rendering/
      depthToImage.ts               # depth[][] -> canvas data URL, orange-red ramp (transparent at 0 depth)
    components/
      ConfigPanel.tsx                # steps/frame_interval/outflow_fraction form
      FloodMap.tsx                    # plain Leaflet + OSM tiles + L.ImageOverlay, positioned via API bounds
      LogPanel.tsx                     # status/grid_shape/bounds + scrolling step/volume log + error banner
```

`validation/` still exists as an empty, README-documented placeholder — no code yet, added in step 8.
`data/raw/` and `data/processed/` now hold real (gitignored) files once `download_dem.py`/
`download_landcover.py` and the ingestion pipelines have been run locally.

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
2. **Add Manning roughness weighting** *(done)* — introduce a synthetic roughness matrix `N`, extend the transition rule to match the TCC's full documented equation (`Q_i = (1/n_i) h_i^(5/3) sqrt(S_i)`), still on artificial grids.
3. **Real DEM ingestion** *(done)* — `rasterio` + a hand-rolled priority-flood sink filler; downloaded/clipped a real SRTMGL1 tile (via OpenTopography) for a small Lajeado/Estrela test box, reprojected to a metric CRS with square pixels, sink-filled it, and ran the validated engine on real terrain (still no roughness-from-data or historical validation yet).
4. **Real land-cover / roughness data** *(done)* — MapBiomas Collection 10 raster → Manning's n lookup table → real `N` matrix, replacing the synthetic uniform one `poc_real_dem.py` previously used.
5. **Wrap in FastAPI** *(done)* — `POST /simulations` + `WS /simulations/{run_id}/stream`, serving the real Lajeado/Estrela grid with JSON numeric frames. Still no frontend — verified with `curl` + a `websockets` script.
6. **React + Vite + Leaflet frontend** *(done)* — config panel, live map overlay fed by the WebSocket stream, log/metrics panel (loosely following the Figure 12 mockup from the TCC).
7. **Docker Compose** *(done)* — containerize backend + frontend + static data volume.
8. **Real timestep (`dt`) derivation** *(done)* — `compute_stable_dt` derives a real `dt` from Manning flow velocities under a CFL-style stability condition, using the real `dx = 30m` cell size already established in step 3. See "Step 8 done" above for the full design (source-cell velocity convention, adaptive recomputation, the `dt ∝ dx^(3/2)` identity, and the zero-velocity fallback).
9. **Real driving hydrograph, wired end-to-end** *(current step)* — download the ANA/SGB gauge station `86879300` (Porto Fluvial de Estrela) 15-minute river-level record for the May 2024 event via the Hidroweb API, convert it into a time-varying `inflow` series using step 8's `dt`, and — unlike the engine-only `inflow` capability added ahead of schedule (see "Current status" above) — actually thread it through: `POST /simulations`/the WebSocket streaming loop in `backend/api/routers/simulations.py`, and the frontend (`ConfigPanel`/`LogPanel` need to reflect an open-system run, since volume will grow instead of staying flat). Only once this step is done can a user run a real, gauge-driven event through the actual app, not just through a Python script.
10. **CSI/RMSE validation against real events** — ingest SGB/CPRM's stage-indexed flood-extent shapefiles (and HWM/SWOT ground truth where available) for the 2023/2024 events, and implement CSI (spatial overlap between simulated and observed flooded extent) and RMSE (depth, where ground-truth depth exists) in the already-scaffolded `validation/` module.
11. **Performance benchmarking** — vectorized NumPy vs. loop-based comparison, exploratory CuPy/GPU, run against the real event replay from steps 9–10.

Update the "Current status" section above as steps complete — this file is meant to be read at the start of future sessions instead of re-deriving the plan from scratch.

## Possible future features (ideas, not yet scheduled)

Raised in session while trying out the step-6 frontend and discussing what would make the demo feel
like an actual usable flood simulator rather than just validated mechanics. Unlike the numbered
roadmap above (sequential, each step a prerequisite for the next), these are independent candidate
enhancements — not committed to, not ordered, and not required for steps 7-11. Grouped by how much
they'd cost and whether they touch the TCC's documented model:

**Cheap — UI/plumbing only, no engine or model changes:**
- Expose seed volume as a real config-panel parameter (currently hardcoded `SEED_VOLUME = 400.0` in
  `backend/api/routers/simulations.py`, not user-controllable at all).
- Click-to-place seed location on the map, instead of always seeding at the terrain's lowest point
  (`seed_pool_at_lowest_point` in `simulation/engine.py`) — needs a small API addition to accept a
  start coordinate, but no change to the transition rule itself.
- Visual polish: better depth→color ramp/legend (current one is a quick orange-red fix for
  visibility, not a designed palette), smoother frame-to-frame transitions, terrain shading under
  the flood overlay, general UI/layout polish.
- Timeline scrubber: buffer received frames client-side (`{step, depth, volume}` per frame already
  has everything needed) and add a slider to re-render any past frame instead of only ever showing
  the live one. Fully independent of every other item here — buildable against what already exists
  today.

**Moderate — small engine option, no change to the documented base model:**
- Neighborhood-type toggle (Moore vs. von Neumann) in the config panel — the engine is Moore-only
  today; von Neumann would be a genuinely new, smaller-neighborhood code path, not just a flag.

**Bigger — real modeling changes, a deliberate scope decision for the thesis, not just engineering:**
- **Rain input** (rate/duration exposed in the UI): needs a source term that injects volume into
  `H` every step (e.g. mm/hr converted to volume/cell/step). Technically straightforward, but the
  TCC's documented base model is explicitly *closed, no rain/infiltration* — this changes the
  validated invariant from "total volume constant" to "final volume = initial + cumulative rain
  input" (still checkable, just a different one), and changes what the thesis is claiming to model.
  Should be a deliberate choice, not a quiet addition — flagged as worth discussing with an advisor.
- ~~Real elapsed time (minutes/hours) instead of abstract step counts~~ — **promoted out of this
  backlog into the numbered roadmap as step 8** (needed as a prerequisite for step 9's real
  hydrograph, not just a nice-to-have), see the roadmap above.
- Rain input remains the one item here still touching the TCC's documented base model and needing an
  advisor conversation; it is deliberately **not** folded into steps 8-11, which use boundary inflow
  (already engine-side, being wired end-to-end in step 9) as the real event's driving input instead.
- **Boundary inflow itself exists in the engine (`step()`'s `inflow` parameter) but is not reachable
  through the API or frontend yet — that end-to-end wiring is step 9 above, not a "future feature."**
