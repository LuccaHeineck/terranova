# TCC1 Summary — Modelagem e Simulação de Inundações no Vale do Taquari Baseada em Autômatos Celulares

Condensed reference extracted from `TCC1LuccaHeineck.pdf` (69 pages, TCC I, Univates, Engenharia de Software, submitted by Lucca Coutinho Heineck, advisor Prof. Me. Edson Moacir Ahlert, Lajeado, June 2026). TCC I is the proposal/literature-review phase; TCC II (in progress) is the actual implementation. Read this instead of re-reading the full PDF; go back to the PDF only if a detail here is insufficient.

## Motivation and problem

The Vale do Taquari (Rio Taquari-Antas basin, RS, Brazil — ~26,430 km², 119 municipalities, main contributor to the Guaíba basin) suffered unprecedented floods in September 2023 and May 2024, exceeding the historical 1941 flood record. In the May 2024 event the river at Lajeado/Estrela rose from 13.00 m to 33.66 m in 72 hours. Traditional hydrodynamic models (solving Shallow Water Equations, e.g. HEC-RAS 2D) are accurate but computationally expensive, limiting their use for fast, repeated, emergency-response scenarios. The TCC's research question: **how can a software architecture based on macroscopic cellular automata enable agile modeling/simulation of flood extents, using public topographic data for the Vale do Taquari?**

## Objectives

General: develop and evaluate an efficient, representative CA-based flood simulation model for the Vale do Taquari.
Specific: (a) prepare DEM + historical flood data, (b) design/implement the simulator and its transition rules, (c) validate accuracy against real 2023/2024 flood maps, (d) evaluate computational performance for rapid-response viability.

## Cellular automata theory

