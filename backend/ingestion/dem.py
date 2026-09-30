"""Turn a raw DEM GeoTIFF into the plain `Z` array `simulation/` consumes.

Pipeline:
1. Reproject the raw geographic-CRS (EPSG:4326) GeoTIFF to a projected, metric CRS
   with square pixels - the engine assumes square grid cells (see
   `MOORE_OFFSETS`/`hypot` in `simulation/engine.py`), which only holds in a
   projected CRS. Reprojecting a few-km box also rotates it slightly relative to
   the new grid's axes (true north vs. grid north), leaving thin nodata slivers at
   the corners of the output raster's bounding box.
2. Crop those nodata slivers off (a real elevation array can't contain sentinel
   values - the engine would treat them as bottomless pits).
3. Sink-fill the result (removes artificial radar-noise depressions, per the TCC's
   DEM preprocessing note) via a priority-flood algorithm (Barnes et al. 2014):
   grow outward from the border, always expanding into the lowest known frontier
   cell next, raising any cell below its filling neighbor up to that neighbor's
   elevation. Implemented directly with `heapq` (stdlib) rather than a hydrology
   library - the algorithm is a few dozen lines, and it sidesteps `pysheds`/`numba`
   JIT compilation, which is currently broken on this project's Python 3.14
   (numba's codegen for generator-based iterators fails to compile - a numba/
   CPython version-compatibility bug, not anything about our DEM).

Reads from `data/raw/`, writes to `data/processed/`. Depends on `config/` for
paths/CRS/resolution. No CA logic here, no imports from `simulation/` - see
`docs/ARCHITECTURE.md`.
"""

import heapq
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.transform import rowcol
from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_bounds
from rasterio.warp import transform as warp_transform

from config import settings


def reproject_to_target_crs(
    src_path: Path,
    dst_path: Path,
    dst_crs: str = settings.TARGET_CRS,
    resolution: float = settings.TARGET_RESOLUTION_METERS,
) -> None:
    """Reproject and resample a GeoTIFF to `dst_crs` with square `resolution`-meter pixels."""
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds, resolution=resolution
        )
        profile = src.profile.copy()
        profile.update(crs=dst_crs, transform=transform, width=width, height=height)

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **profile) as dst:
            reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
            )


def crop_nodata_border(elevation: np.ndarray, nodata: float, transform: Affine) -> tuple[np.ndarray, Affine]:
    """Trim rows/cols off each edge until no nodata sentinel remains on the border.

    Reprojection rotates the raster slightly relative to the new grid's axes,
    leaving thin nodata slivers only at the corners - a greedy edge trim clears
    them without discarding more real data than necessary. Returns the cropped
    array along with the transform adjusted for the new (0, 0) origin.
    """
    mask = elevation == nodata
    top, bottom = 0, mask.shape[0]
    left, right = 0, mask.shape[1]

    changed = True
    while changed:
        changed = False
        if mask[top, left:right].any():
            top += 1
            changed = True
        if mask[bottom - 1, left:right].any():
            bottom -= 1
            changed = True
        if mask[top:bottom, left].any():
            left += 1
            changed = True
        if mask[top:bottom, right - 1].any():
            right -= 1
            changed = True
        if top >= bottom or left >= right:
            raise ValueError("nodata border trim consumed the entire raster")

    cropped_transform = transform * Affine.translation(left, top)
    return elevation[top:bottom, left:right], cropped_transform


_MOORE_NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def fill_sinks(elevation: np.ndarray) -> np.ndarray:
    """Fill depressions in an elevation array (priority-flood, Barnes et al. 2014).

    Starts from the border (guaranteed to drain, since the grid boundary is the
    edge of our data) and grows inward always through the lowest-elevation
    frontier cell first, raising any interior cell up to the level of whichever
    filling front reaches it first. That's the same guarantee closed-basin
    hydrological correction needs: every interior cell ends up connected to the
    border by a monotonically non-increasing path.
    """
    rows, cols = elevation.shape
    filled = elevation.astype(np.float64).copy()
    visited = np.zeros((rows, cols), dtype=bool)

    heap = []
    for r in range(rows):
        for c in (0, cols - 1):
            if not visited[r, c]:
                visited[r, c] = True
                heapq.heappush(heap, (filled[r, c], r, c))
    for c in range(cols):
        for r in (0, rows - 1):
            if not visited[r, c]:
                visited[r, c] = True
                heapq.heappush(heap, (filled[r, c], r, c))

    while heap:
        elev, r, c = heapq.heappop(heap)
        for dr, dc in _MOORE_NEIGHBORS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr, nc]:
                visited[nr, nc] = True
                if filled[nr, nc] < elev:
                    filled[nr, nc] = elev
                heapq.heappush(heap, (filled[nr, nc], nr, nc))

    return filled


