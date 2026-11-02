# Terranova: full context for writing the TCC II

This file is the context pack for an assistant that helps write the TCC II (the undergraduate thesis)
about Terranova. It collects, in one place, what was proposed in TCC I, what was built, every decision
that changed along the way and why, all validated results with their exact numbers, the problems found
while building, and the limitations. It is condensed from the repository's own records
(`docs/project-plan.md`, `docs/tcc-deviations.md` §0–§25, `docs/development-difficulties.md`,
`docs/ARCHITECTURE.md`, `docs/tcc-summary.md`, the git history and the code). Section numbers written as
"§16.2" refer to `docs/tcc-deviations.md`, which holds the full technical write-up of each topic.

---

## 0. How to use this file (read first)

**Who and what.** Author: Lucca Coutinho Heineck. Course: Engenharia de Software, Universidade do Vale do
Taquari (Univates), Lajeado, RS, Brazil. Advisor: Prof. Me. Edson Moacir Ahlert. TCC I (proposal and
literature review) was submitted in June 2026 with the title *"Modelagem e Simulação de Inundações no
Vale do Taquari Baseada em Autômatos Celulares"*. TCC II is the implementation and evaluation, described
here. The thesis is written in **Brazilian Portuguese** under Univates' ABNT-based template. Code,
comments and repository docs are in English. A glossary of English terms → Portuguese thesis terms is in
§19.

**Rules for the assistant writing with this file:**
1. **Use only numbers that appear in this file.** Every figure here was measured in the project. Do not
   round them into stronger claims, and do not invent numbers (run times, CSI values, cell counts, DOIs,
   page numbers).
2. **Keep the qualifiers.** The validated result is *one event (May 2024), one study area (a ~6 km box at
   Lajeado/Estrela), one grid (90 m)*, scored on *flood extent only* (no depth validation is possible,
   §12.6). The thesis should say so.
3. **Cite the "gap-corrected" CSI with its explanation.** The headline number (CSI ≈ 0.90) is scored with
   a documented exclusion of cells the reference dataset never modeled (§10.4). The naive score (≈ 0.40)
   must be reported next to it, with the reason for the correction.
4. **Negative results are results.** Several investigations ended in "this did not work, here is the
   evidence" (outlet margin, substep relaxation, partial time window, single-ulp divergence). They belong
   in the methodology/discussion chapters, not hidden.
5. **Where TCC II deviates from TCC I, say so explicitly**, using the "TCC I said X → we did Y → because Z"
   table in §13.
6. When the author asks for a figure, use the captions in §16 (Portuguese, ready to use) and the PNGs in
   `docs/tcc2/figures/`.
7. References: §18 lists every work the project used, with the details known. Fields marked "(to
   complete)" must be filled from the actual source, not guessed.

**Status in one paragraph.** All 11 roadmap steps are done (§3). The system is a working web application
(Python/FastAPI backend, React/Leaflet frontend, Docker Compose) running two flood engines on real public
data for the May 2024 Taquari flood: a time-stepped macroscopic cellular automaton (the thesis' core
model) and a non-temporal "fast mode" inspired by Torres et al. (2022). Against the official SGB/CPRM
flood extent of the May 2024 peak, the temporal CA scores **CSI 0.899** (gap-corrected; naive 0.395) on
the 90 m grid in ~7 minutes on a laptop CPU, and the fast mode scores **CSI 0.896** in ~73 ms. Results hold
at 60 m without re-tuning (0.875 / 0.880). Vectorized NumPy is 55–72× faster than equivalent Python loops,
and run time and memory scale linearly. RMSE against high-water marks could not be computed because no
usable observation dataset exists for the area.

---

## 1. The research problem and objectives (from TCC I)

**Motivation.** The Vale do Taquari (Taquari-Antas basin, ~26,430 km², 119 municipalities, main
contributor to the Guaíba basin) had record floods in September 2023 and May 2024, exceeding the 1941
record. In May 2024 the river at Lajeado/Estrela rose from 13.00 m to 33.66 m in about 72 hours.
Hydrodynamic models that solve the shallow-water equations (e.g. HEC-RAS 2D) are accurate but expensive,
which limits fast, repeated, emergency-response use.

**Research question.** How can a software architecture based on macroscopic cellular automata enable
agile modeling and simulation of flood extents, using public topographic data, for the Vale do Taquari?

**General objective.** Develop and evaluate an efficient and representative CA-based flood simulation
model for the Vale do Taquari.

**Specific objectives** and where TCC II stands on each:

| Specific objective (TCC I) | Status in TCC II |
|---|---|
| (a) Prepare DEM and historical flood data | Done: SRTM DEM, MapBiomas 2024 land cover, ANA gauge record, SGB/CPRM flood extents, all downloaded by scripts and processed reproducibly (§6) |
| (b) Design and implement the simulator and its transition rules | Done: temporal CA engine + fast mode + API + web frontend + Docker (§4, §7, §8) |
| (c) Validate accuracy against real 2023/2024 flood maps | Done for May 2024 (CSI, hit rate, false-alarm rate). 2023 not validated (no reference extent was ingested for it). RMSE closed as a data limitation (§12.6) |
| (d) Evaluate computational performance for rapid response | Done: loops vs. NumPy, scaling with grid size and iterations, GPU (CuPy) experiments (§12.9) |

---

## 2. What TCC I proposed (baseline for comparison)

- **Model:** macroscopic CA. Each cell holds terrain elevation `Z` and water depth `H`. Water surface
  elevation `WSE = Z + H`; water flows from higher to lower WSE across the 8-cell **Moore** neighborhood,
  distributed by Manning's equation `Q_i = (1/n_i) · h_i^(5/3) · √S_i` (zero for upslope directions),
  normalized into transport factors `F_Ti = Q_i / ΣQ_i`, `V_i = F_Ti · V_tot`. Diagonal neighbors use a
  longer distance to avoid geometric distortion. Mass is conserved; the base model is **closed** (no
  rain, no infiltration). Rules apply to all cells simultaneously (vectorizable).
- **Cell states** (an optimization in the CA theory chapter): Inactive, Transport, Accumulation.
- **Informal PoC already in TCC I (§4.3.1):** synthetic terrain with a hill and a basin, a central pool,
  closed system, head-difference redistribution without Manning; after 100 steps: 1,060 flooded cells,
  mean depth 0.6393, total volume 678.6000 (conserved), 0.5428 s (Quadro 6). A separate HTML/CSS/JS UI
  mockup (Figure 12 of TCC I).
- **Data:** SRTM/TOPODATA DEM (~30 m), optional LiDAR, MapBiomas land cover → Manning's n via a static
  dictionary, ANA/SGB telemetry and high-water marks (HWM) for validation only, SWOT satellite for
  independent validation. Preprocessing: clip to the region, sink filling.
- **Architecture:** Docker; Python backend reading preprocessed rasters from disk (no DB); NumPy
  (CuPy-compatible) engine; FastAPI REST + WebSocket broadcasting frames every N iterations as **base64
  PNG** and **persisting H[t] to disk**; validation metrics server-side. React + TypeScript + Vite
  frontend with a config panel (initial river stage, rainfall/volume, neighborhood type), a Leaflet map
  with an **OpenStreetMap** base layer, and a log/metrics panel.
- **Validation plan:** CSI (with hit rate and false-alarm rate) for extent; RMSE against HWM/SWOT for
  depth; performance vs. grid size and iterations, NumPy vs. naive loops, exploratory GPU.
- **Timeline (Quadro 7):** Jun Docker/repo/WebSocket → Jun DEM/roughness → Jul transition rules → Jul
  optimization/timestep → Aug React/Leaflet → Aug WebSocket → Sep HWM/SWOT and 2024 calibration → Oct
  metrics and GPU → Nov writing.
- **Related work used for positioning:** Liu et al. 2015 (gravity-only CA), Jahanbazi & Egger 2017 (OFS-CA,
  adaptive timestep beyond CFL; explicitly deprioritized), Jamali et al. 2019 (CA-ffé, 250–1,100× faster,
  no velocity/arrival time), Tavakolifar et al. 2021 (SWMM-2DCA), **Torres et al. 2022** (top-down CA,
  Moore, Manning; HR > 94%, ~1 s vs. 2,012 s; the closest match), Monte et al. 2016 (MGB-IPH + HEC-RAS),
  Sales et al. 2025 (SWOT virtual gauges). TCC I positions this project as Torres-like but
  **time-stepped**, so it can represent wave-front arrival.

---

## 3. How the work was done (methodology of development)

### 3.1 Order of work: algorithm first, infrastructure later

TCC I's Quadro 7 starts with Docker/repo/WebSocket. TCC II **inverted that**: the transition rule (the
highest academic risk) was implemented and validated on small synthetic grids first, with exact mass
conservation as the correctness check, and only then were real data, API, frontend and Docker added.
Each step was validated before the next started. This is a deliberate methodological choice to
front-load risk, recorded from the first session (§0 of the deviations log).

### 3.2 The roadmap as executed (dates from the git history, 2026)

