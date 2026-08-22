# config

Empty for now — starts mattering at roadmap step 3.

Will centralize settings that are currently just hardcoded constants in `examples/poc_grid.py`
(grid size, `outflow_fraction`, etc.) plus things that don't exist yet: paths to DEM/land-cover files
(step 3-4), API host/port and WebSocket settings (step 5), and Docker-driven environment variables
(step 7).

Pure settings module — no imports from `simulation/`, `ingestion/`, or `api/`. Everything else may import
`config/`, never the other way around.
