# ingestion

Empty for now — activates at roadmap step 3.

Will hold the code that turns raw geodata into the plain NumPy arrays `simulation/` consumes: reading
DEM tiles with `rasterio`, sink filling (hydrological correction), clipping to the Lajeado/Estrela ROI
(step 3), and applying the MapBiomas land-cover → Manning's-n lookup table to build the roughness
matrix `N` (step 4).

Reads from `data/raw/`, writes to `data/processed/`. Depends on `config/` for file paths. Never imports
`simulation/`, `api/`, or vice versa — `simulation/` only ever receives finished arrays.