| Step | What | Done |
|---|---|---|
| 1 | Core CA engine + synthetic PoC (exact mass conservation, crescent-shaped spread around a hill) | 22 Aug |
| 2 | Manning roughness weighting (`√S / n`) on synthetic grids; pytest suite starts | 25 Aug |
| 3 | Real DEM ingestion (SRTMGL1 via OpenTopography, reprojection, priority-flood sink filling) | 26 Aug |
| 4 | Real land cover (MapBiomas 2024 → Manning's n) | 26 Aug |
| 5 | FastAPI: `POST /simulations` + WebSocket stream | 26 Aug |
| 6 | React + Vite + Leaflet frontend | 31 Aug |
| 7 | Docker Compose (backend + frontend + data volume) | 1 Sep |
| — | Boundary inflow source term (open system), ahead of step 8 | 7 Sep |
| 8 | Real timestep `dt` from Manning velocities under a CFL condition | 13 Sep |
| 9 | Real May 2024 hydrograph (ANA gauge 86879300) driving the engine end to end | 16–18 Sep |
| — | Outlet boundary condition (fixes whole-domain flooding) | 21 Sep |
| 10 | CSI validation against the SGB/CPRM May 2024 extent (first score: 0.133) | 22 Sep |
| — | Investigation of the low score; `outflow_fraction` calibrated to 0.085; Estrela reference gap found | 22–27 Sep |
| — | GPU/CuPy first measurement; RMSE closed as data limitation; fast mode (offline, then in the app) | 27 Sep |
| — | Frontend: two-pane compare, replay preset, timeline scrubber, click-to-seed, von Neumann option, 60 m grid | 27–29 Sep |
| — | Frontend redesign, basemaps, observed-extent layer with live CSI, fast mode HAND rating curve (0.53 → 0.896) | 1 Oct |
| — | Input layers, cell inspector, About page, arrival-time/max-depth maps, exports, EN/pt-BR UI | 2–5 Oct |
| — | 60 m grid scored | 6 Oct |
| 11 | Performance comparisons (loops vs. NumPy, scaling, fused GPU kernel); Playwright smoke tests | 8 Oct |

92 commits from 17 Aug to 8 Oct 2026.

### 3.3 Verification practices (a methodological upgrade over TCC I)

TCC I's PoC was validated by printed metrics and visual inspection. TCC II added:
- **Automated tests:** 198 backend tests (pytest) covering engine invariants, hand-computed values,
  ingestion, metrics, API contract, regression against a frozen copy of the engine, and bit-identity of
  the alternative engines; 6 browser smoke tests (Playwright) against the real backend.
- **Invariants asserted at every step of every real run:** non-negative depth and exact volume balance
  (closed: `ΣH = V0`; open: `ΣH = inflow − outflow`, to relative 1e-9).
- **Real-data checks, not only synthetic ones.** A lesson learned (§11): synthetic stability tests passed
  a change that produced a visible artifact on real terrain, so numerical changes are checked on real
  terrain before being accepted.
- **Noise-floor checks before trusting a CSI difference** (§10.5): a "shift search" measures how much CSI
  changes when the simulated mask is shifted by 1–3 cells; a parameter effect smaller than that is noise.
- **Bit-identity instead of "close enough"** when comparing implementations, because the engine amplifies
  one floating-point ulp into ~0.2 m within ~50 steps (§12.10).
- **Browser verification** of every frontend feature against real servers, which caught bugs no type
  checker found (e.g. a Stop button that restarted the run, a React dev-mode memory exhaustion).
- **Design notes and review:** step 9 had a written design spec and implementation plan
  (`docs/superpowers/specs|plans/2026-09-16-*.md`); whole-branch reviews caught real errors (the wrong
  inflow edge, §11).

### 3.4 Working process and decisions taken with the author

The code was developed by the author with an AI coding assistant (Claude Code) in working sessions; each
session read the project docs first and updated them at the end, which is why the repository keeps a
decision log. Whether and how to disclose AI assistance in the thesis follows Univates' rules and is the
author's decision. Decisions the author made explicitly during those sessions (as recorded in the docs):
- Build in the incremental order above, not TCC I's calendar order.
- Manning roughness affects only the *direction* of outflow, not its amount (confirmed with the author at
  step 2, §7.3).
- Docker and a FastAPI skeleton were added ahead of their step at the author's request (Aug 25).
- Frontend unit tests were deferred (later replaced by Playwright smoke tests).
- Basemap returned to OpenStreetMap after a period on Esri Dark Gray (a later redesign made "Relief" the
  default).
- Rain input deferred until it is discussed with the advisor, since it changes the documented base model.
- The loop-based benchmark engine uses Python lists (chosen with the author as the fastest honest
  pure-Python form, so the measured NumPy speedup is conservative).
- English/Portuguese UI switch added.

---

## 4. Final system architecture

### 4.1 Overview

```
frontend (React/TS/Vite/Leaflet)  --HTTP + WebSocket-->  api (FastAPI)
                                                          |
                     +------------------+-----------------+-----------------+
                     v                  v                 v                 v
               simulation/        ingestion/          validation/        config/
          (engine.py, fast_engine)  (DEM, land cover,   (CSI, HR, FAR)   (paths, ROI,
           pure NumPy, no I/O)       hydrograph, extent)                  constants)
                                          |
                                     data/raw -> data/processed (GeoTIFF)
```

- **Dependency rule:** arrows point from orchestration to core logic only. `simulation/` imports nothing
  from the project (no I/O, no geodata, no framework), so it is testable on plain arrays and can run on
  NumPy or CuPy arrays unchanged. `config/` is a leaf. `api/` wires everything. `examples/` (scripts for
  experiments) and `scripts/` (download CLIs) are leaves nobody imports.
- **No database:** static rasters are preprocessed to files and loaded once at API startup; runs live in
  memory and are consumed once.

### 4.2 Technology stack (as built)

| Layer | Technology |
|---|---|
| Engine | Python 3.14.5 (dev venv; the Docker image uses python:3.12-slim), NumPy 2.5.3 (vectorized); optional CuPy 14.2 on CUDA for GPU experiments |
| Geodata | rasterio (GDAL): reprojection, resampling, rasterization, COG range reads |
| API | FastAPI + uvicorn, WebSocket streaming, pydantic validation |
| Tests | pytest (198 tests), Playwright (6 browser smoke tests) |
| Frontend | React 19, TypeScript 6, Vite 8, Leaflet 1.9 (plain, not react-leaflet), Tailwind CSS 4, Geist font, oxlint |
| Deployment | Docker Compose: backend (python:3.12-slim) + frontend (Node build → nginx), `data/` bind-mounted |
| Hardware for all measurements | Laptop: Intel i7-13620H CPU, NVIDIA RTX 4050 Laptop GPU (6 GB) |

### 4.3 Backend modules

- `simulation/engine.py`: the temporal CA (`step`, `compute_stable_dt`, `outflow_fraction_for_dt`,
  seeding helpers). §7.
- `simulation/fast_engine.py`: the non-temporal fast mode (`classify_steady_flood`). §8.
- `simulation/engine_loops.py`, `engine_cupy_fused.py`: benchmark-only, bit-identical alternatives (§12.9).
- `ingestion/dem.py`: reprojection, nodata crop, priority-flood sink filling, georeference helpers
  (`lonlat_to_cell`, footprint).
- `ingestion/landcover.py`: MapBiomas alignment (nearest neighbor) and the Manning table.
- `ingestion/hydrograph.py`: ANA XML parsing, empirical rating curve, discharge → per-cell inflow,
  inflow-edge and outlet detection.
- `ingestion/flood_extent.py`: SGB/CPRM polygons → boolean masks; the offline Estrela coverage-gap
  correction.
- `validation/metrics.py`: CSI, hit rate, false-alarm rate (pure functions on boolean arrays).
- `api/`: routers for simulations (REST + WebSocket), grids, hydrograph, validation, health.

### 4.4 API contract

- `POST /simulations` validates and registers a run, returning `run_id`, grid shape and bounds. Fields:
  `mode` (`seeded_pool` | `gauge_driven` | `fast`), `resolution` (30 | 60 | 90, default 30),
  `frame_interval`, `outflow_fraction` (default 0.085), `neighborhood` (`moore` | `von_neumann`, temporal
  only; von Neumann capped at 0.085), `steps` (seeded pool only), `stop_at_peak` (gauge-driven),
  `seed_volume` and `seed_location` (seeded pool). Invalid combinations → 422; missing hydrograph → 503.
- `WS /simulations/{run_id}/stream` runs it and sends JSON frames (`step`, `depth` grid, `volume`, and for
  gauge-driven runs `elapsed_time`, `cumulative_inflow`, `cumulative_outflow`), then `{"done": true}`.
  The fast mode sends exactly one frame (`step: 0`). Unknown or consumed run → close code 4004. Temporal
  loops yield every step, so a disconnect stops the run within one step and other requests are served.
- `GET /grids`, `GET /grids/{resolution}/inputs` (terrain and land-cover per cell), `GET /hydrograph`,
  `GET /validation/may2024` (observed extent + excluded cells on the 90 m grid), `GET /health`.

### 4.5 Frontend features

Top bar (status, Start/Stop, About, language), left panel with Setup / Results / Log tabs, full map.
- **Setup:** engine (temporal CA / fast), scenario (seeded pool / May 2024 gauge-driven), grid (30/60/90
  m), neighborhood, seed volume, click-to-place seed (converted with the grid's true UTM transform),
  engine tuning (outflow fraction, frame interval).
- **"Replay May 2024 flood" preset:** one click runs the fast engine, then the temporal engine to the
  observed peak on the 90 m grid, side by side.
- **Map views:** Temporal / Fast / Compare (two synced panes). Temporal products: depth (6 fixed bands
  0.01–0.5–2–5–10–20+ m), arrival time, maximum depth. Fast mode drawn as extent only.
- **Layers:** observed May 2024 extent as hit / miss / false alarm / not scored; terrain and roughness
  inputs; basemaps (Relief with hillshade, Topographic, Streets/OSM, Satellite); overlay opacity.
- **Timeline scrubber** over a bounded (32 MiB) Float32Array frame buffer with decimation; playback 1×/4×/16×.
- **Results tab:** live CSI / hit rate / false-alarm rate (gap-corrected and naive) for real-event runs,
  gauge hydrograph chart with the current time marked.
- **Cell inspector:** inputs (Z, land cover, n), depth/WSE/first-wet time, the 3×3 outflow split.
- **Exports:** PNG of the map with legends; flooded extent as GeoJSON.
- **About page**, English / Brazilian Portuguese switch, phone-width layout.

---

## 5. Study area and grids

- **Region of interest (ROI):** a ~6 km box on the Taquari river between Lajeado (west/north-west bank)
  and Estrela (east/south-east bank): lon −51.99 to −51.93, lat −29.505 to −29.455. Kept small for fast
  iteration; widening it is a settings change plus re-download.
- **CRS:** SIRGAS 2000 / UTM zone 22S (EPSG:31982), square cells.
- **Grids:** 30 m: 183 × 192 = 35,136 cells (the live default). 60 m: 91 × 96 = 8,736. **90 m: 61 × 64 =
  3,904 (the validated grid).** The river enters on the **north** edge (9 inflow cells at 30 m, 4 at 60 m,
  3 at 90 m) and leaves through the **south** edge outlet (9 cells at 30 m, 2 at 90 m).
- **Gauge:** ANA station 86879300 "ESTRELA" (Porto Fluvial de Estrela), lat −29.4717, lon −51.965 (ANA
  HidroInventario), inside the ROI; cell (20, 26) on the 90 m grid, (30, 39) at 60 m, (61, 79) at 30 m,
  on Lajeado's bank of the DEM channel.

---

## 6. Data sources and preprocessing (with the decision behind each)

### 6.1 Terrain (DEM)
- **Source:** SRTMGL1 (1 arc-second SRTM) via the **OpenTopography REST API** (free API key), clipped
  server-side to the ROI (`scripts/download_dem.py`). *TCC I named SRTM/TOPODATA; TOPODATA's portal is
  manual and not scriptable, so the same SRTM data class was taken from a reproducible HTTPS API.*
- **Reprojection** from EPSG:4326 to EPSG:31982 at 30 m (bilinear). Needed because the engine's neighbor
  distances (1 and √2 cells) assume square metric cells. *Not mentioned in TCC I.*
- **Corner nodata crop:** reprojection rotates the box slightly and leaves nodata slivers at the corners
  (which would act as bottomless pits); a greedy border trim removes them.
- **Sink filling:** a hand-written **priority-flood** (Barnes et al. 2014) in ~30 lines with Python's
  `heapq`. `pysheds`/`richdem` were tried first, but `pysheds`' numba JIT failed to compile on Python 3.14.
  On the 30 m tile filling changed ~11% of cells by up to 10 m (SRTM radar noise, mostly in the river
  channel).
- **Known limitation:** SRTM is from ~2000 and has **whole-meter vertical resolution**; the river channel
  sits at 11–14 m over the whole ~8.3 km reach. This quantization limits slope estimation and the
  granularity of flood edges (§8.3, §12.5).
- 60 m and 90 m grids are built from the same raw file by the same pipeline (`resolution` parameter).

### 6.2 Land cover → Manning's n
- **Source:** MapBiomas Collection 10, **year 2024** (chosen to match the validated event), read as a
  Cloud-Optimized GeoTIFF over HTTP range requests (`/vsicurl/`): ~40 KB downloaded instead of the ~800 MB
  national file, no key.
- **Alignment:** reprojected onto the DEM's exact grid with **nearest-neighbor** resampling (class IDs are
  categorical; bilinear would invent meaningless classes). Regression-tested.
- **Coefficients:** MapBiomas has no roughness table, so each class was cross-walked to the nearest NLCD
  class in the NRCS (Kansas) Manning's n table used for HEC-RAS 2D, rooted in Chow (1959):

| MapBiomas class | n | | MapBiomas class | n |
|---|---|---|---|---|
| 3 Forest Formation | 0.160 | | 21 Mosaic of Uses (as crops) | 0.035 |
| 6 Floodable Forest | 0.120 | | 24 Urban Area | 0.150 |
| 9 Forest Plantation (as forest) | 0.160 | | 25 Other non-vegetated | 0.025 |
| 11 Wetland | 0.070 | | 30 Mining | 0.025 |
| 12 Grassland | 0.035 | | 33 River, lake, ocean | 0.040 |
| 15 Pasture | 0.030 | | 39 Soybean | 0.035 |
| | | | 41 Other temporary crops | 0.035 |

  Ten classes occur in the ROI (urban area 42% of the 30 m grid, mosaic of uses 24%, forest 12%, water
  6%). Two documented simplifications: plantation = natural forest; mosaic of uses = crops. A class not in
  the table raises an error rather than being guessed.
- **Known limitation:** land cover is 2024 while the DEM is ~2000 (vintage mismatch, documented, not
  resolved).

### 6.3 Driving hydrograph (May 2024)
- **Source:** ANA telemetry for station 86879300, via ANA's key-free SOAP service, operation
  `DadosHidrometeorologicos` (the first choice, `HidroSerieHistorica`, silently returned a monthly
  summary that dropped part of the window; found by reading the live WSDL). Window 27 Apr – 10 May 2024,
  610 readings (~15-minute to hourly).
- **Stage → discharge:** the plan was to research an external rating curve, but the record itself carries
  ANA's computed discharge (`Vazao`) on many rows. The project builds an **empirical rating curve from
  288 real (stage, discharge) pairs** spanning 14.11–33.66 m and interpolates. Below 14.11 m (45.8% of
  readings, the pre-flood lead-in) discharge is held at the lowest calibrated value, 2,251.8 m³/s
  (documented simplification, not extrapolated).
- **Peak:** stage **33.66 m** at **133.5 h** after the record start (**2 May 2024, 13:30**), discharge
  **23,472 m³/s**.
- **Role change vs. TCC I:** TCC I said gauge data would be used only for validation. Here it **drives**
  the model. This is not circular: the spatial validation target is a different dataset (SGB/CPRM extent).

### 6.4 Reference flood extent (ground truth)
- **Source:** SGB/CPRM flood-alert system for **Lajeado** (developed with IPH-UFRGS): HEC-RAS 2D-modeled
  flood-extent polygons indexed by river stage, published as a public ArcGIS REST MapServer
  (`geoportal.sgb.gov.br/server/rest/services/LAJEADO/MapServer`). Layer `COTA_3367cm` (33.67 m) matches
  the observed peak (33.66 m) and is the CSI target. Layers 19.00 m and 26.00 m are also downloaded for
  the coverage-gap correction.
- Rasterized onto each grid (reprojected from EPSG:4674). At 90 m: **831 of 3,904 cells observed flooded
  (21.3%)**.
- Important property discovered later: the product was built and calibrated for **Lajeado**; the
  **Estrela side was never modeled** (§10.4).

### 6.5 Other sources checked
- **SWOT** (NASA/CNES) raster pass of 6 May 2024: covers the ROI; used only as corroborating evidence
  that Estrela flooded (§10.4). Copernicus EMSN194 and EMSR720 do not overlap the ROI; Copernicus GFM had no
  usable signal. **High-water marks:** only a statewide CPRM PDF report exists (no point table) → RMSE not
  computed (§12.6).

---

## 7. The temporal CA engine (the thesis' core model)

All in `backend/simulation/engine.py`, pure functions over 2-D arrays.

### 7.1 One step (`step(Z, H, N, outflow_fraction=0.085, inflow, boundary_elevation, boundary_roughness, neighborhood)`)

For each cell, with `WSE = Z + H` and neighbors `i` in the Moore neighborhood (8 cells; distance 1 for
orthogonal, √2 for diagonal):
1. `drop_i = max(WSE_cell − WSE_i, 0)`, `S_i = drop_i / distance_i`.
2. Weight `w_i = √S_i / n_i`, where **`n_i` is the roughness of the receiving neighbor**.
3. The cell releases `outflow_fraction · H` in total (if any weight is positive), split as
   `w_i / Σw` to each neighbor. All cells update simultaneously (synchronous/Jacobi update).
4. Optional `inflow` (per-cell source) is added after the redistribution.

This is TCC I's equation `Q_i = (1/n_i) h^(5/3) √S_i`, `F_Ti = Q_i / ΣQ`: since `h^(5/3)` is the same in all
directions leaving a cell, it cancels in the normalization, so only `√S_i / n_i` remains.

### 7.2 Engineering additions not in TCC I's equation (each with its reason)
- **`outflow_fraction` cap:** a cell releases at most this fraction of its depth per step. It keeps the
  explicit scheme stable and `H` non-negative. Initially 0.5 (never tuned); **calibrated to 0.085** against
  May 2024 (§10.3), now the single default constant `DEFAULT_OUTFLOW_FRACTION`.
- **Substep decomposition:** releasing the whole fraction in one synchronous pass made neighbors overshoot
  each other and produced a checkerboard/speckle pattern (the same family of instability as violating a
  CFL condition). Diagnosed with a flat-water control (artifact appears with zero asymmetry) and a
  fraction sweep (magnitude linear in the fraction). Fix: each step runs `ceil(f / 0.01)` smaller passes
  with per-pass fraction `1 − (1 − f)^(1/k)`, which removes the same total. At 0.085 that is 9 passes.
  Raising the bound to 0.02 passed both synthetic tests but produced a visible artifact on real terrain,
  so it stays 0.01 (§11).
- **Walls by default:** the grid is padded with `+∞` elevation, so no water leaves → exact conservation.
- **Correction of a step-1 error:** step 1 used bare slope instead of `√S`; caught when Manning weighting
  was added in step 2.

### 7.3 Modeling choices where TCC I is silent
- **Roughness steers direction only.** Because `h^(5/3)` cancels, `N` changes *where* the capped release
  goes, not *how much* leaves. Decided with the author; a magnitude effect would have needed an
  unjustified constant at that stage. Proven by a test: a 4:1 roughness ratio between two equal-slope
  neighbors yields exactly a 4:1 outflow ratio.
- **Destination-cell roughness** for `n_i` (the surface water is entering).
- **Finding:** in a closed system run to equilibrium, the final water shape is identical regardless of
  roughness (bit-identical extent statistics by step 50 in a uniform vs. channel-roughness comparison;
  mid-transient difference ~0.0075 mean depth at step 10). Roughness affects path and speed, not where a
  fixed volume settles, since a flat water surface has no slope for `n` to act on.
- **Cell states (Inactive/Transport/Accumulation) were not implemented.** The engine applies one dense
  vectorized update to the whole grid; at these grid sizes that was fast enough (55–72× faster than loops,
  §12.9). This is a simplification relative to TCC I's theory chapter and should be stated.

### 7.4 Open boundaries: inflow and outlet
- **Boundary inflow** (`inflow` array): turns the closed system into an open one; the invariant becomes
  `final volume = initial + cumulative inflow`, still exact. The real discharge `Q(t)` is converted to depth
  per inflow cell per step: `Q · dt / (cell area · number of inflow cells)`. Generic enough to also serve
  rain later (not used for rain).
- **Inflow edge detection:** a heuristic first picked the **east** edge ("highest boundary minimum is
  upstream"); a review against the real DEM showed the channel only crosses north and south (east was a
  hillside dip 15 m above the bed). Corrected to **north**; the heuristic is valid only on edges that carry
  the channel and needs a human check at each new resolution (it produced spurious channel cells on west
  and east at 60 m).
- **Outlet** (`boundary_elevation`/`boundary_roughness`): the south edge's channel cells get a "virtual
  outside" elevation equal to their own elevation minus 2 m (and water's n = 0.040). Water reaches it through
  the same weighting and leaves the domain. Without arguments, behavior is bit-identical to the walled
  engine. Outflow is bookkept as `ΣH_before + Σinflow − ΣH_after`, giving the invariant
  `ΣH = initial + inflow − outflow`.
- **Why the outlet was necessary:** with walls everywhere, the real event's ~9.1 × 10⁹ m³ would imply a
  mean depth of ~288 m over the ROI (terrain max ~96 m). A real run to the peak at 90 m without an outlet
  had the **whole ROI flooded, mean depth 113.88 m, max 147.27 m**, by the peak; restricting validation to
  a partial time window therefore does not avoid it. With the outlet (at `outflow_fraction = 0.5`): **max
  depth 16.43 m, 449 of 3,904 cells flooded (11.5%)**, and the run took 82,933 steps / 23.1 min instead of
  403,554 steps / 1.92 h: a draining system never builds the extreme gradients that shrink `dt`.
  Correctness and speed came from the same fix.

### 7.5 Real elapsed time: `compute_stable_dt` (CFL)
- Per cell, Manning velocity with the wide-channel simplification (hydraulic radius ≈ depth), SI units:
  `v = (1/n) · h^(2/3) · √S`, with `S` the steepest WSE drop over neighbors divided by `distance · dx`, and
  `n`, `h` of the **source** cell (a physical velocity, so co-located; the opposite convention to the
  direction weighting, on purpose).
- `dt = C · dx / v_max` with Courant number `C = 1`. Recomputed every step (adaptive). Dry or flat grid →
  fallback 3,600 s. Exact property: `dt ∝ dx^(3/2)` (tested).
- In gauge-driven runs `dt` is also capped at **900 s** (the gauge's sampling interval): on a dry grid
  the fallback would otherwise inject an hour of river discharge into a few cells in one step. Even so the
  first step puts ~250 m of water into the 9 inflow cells at 30 m (a documented, bounded transient that
  decays to ~12–14 m after ~200 steps).
- `outflow_fraction_for_dt` scales the release down when `dt` is capped below the CFL bound. Correct and
  kept, but measured to have no effect on real runs (the cap rarely binds in the wet phase).
- *TCC I deprioritized adaptive time-stepping beyond CFL (Jahanbazi & Egger 2017); a recomputed CFL bound
  is consistent with that scope.*
- In the validated run (fig05) the first step uses the 900 s cap (dry grid); the inflow burst then drops
  `dt` to 0.2 s for a few steps, after which it settles at ~4.3 s (median over 5–65 h, low baseflow), falls
  to ~3.5 s as the flood rises (70–100 h) and to ~2.4 s near the peak (120–133.5 h). Overall median 3.8 s;
  134,639 steps cover 133.5 simulated hours. The flooded extent fills the channel (~430 cells) within the
  first ~3 h at baseflow and stays there until the rise begins at ~67 h.

### 7.6 Neighborhood option (von Neumann)
- `neighborhood="von_neumann"` (4 orthogonal neighbors) was added because TCC I names a neighborhood-type
  setting. Moore stays the default and the only validated one.
- The Moore path was proven **bit-identical** to the pre-change engine against a frozen copy (500 synthetic
  + 1,000 real steps; a reordering of the offsets alone fails at step 2 by 1.1e-16).
- Von Neumann is restricted to `outflow_fraction ≤ 0.085` because above that its result keeps changing as
  the substep fraction shrinks (not converged), measured with a time-matched convergence test (§10.6).

### 7.7 Backend-agnostic engine
The same functions run on CuPy (GPU) arrays: the array module is chosen from the input type, and CuPy is
imported only then. The NumPy path is bit-identical to before.

### 7.8 Seeded-pool mode
A synthetic 5×5 pool (default 400 units of summed depth, up to 10,000) at the lowest point or a clicked
location, in a closed system. Used for demonstration; every step asserts `|ΣH − V0| ≤ 1e-9 · V0`.

---

## 8. The fast mode (hybrid architecture)

### 8.1 Why it exists
After the runtime and accuracy work (§12), the project decided (§17) to keep the temporal CA as the core
model, since it is the differentiator vs. Torres et al. (it captures wave-front arrival), and to add a
separate, explicitly labeled **non-temporal** mode, so the speed/accuracy trade-off could be **measured
rather than asserted**.

### 8.2 Design (`simulation/fast_engine.py`)
*Inspired by* Torres et al. (2022) (top-down evaluation, Moore neighborhood, four states). Their rules are
paywalled, so the state rules are the project's own; it is never compared numerically with their paper.
- **Forcing:** the steady peak discharge (23,472 m³/s). No time, no `dt`. (A volume would just drain out
  of an open domain; conveyance is what sets extent for a through-flowing river.)
- **Routing surface:** the DEM re-filled by priority-flood from the outlet cells only (at steady state a
  depression on the flow path is full to its spill level). The first version, without this, retained 100%
  of the flow after 10 cells against a wall.
- **Routing pass:** top-down in that flood's order; each cell splits its discharge by `√S / n_dest` (the
  same weighting as the temporal engine).
- **States:** CONVEYING (carries discharge), EXITING (conveying cell that discharges through the outlet),
  INUNDATED (no flow of its own, but below the water surface of the conveying cell it drains to: a
  HAND-style lateral rule), DRY.
- **Invariant:** discharge continuity `outflow + retained = inflow` (exact on real grids: 23,472.37 m³/s
  out, 0 retained).

### 8.3 Two depth rules and why the second replaced the first
- **First rule (§19), "single cell":** Manning normal depth through a channel one cell wide,
  `h = (Q·n / (dx·√S))^(3/5)`. Pushing the whole river through 90 m-wide cells needs ~50 m of depth against
  a ~20 m real rise; the lateral rule then flooded high ground. Gap-corrected CSI 0.530 (547 false alarms).
  Its slope floor (`_MIN_SLOPE = 1e-4`) dominated the result; a disclosure sweep gave 0.49–0.76, but the
  better values only stood in for the missing width, so it was **not** tuned.
- **Second rule (§23), "cross section" (default):** a HAND synthetic rating curve per reach (Zheng et al.
  2018). Every cell draining to a reach belongs to its cross-section as a strip of width `dx²/L`; the stage
  `h` solves `Q = √S · Σ (1/n_k)(dx²/L)(h − HAND_k)^(5/3)` over wet cells (bisection), with `S` the
  least-squares fall of the channel over the reach. Reaches are at least **10 km** long: with whole-meter
  DEM heights and a ~1e-4 slope, shorter reaches fit DEM rounding, not the river; on this ROI's ~8.3 km of
  river that gives one reach. Result: gap-corrected **CSI 0.896**, untuned (fitted slope 1.02e-4 = 3 m over
  8.2 km; the slope floor no longer binds; shift noise floor +0.0000).
- **Disclosed:** the reach-length sweep (shorter lengths swing 0.76–0.84 with no plateau) was run before
  the 10 km constant was fixed. Two other ideas (connectivity-aware wetting, non-increasing downstream
  surface) were tried and dropped. A later calibration attempt (Manning's n multiplier, tilted surface)
  found no gain beyond noise (best +0.005, ~5 cells), so the untuned default stays: within this rule family
  the fast mode is at its ceiling for this event; better input data (finer vertical DEM resolution) would
  be needed.

---

## 9. Validation methodology

- **Scenario:** the real May 2024 event, from a dry grid at the record start (27 Apr 00:00) to the observed
  peak (133.5 h), real terrain, roughness, inflow and outlet. Temporal engine with Moore,
  `outflow_fraction = 0.085`, substep bound 0.01.
- **Flooded cell:** depth > **0.01 m** (a float-residue cutoff, the same in scripts and frontend).
- **Metrics** (from the confusion counts TP hits, FP false alarms, FN misses):
  `CSI = TP / (TP + FP + FN)`, `Hit Rate = TP / (TP + FN)`, `False Alarm Rate = FP / (TP + FP)`.
  Each raises an error when undefined rather than returning a placeholder.
- **Grid:** validated at **90 m**, a deliberate wall-clock trade-off (at 30 m a run to the peak takes
  ≈ 4.25 h even after all optimizations; §10.7). 60 m and 30 m scored as resolution checks (§10.7).
- **Gap-corrected ("Estrela-gap-only") scoring:** excludes the 2,280 Estrela-bank cells that the reference
  leaves dry at all three stage layers (§10.4). Both naive and corrected scores are always reported.
- **Noise floor ("shift search"):** shift the simulated mask by every offset in [−3, 3]² cells, take the
  best CSI; the gain shows how sensitive the score is to registration. A parameter effect smaller than this
  is not trusted. A naive top-3 spread of 0.0054 is the threshold used to call differences noise.
- **Reproducibility:** `python -m examples.validate_may2024 --outflow-fraction 0.085 [--resolution 60]` and
  `python -m examples.fast_mode_may2024 [--resolution 60]` (§17).

---

## 10. Results, in the order they were found

### 10.1 Synthetic proof of concept (steps 1–2)
50 × 50 grid, bowl + hill terrain, diagonal smooth "channel" in `N`, 5×5 pool of 400 units, 100 steps:
mass conserved to float64 round-off (errors ~1e-13 against an assertion tolerance of 1e-6, fig03), depth
never negative, the flood bends around the hill into a crescent (TCC I Fig. 11 behavior). An open-system
variant (inflow 2/step at one edge cell) grows by exactly 2 per step. The first real-terrain run (30 m, a
seeded pool in the river) conserved 400.0000 over 100 steps and followed the real channel.

### 10.2 First real-event score (step 10): CSI 0.133
At `outflow_fraction = 0.5`, 90 m, outlet on: 82,933 steps, 133.5 h simulated, 28.5 min wall-clock; exact
mass balance. Simulated 436 flooded cells (11.2%) against 831 observed (21.3%): **CSI 0.133, hit rate
0.179, false-alarm rate 0.658**. A narrow plume hugging the channel, much narrower than the real
floodplain. Reported as is, then investigated.

### 10.3 Investigation of the low score
**Ruled out, each with direct evidence:**
1. CRS/projection bug: simulated grid and reference mask are byte-identical in CRS, transform and shape.
2. Rasterization/indexing bug: exact pixel alignment; `all_touched` sensitivity ~10× too small.
3. Outlet drainage margin: swept `drop_m` ∈ {0.01, 0.5, 1, 2, 5, 10, 20} m (2,000× range): CSI
   0.13315–0.13411, spread **0.00096**; hit rate bit-identical in every run. A 1–3-cell shift of the mask
   alone moves CSI by +0.146, ~150× more. A clean negative result (fig11).
4. Stopping too early: the gauge-cell water surface was still rising monotonically over the last 20% of
   the run (five ~5.3 h windows), so the run is not cut off before its own peak. (The DEM-vs-gauge vertical
   datum is unresolved, so only relative water-surface dynamics are compared, never absolute stage.)
5. Dry initial condition: seeding a Manning baseflow depth (~0.15% of event inflow) washed out before the
   peak.
6. Depth threshold: false-positive and true-positive cells have indistinguishable depths (median ~9–10 m).

**The real lever: `outflow_fraction`.** The never-tuned 0.5 drains water toward the outlet too fast; slower
redistribution lets water spread laterally first. CSI is non-monotonic with a broad plateau at
[0.07, 0.10], peak **0.085** (13-point sweep; fig09). Lower values over-spread (at 0.05 the hit rate is 0.988
but the simulated extent is 57.7% of the ROI). The better-scoring values are also the *more* stable ones
(lowest checkerboard metric), and every swept depth field was visually smooth. At 0.085 the shift noise
floor is +0.0000.

| outflow_fraction | naive CSI | gap-corrected CSI | bundled CSI |
|---|---|---|---|
| 0.05 | 0.363 | 0.848 | 0.819 |
| 0.07 | 0.390 | 0.891 | 0.868 |
| **0.085** | **0.395** | **0.900** | 0.878 |
| 0.1 | 0.390 | 0.870 | 0.841 |
| 0.115 | 0.383 | 0.836 | 0.800 |
| 0.13 | 0.374 | 0.800 | 0.755 |
| 0.15 | 0.358 | 0.754 | 0.699 |
| 0.2 | 0.323 | 0.662 | 0.588 |
| 0.3 | 0.221 | 0.406 | 0.314 |
| 0.5 (old default) | 0.133 | 0.179 | 0.059 |
| 0.6 | 0.113 | 0.139 | 0.018 |
| 0.7 | 0.110 | 0.128 | 0.010 |
| 0.8 | 0.101 | 0.116 | 0.006 |

(All 13 swept points; same table as `docs/tcc-deviations.md` §16.3.) Adopted as the live default everywhere.

### 10.4 The reference-data gap (Estrela)
- At 0.085 the naive confusion counts are TP 789 / FP 1,166 / FN 42. The false positives form one large
  contiguous region, terrain-consistent with the true-positive band, on **Estrela's side**.
- **Stage-invariance test:** across the SGB layers at 19.00, 26.00 and 33.67 m, Lajeado's side grows
  normally (106 → 430 → 783 cells) while the same 48 cells on Estrela's side are flooded at every stage:
  that side is frozen at "permanent channel only".
- **Cause (external research):** the SGB system was commissioned for Lajeado, built from Lajeado's
  bathymetry and aerial photogrammetry and calibrated on Lajeado flood records 2007–2024. Estrela's terrain
  was only supporting input, never modeled as a target.
- **Correction:** exclude the **2,280** Estrela-bank cells that are dry in all three stage layers
  (bank = opposite side of the DEM channel from the gauge). FP drops from 1,166 to 47; TP and FN are
  untouched (an exclusion of reference-dry cells can only remove potential false positives).
- **Rejected alternatives:** (i) excluding stage-invariant cells domain-wide is degenerate: the SGB layers
  are nested, so "dry at all stages" = "dry at the peak", and FP becomes zero by construction (CSI = hit
  rate). (ii) A "bundled" correction that also removes permanent-channel cells removes real hits (68.8% of
  them are on Lajeado's side) and understates the result (0.878 vs. 0.900); reported for transparency only.
- **A labeling bug caught:** an early version swapped the Lajeado/Estrela labels; a double negation hid it
  in the numbers. It was audited cell by cell against an independent derivation before being trusted.
- **Independent corroboration:** a SWOT raster pass (6 May 2024, four days after the peak) shows
  Estrela-side water fraction of the same order as Lajeado's (mean 0.274 vs. 0.250; 18.9% vs. 15.1%
  classified wet). Mostly "suspect" quality (81.6%), off-peak, so used as supporting evidence only, not as a
  second metric.

### 10.5 The validated result (90 m, May 2024 peak)

| | naive (whole domain) | **gap-corrected** |
|---|---|---|
| TP / FP / FN | 789 / 1,166 / 42 | **789 / 47 / 42** |
| CSI | 0.395 | **0.899** (0.8986) |
| Hit rate | 0.949 | **0.949** |
| False-alarm rate | 0.596 | **0.056** |

- 134,639 steps; 1,955 flooded cells (50.1% of the grid, about half of them in the excluded zone); max
  depth 28.9 m; flooded depths p50 9.3 m, p90 17.7 m, p95 22.7 m.
- Wall-clock **7.6 min** with mass checks every step (6.9 min projected without checks); NumPy on a laptop
  CPU. Through the API with frames streamed: 7.4 min uncontended (longer when the machine was loaded).
- **0.8986 vs. 0.8997:** the documents quote both. They differ by one cell (FP 47 vs. 46); a run with the
  water depth perturbed by a single ulp gives exactly 0.8997, so this is floating-point noise (§12.10).
  Cite **0.899** (or 0.90).
- **Qualifier for the thesis:** CSI depends on the substep bound too (0.892 / 0.899 / 0.869 at 0.02 /
  0.01 / 0.005), and `outflow_fraction` was calibrated with the bound at 0.01. The validated result is
  the configuration "Moore, outflow_fraction 0.085, substep 0.01", not a converged-limit claim.
- **Where the residual errors are** (fig08d): a thin 1–2-cell fringe along the valley edges (misses) and
  around the outlet/Estrela (false alarms), on whole-meter terrain steps.

**Reproducibility check (TCC II figure session, 25 Oct 2026).** All four temporal scenarios were re-run
from scratch for the figures (`examples/tcc2_scenarios.py`) and reproduced the documented results
exactly: 90 m Moore 134,639 steps, 789/47/42, CSI 0.8986; 90 m von Neumann 133,245 steps, 830/277/1,
0.7491; 90 m baseline (0.5) 82,936 steps, naive 0.1333, gap-corrected 0.1789; 60 m Moore 232,908 steps,
1,700/62/181, 0.8749. The thesis can state that the results are reproducible from the public data with
the published scripts.

### 10.6 Moore vs. von Neumann (same event, 90 m, 0.085)

| | Moore (validated) | von Neumann |
|---|---|---|
| steps to the peak | 134,639 | 133,245 |
| flooded cells | 1,955 | 2,583 |
| gap-corrected TP / FP / FN | 789 / 47 / 42 | 830 / 277 / 1 |
| gap-corrected CSI | **0.899** | 0.749 |
| water held at the peak | 19,097 | 41,034 (2.15×) |
| WSE at the gauge cell (observed stage 33.66 m) | 36.4 m | 46.8 m |
| wall-clock, side by side | 7.41 min | 4.48 min (0.60×) |

Von Neumann's extent is a strict superset of Moore's (628 extra cells, a coherent 1–3-cell rim up the valley
sides, i.e. a higher water level, not speckle). Likely cause: the Taquari runs diagonally (NE → SW) across
the grid; with only orthogonal moves water staircases along the channel, conveys less, and the stage
rises. This is TCC I's own reason for weighting diagonal distances. Von Neumann is not calibrated (its
`outflow_fraction` was tuned for Moore) and is labeled "not validated" in the app. Isotropy: the
von Neumann front is diamond-like (fill 0.65) and Moore's octagon-like (0.87), while the developed bulk is
near-round under both.

### 10.7 Resolution check: 60 m, nothing re-tuned

| | temporal 90 m | temporal 60 m | fast 90 m | fast 60 m |
|---|---|---|---|---|
| gap-corrected TP / FP / FN | 789 / 47 / 42 | 1,700 / 62 / 181 | 800 / 62 / 31 | 1,708 / 60 / 173 |
| **gap-corrected CSI** | **0.899** | **0.875** | **0.896** | **0.880** |
| hit rate / FAR | 0.949 / 0.056 | 0.904 / 0.035 | 0.963 / 0.072 | 0.908 / 0.034 |
| naive CSI | 0.395 | 0.393 | 0.390 | 0.396 |
| steps / time | 134,639 | 232,908 (1.73×) | 73 ms | 168 ms |

The calibration transfers (an out-of-sample check, not a second calibration). The small loss is recall
(misses on the valley-edge fringe); false alarms stay flat. Temporal and fast agree at CSI 0.948 at 60 m.
The step ratio 1.73× is close to the CFL expectation (90/60)^1.5 = 1.84×.

**30 m (TCC I's own resolution), same defaults, nothing re-tuned** (deviations §26):

| | temporal 90 m | temporal 60 m | temporal 30 m | fast 30 m |
|---|---|---|---|---|
| gap-corrected TP / FP / FN | 789 / 47 / 42 | 1,700 / 62 / 181 | 6,681 / 246 / 838 | 6,983 / 360 / 536 |
| **gap-corrected CSI** | **0.899** | **0.875** | **0.860** | **0.886** |
| hit rate / FAR | 0.949 / 0.056 | 0.904 / 0.035 | 0.889 / 0.036 | 0.929 / 0.049 |
| naive TP / FP / FN | 789 / 1,166 / 42 | 1,700 / 2,448 / 181 | 6,681 / 9,856 / 838 | 6,983 / 10,060 / 536 |
| naive CSI | 0.395 | 0.393 | 0.385 | 0.397 |
| naive hit rate / FAR | 0.949 / 0.596 | 0.904 / 0.590 | 0.889 / 0.596 | 0.929 / 0.590 |
| steps / time to the peak | 134,639 / 7.6 min | 232,908 / 20.7 min* | 556,774 (2.39× 60 m) / ≈ 4.25 h | 658 ms |

Naive scoring is the whole grid, nothing excluded, at the May 2024 peak, against the SGB/CPRM reference at
the 33.67 m stage, flooded = depth > 0.01 m. TP and FN are the same under both scorings, because no
observed-flooded cell lies in the Estrela gap. Only the false alarms change: the cells the model floods
inside the gap (9,610 temporal, 9,700 fast at 30 m) count as FP in the naive score.

*Times:* 90 m 7.6 min is a measured full run with no throttling (deviations §18). 30 m ≈ 4.25 h is the
real run's own step count at its own rate once throttling was off (556,774 × 27.5 ms). The run took 281 min
in total, of which the first ~35 min (~20,000 steps, ~100 ms per step) were slowed by Windows power
throttling. \*60 m has **no clean measured run**. 20.7 min is a projection, 232,908 measured steps × the
5.33 ms benchmark macro-step median (deviations §25). The only full 60 m timings are 23.8 min (§24, run
side by side with a 90 m run, so contended) and 85.8 min (the figure-session cache, most likely
throttled). Projections from benchmark medians run ~10% below measured runs (90 m: 6.9 vs. 7.6 min), so
20.7 min is probably slightly low.

The same pattern continues: a small, monotone loss in recall (FN on the valley-edge fringe) with false
alarms flat, a gap-corrected shift noise floor of +0.0000 (±270 m), exact mass balance at every one of
the 556,774 steps, and the smoothest depth field of the three grids. The fast mode scores above the
temporal engine at 60 m and 30 m (it was just below at 90 m); the two 30 m extents agree at CSI 0.931.
The validated figure stays the 90 m one (where `outflow_fraction` was calibrated); 60 m and 30 m are its
out-of-sample resolution checks. The 30 m run to the peak takes ≈ 4.25 h unthrottled (see *Times* above;
≈ 3.3 h on the §25 benchmark median of 21.6 ms per macro step). Figures: fig15_resolucao_60_30m (temporal
CA at 60 m and 30 m), fig17 (both 30 m points).

### 10.8 Temporal vs. fast (90 m, same moment)

| | fast, single cell (§19) | **fast, cross section** | temporal (0.085) |
|---|---|---|---|
| naive TP / FP / FN | 731 / 2,109 / 100 | 800 / 1,223 / 31 | 789 / 1,166 / 42 |
| naive CSI | 0.249 | 0.390 | 0.395 |
| gap-corrected TP / FP / FN | 731 / 547 / 100 | 800 / 62 / 31 | 789 / 47 / 42 |
| **gap-corrected CSI** | 0.530 | **0.896** | **0.899** |
| hit rate / FAR | 0.880 / 0.428 | 0.963 / 0.072 | 0.949 / 0.056 |
| flooded depth median / p95 | 33.5 / 54.7 m | 10.0 / 24.0 m | 9.3 / 22.7 m |
| time to a final extent | ~74 ms | ~73 ms | 7.6 min |

The two engines also agree closely with **each other**: at the 90 m peak the temporal and cross-section
fast extents match at CSI **0.961** (1,949 cells flooded in both, 6 temporal only, 74 fast only; fig13;
computed in the TCC II figure session). The older 1,648 / 307 / 1,192 split quoted in §21 is against the
first, single-cell fast rule and is superseded. At 60 m the agreement is 0.948 (§10.7).

The fast mode reaches essentially the same extent accuracy about **6,000× faster**. What it cannot give is
time: no arrival times, no hydrograph-driven evolution, no recession. That is the temporal engine's
distinct contribution and the reason the architecture keeps both. Depth is not validated for either engine
(no observations), so the app draws the fast result as extent only.

### 10.9 Performance (step 11; i7-13620H CPU, RTX 4050 Laptop GPU, float64)

**Fairness rule:** each alternative implementation was first proven **bit-identical** to the live engine
(`np.array_equal`), then timed. Negative controls confirmed the tests catch a reordered sum or a fused
multiply-add.

*Vectorized NumPy vs. plain Python loops* (`step()` medians, 9 substeps):

| grid | cells | loops (ms) | NumPy (ms) | speedup |
|---|---|---|---|---|
| synthetic 32² | 1,024 | 38.9 | 1.46 | 27× |
| synthetic 128² | 16,384 | 650 | 8.49 | 77× |
| synthetic 256² | 65,536 | 2,744 | 56.7 | 48× |
| **real 90 m** | 3,904 | 155 | 2.83 | **55×** |
| **real 60 m** | 8,736 | 354 | 5.03 | **71×** |
| **real 30 m** | 35,136 | 1,460 | 20.1 | **72×** |

Loops cost a flat ~40 µs per cell per step. NumPy's cost per cell is lowest in the 4k–35k range (where the
real grids are); it rises on very small grids (fixed call overhead) and on very large ones (consistent with
exceeding the CPU's L3 cache; not profiled).

*Scaling with grid size* (`step()` ms): NumPy 2.83 / 5.03 / 20.1 at 90/60/30 m, linear from ~16k cells;
plain CuPy flat at ~16 ms up to 262k cells (kernel-launch-bound: ~80 small kernels per substep), 18–26×
faster than NumPy at ≥ 1M cells; **fused CuPy** (2 CUDA kernels per substep) 1.52 / 1.83 / 4.02 ms on the
real grids = **1.9× / 2.7× / 5.0× faster than NumPy**, up to 14× faster than plain CuPy.

*Memory:* model arrays 40 B/cell; NumPy `step()` transient peak ~170 B/cell (0.67 MB at 90 m, 5.7 MB at
30 m); loops ~3× more; memory is not a constraint at any size used.

*Scaling with iterations* (NumPy, full macro steps): 90 m 0.32 s per 100 steps → 32.2 s per 10,000;
linear within 1% per decade; memory flat over 10,000 steps.

*Projected time to the May 2024 peak (NumPy, from benchmark medians):* 90 m **6.9 min**, 60 m **20.7 min**,
30 m **≈ 3.3 h** (556,774 measured steps × 21.6 ms; the first projection, ~4.0 h, assumed 659k steps).
Measured full runs come out somewhat slower: 90 m 7.6 min, 30 m ≈ 4.25 h at the run's own unthrottled rate
(§10.7).

*Fused GPU on the real event (90 m):* same outcome as NumPy (134,634 vs. 134,639 steps, 1,955 cells, CSI
0.395 naive), 6.72 vs. 7.22 min in the same session = only **1.07×** end to end, because the still-unfused
`compute_stable_dt` and per-step synchronizations now dominate. A fused `dt` reduction is the next GPU
lever (not attempted). The live API runs NumPy.

*Calibration as a performance win:* moving 0.5 → 0.085 made the 90 m run **3.1× faster** (23.3 → 7.6
min): each step needs 9 substeps instead of 50 (~5× cheaper), partly offset by 1.62× more steps (slower
redistribution holds more water, velocities rise, CFL `dt` shrinks).

*Earlier performance attempts that failed (negative results):* stacking the 8 directions into one
`(8, rows, cols)` array made runs 2.6× *slower* (copy cost); relaxing the substep bound to 0.02 gave 1.85×
but created a visible artifact on real terrain; dt-ratio scaling had no measurable effect.

### 10.10 Comparison with the performance class TCC I cites
TCC I cites CA models running in seconds against hours for hydrodynamic models (Jamali et al. 250–1,100×;
Torres et al. ~1 s vs. 2,012 s). The fast mode (~0.07 s at 90 m) is in that class. The temporal CA takes
minutes at 90 m and hours at 30 m for a 5.6-day event, which is slower than the non-temporal models but
produces the full time evolution. The project did **not** run HEC-RAS on the same area, so no direct
speedup factor against a hydrodynamic model can be claimed; the SGB reference itself is a HEC-RAS 2D
product, but its run time is unknown.

---

## 11. Development difficulties and lessons (for the methodology/discussion chapters)

- **Checkerboard instability (step 1):** diagnosed with controls, fixed with substeps (§7.2).
- **Bare-slope transcription error (step 1 → 2):** caught by re-reading the equation when adding Manning.
- **Hydrology libraries unusable on Python 3.14:** priority-flood written by hand.
- **Reprojection corner slivers:** found by inspecting the raster.
- **Flood overlay invisible against the basemap, twice:** a blue ramp vanished on OSM's blue river; later
  the whole basemap competed. Final design: a 6-band blue ramp checked for ≥ 2:1 contrast against OSM
  water, an orange extent color for the fast mode, a relief basemap. Only visible in a browser.
- **Docker-only failures:** missing `libexpat1` for rasterio's wheel; the backend container could not see
  `data/`. Neither caught by tests.
- **Wrong ANA operation returned the wrong data shape silently.** Found by reading the WSDL.
- **Wrong inflow edge from a heuristic;** caught by whole-branch review against the DEM; the heuristic also
  misfires at 60 m.
- **Absolute tolerance broke at real scale:** cumulative inflow reaches ~1e7, so conservation checks became
  relative.
- **First-step inflow burst:** bounded by the 900 s cap.
- **WebSocket closed before accept** (unknown run): only visible through `onclose`, handled explicitly.
- **Closed boundary meeting a real event:** whole-domain flooding → outlet (§7.4).
- **The performance wall:** a 30 m full-event run was estimated at 45–49 h at the old settings; "simulate
  only to the peak" turned out not to save proportionally (the rising limb is the expensive part). Resolved
  by validating at 90 m, calibration (3.1×), and measurement.
- **A "should be faster" vectorization made it 2.6× slower:** measure, don't assume.
- **Synthetic tests are not enough:** a change passing both synthetic stability tests produced a visible
  artifact on real terrain; real-terrain checks became mandatory.
- **Step-matched snapshots compare different simulated times** when runs have different `dt` histories;
  convergence must be judged at matched times (found in the von Neumann work).
- **Single-ulp amplification:** the engine turns one ulp into ~0.2 m within ~50 steps (weights use `√S`,
  whose derivative is infinite at zero slope; on near-flat water an ulp-scale drop redirects a cell's whole
  release). Consequence: compare implementations bit for bit, compare runs across machines/backends on
  outcomes (extent, CSI, step count), and treat 0.8986 vs. 0.8997 as noise.
- **Frontend bugs only a browser found:** Stop button turned into submit mid-click and restarted the run;
  React 19 dev-mode performance tracks exhausted memory after ~1,200 frames by diffing typed arrays (fixed
  with a private class field); a 2-cell misplacement from linear lat/lon interpolation over a rotated grid
  (fixed by using the real UTM transform for seeding).
- **A file-name collision** silently overwrote the 90 m validation mask with a 30 m one; fixed with separate
  paths.

---

## 12. Limitations (state these in the thesis)

1. **One event, one small area.** Validation covers the May 2024 peak on a ~6 km box. September 2023 was not
   validated. Generalization to other reaches or events is not demonstrated.
2. **Reference data.** The SGB/CPRM extent is itself a HEC-RAS 2D model product, not an observation, and it
   does not cover Estrela's bank (gap correction required). SWOT only corroborates.
3. **Calibration on the validation event.** `outflow_fraction` was calibrated on the same event it is
   scored on (90 m). The 60 m score is an out-of-sample *resolution* check, not an independent event.
4. **Resolution.** Validated at 90 m and checked at 60 m and 30 m (TCC I's resolution), with the same
   calibration: gap-corrected CSI 0.899 → 0.875 → 0.860 (temporal). The 30 m run takes ≈ 4.25 h, so it is
   a one-off check, not the working validation grid. Long runs on the development laptop (Windows 11) must
   not be power-throttled: a windowless background process ran ~3.7× slower (~100 ms per step) until
   throttling was disabled for it (deviations §26). No clean full 60 m run was timed (§10.7).
5. **No depth validation.** No usable high-water-mark dataset exists for the ROI (only a PDF report), so
   RMSE was not computed; SWOT gives water fraction, not depth. Depths are therefore not validated, and the
   DEM-to-gauge vertical datum is unresolved.
6. **DEM limitations.** SRTM (~2000) with whole-meter vertical steps; no bathymetry; urban structures not
   represented; land cover is 2024 (vintage mismatch).
7. **Model simplifications.** Storage-cell redistribution with an empirical `outflow_fraction` (not a
   momentum equation); Manning roughness steers direction only; boundary inflow concentrated in a few
   channel cells; a fixed-margin outlet; no rain, no infiltration; cell-state optimization not implemented.
8. **Fast mode:** steady state only; one reach on this ROI; no backwater dynamics (which appear as its
   errors near the outlet in the first rule).
9. **Von Neumann** is available but not validated or calibrated.
10. **Performance:** measured on one laptop; GPU end-to-end gain limited (1.07×) until `dt` is fused.

---

## 13. TCC I → TCC II deviations (what changed and why)

| Topic | TCC I said | TCC II did | Why |
|---|---|---|---|
| Work order | Infra first (Docker/WebSocket), algorithm mid-schedule | Algorithm first on synthetic grids, then data, API, UI, Docker | Front-load the highest academic risk |
| Transition rule | Manning `Q_i`, Moore, normalized | Same, plus `outflow_fraction` cap and substeps | Stability of the explicit synchronous update |
| Roughness | `n_i` in `Q_i` | `√S / n_dest`, direction only | `h^(5/3)` cancels; which cell's `n` was unspecified |
| Cell states | Inactive/Transport/Accumulation | Not implemented | Dense vectorized update already fast at these sizes |
| DEM source | SRTM/TOPODATA | SRTMGL1 via OpenTopography API | Scriptable, reproducible; same data class |
| Preprocessing | Clip + sink fill | + reprojection to UTM, corner crop, hand-written priority-flood | Square metric cells; library failed on Python 3.14 |
| Roughness table | "static dictionary" | NRCS/Chow cross-walk for 13 classes, 2024, nearest-neighbor | MapBiomas has no n table; categorical data |
| Timestep | Not a step; adaptive-beyond-CFL deprioritized | `compute_stable_dt` (CFL, recomputed every step) | Needed to map a real hydrograph onto steps; consistent with the deprioritization |
| Closed system | The base invariant | Optional inflow and outlet; exact open-system invariants | A real event is continuously driven; walls flooded the whole ROI |
| Gauge data | Validation only | Drives the model (inflow); validation uses SGB extents | Only way to represent the real event; not circular |
| Stage → discharge | (implied external curve) | ANA's own `Vazao` pairs as an empirical curve | Better grounded than an external table |
| Validation | CSI + RMSE, 2023 and 2024 | CSI/HR/FAR on May 2024; RMSE closed | No HWM dataset; reference gap needed a documented correction |
| Resolution | ~30 m | Validated 90 m, checked at 60 m and 30 m | Wall-clock (30 m run ≈ 4.25 h) |
| Frames | base64 PNG over WebSocket | JSON numeric arrays, rendered client-side | Simpler, testable; client canvas made PNG unnecessary |
| Persist H[t] | Yes | No (frames buffered client-side; examples save results) | Not needed for the validation as done |
| Config panel | Initial stage, rainfall/volume, neighborhood | Mode (seeded pool / gauge-driven / fast), grid, neighborhood, seed volume/location, engine tuning | Stage replaced by the real hydrograph; rain deferred to the advisor |
| Neighborhood | Moore; UI toggle named | Moore validated; von Neumann optional, unvalidated, capped | Implemented the named toggle without claiming validation |
| Basemap | OpenStreetMap | OSM, then Esri gray, back to OSM; final default "Relief" with alternatives | Overlay contrast |
| Architecture | One temporal model | Hybrid: temporal CA + Torres-inspired fast mode | Measure the speed/accuracy trade-off |
| Testing | Informal PoC prints | 198 pytest + 6 Playwright tests, invariants at every step | Methodological upgrade |
| GPU | CuPy-compatible, exploratory | Backend-agnostic engine; plain and fused CuPy measured | Answered the TCC I question with numbers |

---

## 14. Answering the research question (material for the conclusion)

- A software architecture with a **pure, dependency-free CA engine** wrapped by an ingestion layer
  (public data → arrays), a validation layer, an API and a web client made it possible to go from public
  data (SRTM, MapBiomas, ANA, SGB) to a validated flood extent for a real event in minutes on a laptop.
- The **time-stepped** CA reproduces the May 2024 peak extent with CSI 0.899 (gap-corrected; hit rate
  0.949, false-alarm rate 0.056) at 90 m in ~7 min, and additionally gives the evolution over time
  (arrival times, depth envelopes).
- A **non-temporal** mode in the same architecture reaches CSI 0.896 in ~0.07 s, which is the speed class
  TCC I's literature reports, at the cost of having no time dimension.
- The architecture decisions (engine without I/O, backend-agnostic arrays, exact invariants, bit-identity
  tests) are what made the investigation possible: the low first score was traced to a reference-data gap
  and one parameter, instead of being tuned away.
- Limits: one event, extent only, coarse resolution (§12).

---

## 15. Suggested TCC II structure and where each item goes

(Adapt to Univates' template; TCC I's chapters 1–4 can be revised and reused.)
1. **Introdução**: motivation, problem, question, objectives (§1); short statement of results.
2. **Referencial teórico** (from TCC I, updated): CA and macroscopic CA, storage-cell models, Manning,
   CFL condition (new: needed for §7.5), HAND/rating curves (new: §8.3), priority-flood sink filling,
   validation metrics (CSI/HR/FAR), related work (add Zheng et al. 2018; position Torres et al. vs. the fast
   mode).
3. **Metodologia**: incremental development process and verification practices (§3); study area and data
   (§5, §6); validation design (§9); performance experiment design (§10.9 fairness rule).
4. **Desenvolvimento / Implementação**: architecture (§4); temporal engine (§7); fast mode (§8); API and
   frontend (§4.4–4.5); Docker; deviations from TCC I (§13).
5. **Resultados**: PoC (§10.1); first score and investigation (§10.2–10.4); validated result (§10.5);
   neighborhoods (§10.6); resolution (§10.7); temporal vs. fast (§10.8); performance (§10.9). Figures
   fig03–fig17.
6. **Discussão**: what the investigation shows (reference-data quality as the dominant factor; noise
   floor), speed vs. accuracy (§10.10), lessons (§11), limitations (§12).
7. **Conclusão e trabalhos futuros** (§14, §20).

---

## 16. Figures (in `docs/tcc2/figures/`, generated by `backend/examples/tcc2_figures.py`)

Captions in Portuguese, ready to adapt. "Fonte: elaborado pelo autor" applies to all; data sources are named
in each caption. Figures marked † are plotted from measured values quoted from `docs/tcc-deviations.md`
(sweeps and benchmarks that take hours to re-run); all others are computed from the data when the script
runs.

| File | Caption (pt-BR) | Notes |
|---|---|---|
| fig01_area_estudo | Área de estudo: trecho do rio Taquari entre Lajeado e Estrela (RS), MDE SRTMGL1 reprojetado para SIRGAS 2000/UTM 22S com 30 m de resolução, células de entrada (borda norte), exutório (borda sul) e estação fluviométrica 86879300 da ANA. | Grid 183×192 |
| fig02_cobertura_rugosidade | (a) Cobertura e uso da terra do MapBiomas Coleção 10 (2024) e (b) matriz de rugosidade de Manning derivada por classe. | Table in §6.2 |
| fig03_poc_sintetico | Prova de conceito em grade sintética: terreno, rugosidade, lâmina d'água nos passos 5 e 50 e erro de conservação de massa nos sistemas fechado e aberto. | Errors ~1e-13 |
| fig04_hidrograma | (a) Cota e vazão da estação 86879300 (Porto Fluvial de Estrela) entre 27/04 e 10/05/2024 e (b) curva-chave da estação, com os 288 pares cota–vazão da própria ANA; abaixo de 14,11 m, a vazão é mantida fixa. | Peak 33.66 m, 02/05 13:30 |
| fig05_passo_tempo_balanco | Passo de tempo adaptativo (CFL), balanço hídrico (entrada, saída pelo exutório e volume armazenado) e extensão inundada ao longo da simulação de maio de 2024 (90 m). | Validated run |
| fig06_sequencia_inundacao | Evolução temporal da inundação simulada pelo AC temporal (vizinhança de Moore, 90 m) de 24 h até o pico (133,5 h). | Depth bands as in the app |
| fig07_tempo_chegada_profundidade_max | (a) Tempo de chegada da água e (b) profundidade máxima simulada até o pico, AC temporal (90 m). | Only the temporal engine can produce (a) |
| fig08_validacao_90m | Validação no pico de maio de 2024 (90 m): (a) referência SGB/CPRM na cota 33,67 m e lacuna de cobertura em Estrela, (b) profundidade simulada, (c) matriz de confusão ingênua e (d) com a lacuna excluída. | CSI 0.395 / 0.899 |
| fig09_calibracao_outflow † | CSI em função da fração de liberação por passo (outflow_fraction), nas avaliações ingênua, com lacuna excluída e agregada. | §16.3. "Valor adotado (CSI 0,900)" is the sweep run at 0.085 (789 / 46 / 42 = 0.8997); the validated rerun scores 0.899 (789 / 47 / 42). One FP cell apart: ulp-level noise (deviations §22) |
| fig09_calibracao_ingenuo † | CSI em função da fração de liberação por passo, no pico de maio de 2024 (grade de 90 m) | **Fora do texto.** Avaliação ingênua; usada na Seção 5.2 |
| fig10_primeiro_resultado | Acertos, omissões e falsos alarmes da primeira simulação no pico de maio de 2024 (grade de 90 m, fração de liberação por passo de 0,5) | **Fora do texto.** Avaliação ingênua; substitui a antiga comparação antes/depois da calibração |
| fig11_margem_exutorio † | Sensibilidade do CSI à margem de descida do exutório comparada ao ganho obtido apenas por deslocamento da máscara (resultado negativo). | §15 |
| fig12_modo_rapido | Modo rápido (não temporal): (a) estados das células, (b) primeira regra de profundidade (canal de uma célula) e (c) curva-chave HAND por seção transversal. | 0.530 → 0.896 |
| fig13_temporal_vs_rapido | Comparação entre as extensões do AC temporal e do modo rápido no pico (90 m). | Agreement CSI 0.961 (1,949 / 6 / 74) |
| fig14_moore_vs_vonneumann | Vizinhança de von Neumann (90 m): (a) acertos, omissões e falsos alarmes com a lacuna de Estrela excluída; (b) diferença de extensão em relação à vizinhança de Moore. | 0.749 (von Neumann) vs. 0.899 (Moore); 1,955 / 628 / 0 |
| fig15_resolucao_60_30m | Acertos, omissões e falsos alarmes do AC temporal no pico de maio de 2024, com a lacuna de Estrela excluída e sem recalibração: (a) grade de 60 m; (b) grade de 30 m. | 60 m: 1,700 / 62 / 181 (CSI 0.875); 30 m: 6,681 / 246 / 838 (CSI 0.860). Replaces the older fig15_resolucao (90/60 m) and fig15_resolucao_60m |
| fig16_desempenho † | Desempenho: (a) tempo por passo × tamanho da grade para laços em Python, NumPy (CPU), CuPy (GPU) e CuPy fundido (GPU); (b) tempo de execução × número de passos simulados nas grades de 90, 60 e 30 m. | §25. A aceleração do NumPy sobre os laços fica em tabela no texto (§10.9) |
| fig17_velocidade_precisao | Precisão (CSI com lacuna excluída) versus tempo de execução para todas as configurações avaliadas. | CSI computed from the caches and fast runs. Temporal times are the documented unthrottled ones: §18, §22, §25 (60 m: a projection, §10.7), and 30 m ≈ 4.25 h (§26). Fast times are the documented medians (§19, §23, §24, §26: 0.074, 0.073, 0.168, 0.658 s), not re-measured |

Also useful for the thesis but not generated here: **screenshots of the web application** (Setup tab,
Compare view after the "Replay May 2024 flood" preset, Observed layer with live CSI, timeline, cell
inspector, About page). Take them from the running app (`docker compose up`, open `http://localhost:5173`)
or with the app's PNG export.

---

## 17. Reproducing everything

From `backend/` with the venv (first time: `python -m venv .venv`, `pip install -r requirements.txt`; the
DEM download needs a free `OPENTOPOGRAPHY_API_KEY` in `backend/.env`):
```
python -m scripts.download_dem
python -m scripts.download_landcover
python -m scripts.download_hydrograph
python -m scripts.download_flood_extent
python -m examples.poc_grid                                   # synthetic PoC
python -m examples.validate_may2024 --outflow-fraction 0.085  # validated temporal result (~8 min)
python -m examples.fast_mode_may2024                          # fast mode (seconds)
python -m examples.validate_may2024 --outflow-fraction 0.085 --resolution 60
python -m examples.benchmark_scaling --backends numpy loops --iterations 10 100 1000 10000 --plot scaling.png
python -m examples.tcc2_scenarios                             # caches the runs the figures need (~1 h)
python -m examples.tcc2_figures                               # writes docs/tcc2/figures/*.png
pytest tests/                                                 # 198 tests
```
App: `docker compose up --build` at the repo root → frontend on `http://localhost:5173`, API on
`http://localhost:8000`. Browser smoke tests: `npm run test:e2e` in `frontend/`.

---

## 18. References used by the project

Fill missing fields from the actual sources before citing (marked "to complete").
- BARNES, R.; LEHMAN, C.; MULLA, D. Priority-flood: an optimal depression-filling and watershed-labeling
  algorithm for digital elevation models. *Computers & Geosciences*, v. 62, p. 117–127, 2014.
- CHOW, V. T. *Open-Channel Hydraulics*. New York: McGraw-Hill, 1959.
- TORRES, C.; CHÁVEZ-CIFUENTES, J. F.; REINOSO, E. A conceptual flood model based on cellular automata for
  probabilistic risk applications. *Environmental Modelling & Software*, v. 157, 105530, 2022.
- ZHENG, X. et al. River channel geometry and rating curve estimation using height above the nearest
  drainage. *Journal of the American Water Resources Association*, 2018 (volume/pages to complete).
- USDA NRCS (Kansas). Manning's n values by NLCD land cover, as adopted for HEC-RAS 2D modeling (exact title
  and year to complete); US ARMY CORPS OF ENGINEERS. *HEC-RAS 2D Modeling User's Manual* (version/year to
  complete).
- MAPBIOMAS. Coleção 10 da série anual de mapas de cobertura e uso da terra do Brasil (1985–2024).
  Accessed via public Google Cloud Storage COG.
- FARR, T. G. et al. The Shuttle Radar Topography Mission. *Reviews of Geophysics*, 2007 (standard SRTM
  citation; confirm). Data via OpenTopography (SRTMGL1).
- ANA – Agência Nacional de Águas e Saneamento Básico. Telemetria, estação 86879300 (Porto Fluvial de
  Estrela), serviço `DadosHidrometeorologicos`, 27/04–10/05/2024.
- SGB/CPRM – Serviço Geológico do Brasil. Sistema de alerta de cheias de Lajeado, manchas de inundação por
  cota (MapServer LAJEADO, camada COTA_3367cm), developed with IPH-UFRGS.
- CPRM. Nota técnica: levantamento das cheias de 2024 no RS (`nota_tecnica_levantamento_cheias_2024_rs.pdf`)
  (details to complete).
- NASA/CNES SWOT Level-2 raster product, pass 014/533, 6 May 2024.
- SIMOES-SOUSA, I. et al., 2025, *Geophysical Research Letters* (SWOT and the 2024 RS floods; public Zenodo
  dataset) (details to complete); LAIPELT, L. et al., 2025, *Geophysical Research Letters* (co-authored
  with W. Collischonn and A. Ruhoff, IPH-UFRGS) (details to complete).
- From TCC I's review (full references are in TCC I): Liu et al. 2015; Jahanbazi & Egger 2017; Jamali et al.
  2019 (CA-ffé); Tavakolifar et al. 2021 (SWMM-2DCA); Monte et al. 2016; Sales et al. 2025.
- Software: NumPy, CuPy, rasterio/GDAL, FastAPI, React, Vite, Leaflet, Docker, pytest, Playwright.

---

## 19. Glossary (code/English → thesis/Portuguese)

| English / code | Portuguese |
|---|---|
| cellular automaton (CA), macroscopic CA | autômato celular (AC), AC macroscópico |
| Moore / von Neumann neighborhood | vizinhança de Moore / de von Neumann |
| water surface elevation (WSE) | cota da superfície da água |
| water depth `H`, terrain elevation `Z` | lâmina d'água, cota do terreno |
| Manning's roughness coefficient `n` | coeficiente de rugosidade de Manning |
| transition rule | regra de transição |
| `outflow_fraction` | fração de liberação por passo (taxa de redistribuição interna) |
| substep | subpasso |
| mass conservation | conservação de massa |
| boundary inflow / outlet | vazão de entrada na fronteira / exutório |
| time step `dt`, CFL condition, Courant number | passo de tempo, condição CFL, número de Courant |
| hydrograph, stage, discharge, rating curve | hidrograma, cota, vazão, curva-chave |
| DEM, sink filling | modelo digital de elevação (MDE), preenchimento de depressões |
| land cover | cobertura e uso da terra |
| flood extent | extensão (mancha) de inundação |
| hit / miss / false alarm | acerto / omissão / falso alarme |
| Critical Success Index (CSI), hit rate, false-alarm rate | índice crítico de sucesso, taxa de acerto, taxa de falso alarme |
| coverage gap (Estrela) | lacuna de cobertura da referência (Estrela) |
| noise floor, shift search | piso de ruído, busca por deslocamento |
| fast mode (non-temporal) | modo rápido (não temporal) |
| HAND (height above nearest drainage) | altura acima da drenagem mais próxima (HAND) |
| seeded pool | piscina inicial (cenário sintético) |
| gauge-driven | dirigido pelo hidrograma observado |
| bit-identical | idêntico bit a bit |
| ulp (unit in the last place) | ulp (unidade na última casa do ponto flutuante) |
| wall-clock time | tempo de execução (tempo de parede) |

---

## 20. Future work (already identified)

- Validate other events (September 2023) and a wider ROI along the Taquari; independent reference data
  covering Estrela.
- Use a finer DEM (e.g. LiDAR/ANADEM) with sub-meter vertical resolution, which would sharpen both
  engines' edges and slopes (the 30 m grid is now scored; its losses are on the valley-edge fringe).
- Depth validation if a structured high-water-mark dataset becomes available (RMSE).
- Rain and infiltration source terms (a change to the documented base model, to be discussed with the
  advisor; the engine's `inflow` term already supports it).
- Fuse `compute_stable_dt` into a GPU kernel so the fused substep's 2–5× speedup reaches end to end; consider
  running the API on GPU.
- Calibrate von Neumann separately; relate `outflow_fraction` to a physical discharge rate.
- Use the fast mode for many-scenario (probabilistic) runs, which is what Torres et al.'s method targets.
- Persist runs (frames, `H[t]`) if the app is used operationally.
