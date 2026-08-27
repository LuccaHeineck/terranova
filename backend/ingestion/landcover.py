"""Turn a raw MapBiomas land-cover GeoTIFF into the Manning roughness array `N`
`simulation/` consumes.

Pipeline:
1. Reproject the raw class-ID raster onto the *exact* pixel grid the processed
   DEM (`ingestion.dem.build_elevation_matrix`'s output) already uses - same
   transform, CRS, and shape - so `N` and `Z` line up cell-for-cell, which
   `simulation.engine.step` requires. This is a different reprojection call than
   `dem.py`'s `reproject_to_target_crs`: that one computes its own default
   transform for a target CRS/resolution, this one must land on a grid that
   already exists. It also uses nearest-neighbor resampling rather than
   `dem.py`'s bilinear - class IDs are categorical labels, not continuous
   elevation, so interpolating between e.g. class 15 (Pasture) and class 24
   (Urban Area) would invent a meaningless fractional in-between class.
2. Map each class ID to a Manning's n value via a static lookup table.

Reads from `data/raw/`, writes to `data/processed/`. Depends on `config/` for
paths. No CA logic here, no imports from `simulation/` - see
`docs/ARCHITECTURE.md`.
"""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling

from config import settings

# MapBiomas Collection 10 class ID -> Manning's n, cross-walked to the nearest
# NLCD land-cover analog in the NRCS-Kansas Manning's n table (adopted for
# HEC-RAS 2D dam-breach modeling), itself rooted in Chow (1959) *Open-Channel
# Hydraulics* and the HEC-RAS 2D Modeling User's Manual. MapBiomas has no
# official roughness table of its own.
#
# Deliberately scoped to classes plausible for the Vale do Taquari region (the
# 10 actually observed in the ROI, plus a few floodplain-adjacent extras) rather
# than MapBiomas's full ~29-class national legend - classes like mangrove,
# cerrado/savanna, salt flat, or restinga don't occur here. Any class ID outside
# this table raises loudly in `classes_to_roughness` rather than guessing; widen
# the ROI into new terrain, widen this table.
#
# Two documented simplifications:
# - Forest Plantation (9, Silviculture) is treated identically to natural Forest
#   Formation, though a managed plantation with cleared understory is arguably
#   less rough in reality.
# - Mosaic of Uses (21, a mixed agriculture/pasture/settlement category) is
#   treated as generic Cultivated Crops.
MANNING_N_BY_CLASS = {
    3: 0.160,  # Forest Formation (NLCD 41/42/43 Forest)
    6: 0.120,  # Floodable Forest / varzea (NLCD 90 Woody Wetlands)
    9: 0.160,  # Forest Plantation / Silviculture - simplification: treated as Forest
    11: 0.070,  # Wetland (NLCD 95 Emergent Herbaceous Wetlands)
    12: 0.035,  # Grassland (NLCD 71 Grassland/Herbaceous)
    15: 0.030,  # Pasture (NLCD 81 Pasture/Hay)
    21: 0.035,  # Mosaic of Uses - simplification: treated as Cultivated Crops
    24: 0.150,  # Urban Area (NLCD 24 Developed, High Intensity)
    25: 0.025,  # Other non-Vegetated Areas (NLCD 31 Barren Land)
    30: 0.025,  # Mining (NLCD 31 Barren Land)
    33: 0.040,  # River, Lake and Ocean / water (NLCD 11 Open Water)
    39: 0.035,  # Soybean (NLCD 82 Cultivated Crops)
    41: 0.035,  # Other Temporary Crops (NLCD 82 Cultivated Crops)
}


def classes_to_roughness(classes: np.ndarray) -> np.ndarray:
    """Map an array of MapBiomas class IDs to Manning's n via `MANNING_N_BY_CLASS`.

    Raises on any class ID not in the table instead of silently defaulting - an
    unmapped class in the ROI should be a loud, immediate surprise, not a hidden
    modeling error (same fail-fast style as `simulation.engine.step`'s input
    validation).
    """
    unknown = set(np.unique(classes)) - MANNING_N_BY_CLASS.keys()
    if unknown:
        raise ValueError(f"unmapped MapBiomas class IDs: {sorted(unknown)}")

    lookup = np.zeros(max(MANNING_N_BY_CLASS) + 1, dtype=np.float64)
    for class_id, n in MANNING_N_BY_CLASS.items():
        lookup[class_id] = n
    return lookup[classes]


def align_to_reference_grid(raw_path: Path, reference_path: Path) -> np.ndarray:
    """Resample the raw land-cover class raster onto `reference_path`'s exact grid."""
    with rasterio.open(reference_path) as ref:
        dst_transform, dst_crs = ref.transform, ref.crs
        dst_width, dst_height = ref.width, ref.height

    with rasterio.open(raw_path) as src:
        classes = np.zeros((dst_height, dst_width), dtype=src.dtypes[0])
        reproject(
            source=rasterio.band(src, 1),
            destination=classes,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.nearest,
        )

    return classes


def build_roughness_matrix(
    raw_path: Path = settings.LANDCOVER_RAW_PATH,
    reference_path: Path = settings.DEM_PROCESSED_PATH,
    processed_path: Path = settings.LANDCOVER_PROCESSED_PATH,
) -> np.ndarray:
    """Run the full raw-land-cover -> align -> lookup -> N-array pipeline.

    Also persists the final result to `processed_path` as a GeoTIFF, mirroring
    `ingestion.dem.build_elevation_matrix`.
    """
    classes = align_to_reference_grid(raw_path, reference_path)
    n = classes_to_roughness(classes)

    with rasterio.open(reference_path) as ref:
        profile = {
            "driver": "GTiff",
            "dtype": "float64",
            "width": ref.width,
            "height": ref.height,
            "count": 1,
            "crs": ref.crs,
            "transform": ref.transform,
        }

    processed_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(processed_path, "w", **profile) as dst:
        dst.write(n, 1)

    return n