def build_elevation_matrix(
    raw_path: Path = settings.DEM_RAW_PATH,
    processed_path: Path = settings.DEM_PROCESSED_PATH,
    resolution: float = settings.TARGET_RESOLUTION_METERS,
) -> np.ndarray:
    """Run the full raw-GeoTIFF -> reproject -> crop -> sink-fill -> Z-array pipeline.

    Also persists the final result to `processed_path` as a GeoTIFF. The
    intermediate reprojected raster is scratch - it lives in a temp dir, not
    `data/processed/`, since only the final filled result is a real pipeline output.

    `resolution` defaults to the officially-served grid's resolution
    (`settings.TARGET_RESOLUTION_METERS`, 30m) so every existing caller is
    unaffected; roadmap step 10's validation script passes
    `settings.VALIDATION_RESOLUTION_METERS` (90m) to build a separate, coarser
    grid for a one-off validation run without touching the live 30m pipeline.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        reprojected_path = Path(tmp_dir) / "reprojected.tif"
        reproject_to_target_crs(raw_path, reprojected_path, resolution=resolution)

        with rasterio.open(reprojected_path) as src:
            elevation = src.read(1).astype(np.float64)
            nodata = src.nodata
            transform = src.transform
            crs = src.crs

    cropped, cropped_transform = crop_nodata_border(elevation, nodata, transform)
    filled = fill_sinks(cropped)

    processed_path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "dtype": "float64",
        "width": filled.shape[1],
        "height": filled.shape[0],
        "count": 1,
        "crs": crs,
        "transform": cropped_transform,
    }
    with rasterio.open(processed_path, "w", **profile) as dst:
        dst.write(filled, 1)

    return filled


def get_geographic_bounds(
    processed_path: Path = settings.DEM_PROCESSED_PATH,
) -> tuple[float, float, float, float]:
    """Return (west, south, east, north) WGS84 degrees for the processed grid's exact extent.

    Reads the *processed* GeoTIFF's own transform/CRS - already reprojected and nodata-cropped
    by `build_elevation_matrix` - rather than the raw `ROI_*` constants in `config/settings.py`,
    which describe a slightly larger pre-crop box. This is the precise extent callers need to
    place the Z/H grid on a real-world map.
    """
    with rasterio.open(processed_path) as src:
        west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    return west, south, east, north


def get_georeference(processed_path: Path = settings.DEM_PROCESSED_PATH) -> tuple[str, Affine]:
    """Return the processed grid's own CRS (as a string) and affine transform.

    The exact georeference `Z`'s rows/cols live on - what `lonlat_to_cell` and
    `grid_footprint` need to go between WGS84 map coordinates and grid cells.
    """
    with rasterio.open(processed_path) as src:
        return src.crs.to_string(), src.transform


def lonlat_to_cell(
    lon: float, lat: float, crs: str, grid_transform: Affine, shape: tuple[int, int]
) -> tuple[int, int] | None:
    """Return the (row, col) of the grid cell containing a WGS84 point, or None if outside the grid.

    Reprojects the point into the grid's own (projected) CRS and applies the inverse
    affine transform. Deliberately not a linear interpolation over the grid's WGS84
    bounding box (`get_geographic_bounds`): the grid is north-up in its UTM CRS, so in
    lat/lon it is slightly rotated and its bounding box also covers thin slivers
    outside it - the shortcut misplaces cells by up to a cell or two near the edges.
    """
    (x,), (y,) = warp_transform("EPSG:4326", crs, [lon], [lat])
    row, col = rowcol(grid_transform, x, y)  # floor: the cell whose area contains the point
    row, col = int(row), int(col)
    rows, cols = shape
    if not (0 <= row < rows and 0 <= col < cols):
        return None
    return row, col


def grid_footprint(crs: str, grid_transform: Affine, shape: tuple[int, int]) -> list[tuple[float, float]]:
    """Return the grid's four outer corners as WGS84 (lat, lon), clockwise from the top-left.

    Its true outline on a web map, unlike `get_geographic_bounds`' axis-aligned
    envelope. Straight edges between the corners are exact to well under a meter
    over a few-km grid.
    """
    rows, cols = shape
    corners = [grid_transform * (c, r) for c, r in ((0, 0), (cols, 0), (cols, rows), (0, rows))]
    lons, lats = warp_transform(crs, "EPSG:4326", [x for x, _ in corners], [y for _, y in corners])
    return list(zip(lats, lons))