- Classic CA (e.g. Conway's Game of Life): discrete grid, finite states, local transition rules applied in parallel. Neighborhoods: **von Neumann** (4 cardinal neighbors) and **Moore** (8 surrounding neighbors) — this project uses **Moore**.
- This project uses a **macroscopic CA**: instead of binary states, each cell stores continuous values — terrain elevation and water depth — plus physical principles (mass conservation, continuity, Manning roughness).
- Cell states used to optimize processing: **Inactive** (no water, none incoming), **Transport** (slope allows downstream movement), **Accumulation** (retains volume due to terrain depression or insufficient outflow capacity).

## Modeling approach (the core algorithm)

- Alternative to full Shallow Water Equations: the **storage-cell** approach — water is a set of discrete units whose movement depends on neighboring cells' state, simplifying flow terms to focus on water balance between adjacent cells.
- **Transition rule** (per iteration t → t+1), the actual math to implement:
  1. **Water Surface Elevation**: `WSE = Z + H` per cell (Z = static terrain elevation, H = water depth). Flow goes from higher WSE to lower WSE (gravity).
  2. **Flow distribution to the 8 Moore neighbors**, weighted by **Manning's equation**: `Q_i = (1/n_i) * h_i^(5/3) * sqrt(S_i)` for downstream directions (Q_i = 0 upstream), where `n_i` = roughness coefficient, `h_i` = water depth, `S_i` = slope (≥0). Transport factor `F_Ti = Q_i / Σ Q_i` (normalized so all outflow factors sum to 1). Volume propagated in direction i: `V_i = F_Ti * V_tot`. The model differentiates orthogonal vs. diagonal neighbor distances to avoid geometric distortion.
  3. **Mass conservation**: transferred volumes are subtracted from source cells and added to destination cells every step; total volume in the system must stay constant (no rain/infiltration in the base model).
- Rules are applied **simultaneously/in parallel** across the whole grid — this is what makes CA cheap and vectorizable (NumPy today, CuPy/GPU later).

## Already-built informal proof of concept (section 4.3.1 — done in TCC1)

Before touching the Python/React architecture, an isolated algorithmic PoC was built to validate the transition rule logic in total isolation, using **arbitrary/normalized units, no real geodata**:
- 2D discrete grid; each cell has terrain altitude + water depth.
- Synthetic terrain (a simplified DEM with a couple of "hills"/depressions, see Figure 11 in the PDF — one hill top-left, a basin center-right).
- Initial condition: a **concentrated central pool** of water as the only water source.
- **Closed system**: no rain, no infiltration — total volume must stay exactly constant across iterations (this was the main correctness check).
- Each step: compute hydraulic head per cell, redistribute to the 8 Moore neighbors, prioritizing lower-head neighbors. Note: this informal PoC did **not** yet weight by Manning roughness (no roughness data existed yet) — it was a simpler head-difference redistribution than the full model described above.
- Result: water expanded outward from the center toward lower terrain; high terrain acted as a partial barrier, deforming the flooded area away from a perfect circle.
- Recorded metrics after 100 steps (Quadro 6): 1060 cells flooded, average depth 0.6393, total volume 678.6000 (confirming conservation), runtime 0.5428 s.
- A separate, independent activity was a high-fidelity **HTML/CSS/JS UI mockup** (Figure 12) — not connected to the engine, just a design prototype of the eventual React dashboard (side panel for GIS params, central Leaflet map, log/metrics panel).

**This is the template for the first real implementation step**: reproduce this experiment properly, as reusable code, before wiring any real data or infrastructure.

## Data sources (for later steps — not needed for the synthetic PoC)

| Data | Source | Resolution | Use |
|---|---|---|---|
| Regional topography (DEM) | SRTM / TOPODATA (INPE) | ~30 m | Terrain elevation matrix `Z` |
| Urban topography (optional, high precision) | LiDAR / DSM | ~±15 cm | Building/obstacle detail |
| Land cover | MapBiomas | high-res raster | Looked up into Manning roughness matrix `N` via a static category→coefficient dictionary |
| River geometry/bathymetry | Nautical charts / ADCP | variable | Channel capacity (not core to first version) |
| Historical flood levels | ANA / SGB telemetry, High-Water Marks (HWM) from 2023/2024 events | daily/hourly | Validation ground truth (used only in post-processing/calibration, not in the engine) |
| Remote sensing validation | SWOT satellite (Ka-band radar altimetry) | high spatial res, ~21-day revisit | Independent validation where ground sensors failed during the floods |

DEM preprocessing planned: clip to the Lajeado/Estrela region of interest, then **sink filling** (hydrological correction removing artificial radar-noise depressions) before converting to the elevation matrix `Z`.

## Planned architecture (not yet built beyond the informal PoC)

Client-server, containerized with Docker:
- **Backend (Python)**: loads preprocessed static data (DEM raster, roughness matrix, historical HWM) directly from the filesystem (no external DB/API calls during simulation, for performance). Runs the **CA engine** (the transition rule above) using vectorized NumPy (CuPy-compatible for future GPU use, no code changes needed). Exposes a **FastAPI** REST API for parameters + a **WebSocket** channel that broadcasts simulation frames to the frontend every N iterations. Also computes validation metrics (CSI, RMSE) server-side.
- **Frontend (React + TypeScript + Vite)**: a config panel (initial river stage, rainfall/volume params, neighborhood type), a **Leaflet** map (OpenStreetMap base layer) rendering flood overlays received live via WebSocket, and a log/metrics panel.
- **Rasterio**: reads/writes the geospatial raster data (GeoTIFF DEM, land-cover raster) to build the `Z` and `N` matrices ahead of time.
- Data flow: frontend params → FastAPI validates → engine initializes `H = 0` (Inactive state) → loop: compute WSE → compute Manning+Moore flow → mass-balance update `H` → every N iterations, encode frame as base64 PNG and broadcast over WebSocket, also persist `H[t]` to disk for later validation.

## Validation plan (for TCC II)

- **Horizontal accuracy**: Critical Success Index (CSI), comparing simulated flood extent (cell-by-cell) against real mapped flood polygons (remote sensing/satellite) — penalizes both under- and over-estimation. Related metrics mentioned: Hit Rate (HR), False Alarm Rate (FAR).
- **Vertical accuracy**: Root Mean Square Error (RMSE) between simulated depth and HWM/SWOT points, in meters.
- **Performance**: execution time and memory vs. grid size and iteration count; vectorized NumPy vs. naive loops; exploratory GPU (CuPy) benchmarks if hardware allows.
- Nash-Sutcliffe Efficiency (NSE) is mentioned in the literature review as a general goodness-of-fit metric (−∞ to 1) but CSI/RMSE are the metrics actually planned for this project's spatial/depth validation.

## Related work (for context, not to reimplement)

| Work | Approach | Key number | Relevance |
|---|---|---|---|
| Liu et al. 2015 | CA, gravitational divergence rules only | 4 cm precision, 1.2h event in 35s | No Manning weighting — a simplification this project avoids |
| Jahanbazi & Egger 2017 (OFS-CA) | Diffusive wave + adaptive timestep, beats CFL condition | Validated vs. 5 analytical cases | Adaptive Δt is a possible future optimization, explicitly deprioritized in TCC1 ("removal of the CFL criterion") |
| **Jamali et al. 2019 (CA-ffé)** | Fast CA, no depression pre-identification, no fixed timesteps | **250–1,100× faster** than traditional models | Biggest efficiency benchmark cited; but can't represent flow velocity or time-accurate wave-front arrival — this project's differentiator is doing time-stepped evolution while staying CA-fast |
| Tavakolifar et al. 2021 (SWMM-2DCA) | Hybrid 1D drainage + 2D CA | Matches MikeFlood accuracy, minutes→seconds | Needs detailed municipal infrastructure data (pipe diameters etc.) this project doesn't have/need |
| **Torres et al. 2022** | Top-down CA, Moore neighborhood, Manning-weighted transfer | HR > 94%, RMSE 0.012–0.085 m, ~1s vs. 2012s traditional | Closest methodological match — this project's transition rule is essentially this, extended to be time-stepped |
| Monte et al. 2016 | Traditional MGB-IPH + HEC-RAS coupling (Saint-Venant) | R² 0.99, RMSE 1.41 m | Baseline "traditional/expensive" approach being contrasted against |
| Sales et al. 2025 | SWOT satellite as virtual gauge stations | Up to 99% WSE accuracy, but ~21-day revisit | Used for validation in places ground sensors failed, not for real-time monitoring (too slow revisit) |

## Tech stack rationale (already decided, matches `plan.md`)

- **Python**: readability, huge scientific ecosystem, orchestrates lower-level vectorized routines.
- **FastAPI**: async-native, WebSocket support without HTTP polling overhead.
- **NumPy** (and future **CuPy** for GPU, same API): vectorized matrix ops for the CA engine — avoids explicit Python loops over cells.
- **Rasterio**: reads/writes GeoTIFF rasters (DEM, land cover) into NumPy arrays.
- **React + Vite**: componentized SPA UI.
- **Leaflet**: lightweight interactive map, OpenStreetMap base layer, overlays for flood frames.
- **Docker**: containerizes frontend/backend/data so the environment is reproducible.

## TCC II timeline (as planned in TCC1, Quadro 7 — for orientation only, not binding)

Jun Q1: Docker/repo/WebSocket setup. Jun Q2: DEM download + roughness matrix. Jul Q3: transition rules + Moore neighborhood. Jul Q4: matrix optimization + timestep. Aug Q5: React UI + Leaflet. Aug Q6: WebSocket streaming integration. Sep Q7: HWM + SWOT data vectorization. Sep Q8: historical scenario calibration (2024). Oct Q9: CSI/FAR/Hit Rate metrics extraction. Oct Q10: GPU portability experiments + writing results. Nov Q11–Q12: final writing, formatting, defense prep.

Note: this project (with Claude Code) is choosing to front-load **transition-rule validation on a synthetic grid** before Docker/infra setup, since the algorithm is the highest-risk, highest-value part to get right first — see `docs/project-plan.md` for the actual working order being followed.
