# data

Populated locally starting roadmap step 3 (contents gitignored, folders kept via `.gitkeep`).

Not code — this holds the actual geodata files: DEM tiles (SRTM/TOPODATA), MapBiomas land-cover rasters,
and validation ground-truth (High-Water Marks, SWOT altimetry) for the 2023/2024 floods.

- `raw/` — files as downloaded, untouched.
- `processed/` — clipped/sink-filled/lookup-applied outputs that `backend/ingestion/` produces and
  `backend/simulation/` (indirectly, via whoever calls it) consumes.

Expected to be gitignored once real files land here (large binary rasters don't belong in git history).
The code that reads and writes these files lives in `backend/ingestion/`, not here.
