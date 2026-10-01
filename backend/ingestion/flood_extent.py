"""Turn the raw SGB/CPRM flood-extent polygon for Lajeado into a boolean
"observed flooded" mask, aligned to a given reference grid.

Ground truth: SGB/CPRM (via IPH-UFRGS) publishes real HEC-RAS-2D-modeled
flood-extent polygons for Lajeado, indexed by river stage, as a public,
no-auth ArcGIS REST MapServer (see `config.settings.SGB_LAJEADO_MAPSERVER_URL`).
`scripts/download_flood_extent.py` saves the raw GeoJSON response for one
specific stage layer (33.67m, matching the real May 2024 peak) unparsed to
`data/raw/` - same "network script saves raw bytes, ingestion module does all
parsing" split as `dem.py`/`landcover.py`/`hydrograph.py`.

Pipeline: `load_raw_geojson` parses the saved FeatureCollection (local only).
`reproject_geometry` reprojects it from the source's geographic CRS
(EPSG:4674, SIRGAS 2000) into whatever CRS a reference grid actually uses -
via `rasterio.warp.transform_geom`, which works directly on GeoJSON-like dict
geometries, no shapely/geopandas dependency needed. `rasterize_flood_extent`
burns the reprojected polygon onto that reference grid via
`rasterio.features.rasterize`, producing a boolean mask the same shape as the
grid. `build_observed_flood_mask` runs all of this and persists the result,
mirroring `ingestion.dem.build_elevation_matrix`/
`ingestion.landcover.build_roughness_matrix` - resolution-agnostic, since it
reads its target transform/shape/CRS from whatever `reference_path` GeoTIFF
it's given (works at the live 30m grid or roadmap step 10's 90m validation
grid alike).

Reads from `data/raw/`, writes to `data/processed/`. Depends on `config/` for
paths. No CA logic here, no imports from `simulation/` - see
`docs/ARCHITECTURE.md`.
"""

import json
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.features import rasterize
from rasterio.warp import transform_geom

from config import settings


def load_raw_geojson(raw_path: Path) -> dict:
    """Parse the raw FeatureCollection `download_flood_extent.py` saves and
    return its single feature's geometry.

    Raises if the file doesn't contain exactly one feature rather than
    silently indexing `[0]` - the real SGB response for this layer is always
    one MultiPolygon (confirmed against a real download), so more or fewer
    features means something about the source changed and deserves a loud
    failure, not a silent wrong answer.
    """
    with open(raw_path) as f:
        geojson = json.load(f)

    features = geojson["features"]
    if len(features) != 1:
        raise ValueError(f"expected exactly 1 feature in {raw_path}, got {len(features)}")

    return features[0]["geometry"]


def reproject_geometry(geometry: dict, src_crs: str, dst_crs) -> dict:
    """Reproject a GeoJSON-like geometry mapping from `src_crs` to `dst_crs`.

    Uses `rasterio.warp.transform_geom` directly on the geometry dict - no
    shapely/geopandas dependency needed, reusing the project's existing
    rasterio dependency the same way `dem.py`/`landcover.py` already do for
    rasters.
    """
    return transform_geom(src_crs, dst_crs, geometry)


def rasterize_flood_extent(
    geometry: dict, reference_transform: Affine, reference_shape: tuple[int, int]
) -> np.ndarray:
    """Burn a reprojected polygon onto a reference grid, returning a boolean
    array (True inside the polygon) the same shape as the grid.
    """
    burned = rasterize(
        [(geometry, 1)],
        out_shape=reference_shape,
        transform=reference_transform,
        fill=0,
        dtype="uint8",
    )
    return burned.astype(bool)


