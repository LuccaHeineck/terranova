# scripts

Has code since roadmap step 3: `download_dem.py` fetches the raw DEM tile for the configured ROI from
the OpenTopography API into `data/raw/`. Since step 4, `download_landcover.py` fetches the matching
MapBiomas land-cover clip (a windowed `/vsicurl/` read of a public GCS-hosted GeoTIFF, no API key
needed) into `data/raw/` too. More one-off ops tooling (e.g. a preprocessing-batch trigger) may land
here in later steps.

Distinct from `examples/`: `examples/` holds demos that validate/showcase the engine's behavior (like
`poc_grid.py`); `scripts/` holds operational utilities that support running the project, not explaining
it.
