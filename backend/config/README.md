# config

Has code since roadmap step 3: `settings.py` centralizes the ROI bounding box, DEM source/target CRS/
resolution, `data/raw/` and `data/processed/` paths, and `OPENTOPOGRAPHY_API_KEY` loading (from
`backend/.env`, gitignored). Since step 4, it also holds the MapBiomas collection/year and land-cover
raw/processed paths.

Grid size and `outflow_fraction` are still hardcoded in `examples/poc_grid.py` (synthetic PoC-only
constants, not settings). Still to come: API host/port and WebSocket settings (step 5), and
Docker-driven environment variables (step 7).

Pure settings module — no imports from `simulation/`, `ingestion/`, or `api/`. Everything else may import
`config/`, never the other way around.