def build_observed_flood_mask(
    raw_path: Path = settings.FLOOD_EXTENT_RAW_PATH,
    reference_path: Path = settings.DEM_PROCESSED_PATH,
    processed_path: Path = settings.FLOOD_EXTENT_VALIDATION_PROCESSED_PATH,
) -> np.ndarray:
    """Run the full raw-GeoJSON -> reproject -> rasterize -> boolean-mask
    pipeline, aligned to `reference_path`'s exact grid.

    Also persists the final result to `processed_path` as a uint8 GeoTIFF,
    mirroring `build_elevation_matrix`/`build_roughness_matrix`.
    """
    geometry = load_raw_geojson(raw_path)

    with rasterio.open(reference_path) as ref:
        transform, shape, crs = ref.transform, ref.shape, ref.crs

    reprojected = reproject_geometry(geometry, settings.FLOOD_EXTENT_SOURCE_CRS, crs)
    mask = rasterize_flood_extent(reprojected, transform, shape)

    processed_path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "width": shape[1],
        "height": shape[0],
        "count": 1,
        "crs": crs,
        "transform": transform,
    }
    with rasterio.open(processed_path, "w", **profile) as dst:
        dst.write(mask.astype("uint8"), 1)

    return mask


def dem_channel_col(Z: np.ndarray) -> np.ndarray:
    """Per-row DEM-implied channel column, `argmin(Z[row])` - the thalweg
    proxy the coverage-gap correction splits the two banks with."""
    return np.argmin(Z, axis=1)


def classify_far_bank(Z: np.ndarray, gauge_row: int, gauge_col: int) -> np.ndarray:
    """True for cells on the opposite side of the DEM-implied channel from the
    given gauge cell. With the real ANA "ESTRELA" gauge cell
    (`settings.VALIDATION_GAUGE_ROW/COL`), which sits on Lajeado's bank, this is
    Estrela's bank."""
    col_idx = np.arange(Z.shape[1])[None, :]
    is_west = col_idx < dem_channel_col(Z)[:, None]
    return ~is_west if bool(is_west[gauge_row, gauge_col]) else is_west


def coverage_gap_mask(
    Z: np.ndarray, stage_masks: list[np.ndarray], gauge_row: int, gauge_col: int
) -> np.ndarray:
    """Cells excluded from scoring by the Estrela coverage-gap correction
    (docs/tcc-deviations.md section 16.2): dry in the reference at every given
    stage AND on the bank opposite the gauge. The SGB product never modeled
    Estrela's side, so a cell it leaves dry there from near-baseflow to the peak
    says nothing either way and can't fairly count as a false alarm.

    Mirrors `examples/rescore_stage_invariant.py`'s `valid_estrela_gap_only`
    (as its complement), which computes the same thing from stage layers it
    queries live: there a cell is excluded when its status is identical across
    the stages and dry at the peak, which for any number of stages is exactly
    "dry at every stage".
    """
    dry_at_every_stage = ~np.logical_or.reduce(stage_masks)
    return np.logical_and(dry_at_every_stage, classify_far_bank(Z, gauge_row, gauge_col))


def build_validation_reference(
    Z: np.ndarray,
    reference_path: Path = settings.DEM_VALIDATION_PROCESSED_PATH,
    stage_layers: dict[int, tuple[float, Path]] = settings.FLOOD_EXTENT_STAGE_LAYERS,
    peak_layer_id: int = settings.FLOOD_EXTENT_LAYER_ID,
    gauge_row: int = settings.VALIDATION_GAUGE_ROW,
    gauge_col: int = settings.VALIDATION_GAUGE_COL,
) -> tuple[np.ndarray, np.ndarray]:
    """The observed May 2024 peak extent and the coverage-gap exclusion, both on
    `reference_path`'s grid (whose elevation is `Z`), from the raw stage-layer
    GeoJSONs `scripts/download_flood_extent.py` saves - fully offline.

    Returns `(observed, excluded)` boolean masks. The defaults are the 90m
    validation grid the documented CSI 0.8997 was scored on; the gauge cell is
    only geolocated on that grid (see `settings.VALIDATION_GAUGE_ROW`).
    """
    with rasterio.open(reference_path) as ref:
        transform, shape, crs = ref.transform, ref.shape, ref.crs
    if Z.shape != shape:
        raise ValueError(f"Z has shape {Z.shape} but {reference_path} has shape {shape}")

    masks = {}
    for layer_id, (_, raw_path) in stage_layers.items():
        geometry = reproject_geometry(load_raw_geojson(raw_path), settings.FLOOD_EXTENT_SOURCE_CRS, crs)
        masks[layer_id] = rasterize_flood_extent(geometry, transform, shape)

    excluded = coverage_gap_mask(Z, list(masks.values()), gauge_row, gauge_col)
    return masks[peak_layer_id], excluded
