# ingestion

Has code since roadmap step 3: `dem.py` turns a raw DEM GeoTIFF into the plain NumPy `Z` array
`simulation/` consumes — reprojecting to a metric CRS with square pixels, cropping reprojection's
nodata border artifacts, and sink filling (hydrological correction) via a hand-rolled priority-flood
algorithm. Since step 4, `landcover.py` builds the roughness matrix `N`: it aligns a raw MapBiomas
land-cover raster onto the DEM's exact grid (nearest-neighbor resampling, since class IDs are
categorical) and maps class IDs to Manning's n via a static lookup table.

Reads from `data/raw/`, writes to `data/processed/`. Depends on `config/` for file paths. Never imports
`simulation/`, `api/`, or vice versa — `simulation/` only ever receives finished arrays.
