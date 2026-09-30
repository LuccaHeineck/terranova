import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from affine import Affine
from rasterio.warp import transform as warp_transform

from ingestion.dem import (
    build_elevation_matrix,
    crop_nodata_border,
    fill_sinks,
    grid_footprint,
    lonlat_to_cell,
    reproject_to_target_crs,
)


def test_fill_sinks_removes_artificial_pit():
    """A single-cell depression surrounded by higher terrain (the TCC's
    'artificial radar-noise depression' case) must be raised to no longer be
    a local minimum below its neighbors."""
    Z = np.array(
        [
            [10.0, 10.0, 10.0],
            [10.0, 1.0, 10.0],
            [10.0, 10.0, 10.0],
        ]
    )

    filled = fill_sinks(Z)

    assert filled[1, 1] >= 10.0
    # Untouched elsewhere: the border cells are already the fill sources.
    assert np.array_equal(filled[0, :], Z[0, :])


def test_fill_sinks_leaves_monotonic_terrain_unchanged():
    """Terrain that already slopes monotonically down to the border (no
    depressions) shouldn't be altered by sink filling."""
    rows, cols = 6, 6
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    Z = x + y  # strictly increasing away from the (0, 0) corner

    filled = fill_sinks(Z)

    assert np.allclose(filled, Z)


def test_crop_nodata_border_removes_corner_slivers():
    nodata = -32768.0
    elevation = np.full((6, 6), 50.0)
    # Two corner-touching nodata slivers, mimicking the rotation artifact
    # reprojection leaves at the edges of the output bounding box.
    elevation[0, 0] = nodata
    elevation[0, 1] = nodata
    elevation[5, 5] = nodata

    from affine import Affine

    transform = Affine.identity()
    cropped, cropped_transform = crop_nodata_border(elevation, nodata, transform)

    assert not np.any(cropped == nodata)
    assert cropped_transform != transform


def test_crop_nodata_border_raises_if_all_nodata():
    from affine import Affine

    elevation = np.full((4, 4), -32768.0)
    with pytest.raises(ValueError):
        crop_nodata_border(elevation, -32768.0, Affine.identity())


def test_reproject_to_target_crs_produces_square_pixels(tmp_path):
    """Regression for the engine's square-cell assumption (see
    `simulation/engine.py`'s MOORE_OFFSETS/hypot distance weighting): a raw
    geographic-CRS raster must come out with equal x/y pixel spacing in the
    target metric CRS."""
    rows, cols = 20, 20
    src_path = tmp_path / "src.tif"
    # A small box near Lajeado/Estrela, in degrees (EPSG:4326).
    transform = from_bounds(-51.99, -29.505, -51.93, -29.455, cols, rows)
    data = np.linspace(0, 100, rows * cols, dtype="float32").reshape(rows, cols)

    with rasterio.open(
        src_path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-32768.0,
    ) as dst:
        dst.write(data, 1)

    dst_path = tmp_path / "reprojected.tif"
    reproject_to_target_crs(src_path, dst_path, dst_crs="EPSG:31982", resolution=30.0)

    with rasterio.open(dst_path) as ds:
        assert ds.crs.to_string() == "EPSG:31982"
        res_x, res_y = ds.res
        assert res_x == pytest.approx(30.0)
        assert res_y == pytest.approx(30.0)


def test_build_elevation_matrix_honors_resolution_override(tmp_path):
    """Regression for roadmap step 10's validation grid: build_elevation_matrix's
    `resolution` kwarg must actually reach reproject_to_target_crs, not just sit
    unused - a coarser resolution must produce a coarser (smaller-shape) grid over
    the same real-world extent."""
    rows, cols = 60, 60
    src_path = tmp_path / "src.tif"
    transform = from_bounds(-51.99, -29.505, -51.93, -29.455, cols, rows)
    data = np.linspace(0, 100, rows * cols, dtype="float32").reshape(rows, cols)

    with rasterio.open(
        src_path,
        "w",
        driver="GTiff",
        height=rows,
        width=cols,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-32768.0,
    ) as dst:
        dst.write(data, 1)

    fine = build_elevation_matrix(
        raw_path=src_path, processed_path=tmp_path / "z_30m.tif", resolution=30.0
    )
    coarse = build_elevation_matrix(
        raw_path=src_path, processed_path=tmp_path / "z_90m.tif", resolution=90.0
    )

    assert coarse.shape[0] < fine.shape[0]
    assert coarse.shape[1] < fine.shape[1]


# A 30m UTM 22S grid at the real 30m grid's origin, larger than it (400x400 =
# 12 km), so its ~0.5 deg rotation relative to lat/lon is several cells at the edges.
UTM_CRS = "EPSG:31982"
UTM_TRANSFORM = Affine(30.0, 0.0, 404043.3, 0.0, -30.0, 6741197.92)
UTM_SHAPE = (400, 400)


def _lonlat(row: float, col: float) -> tuple[float, float]:
    x, y = UTM_TRANSFORM * (col, row)
    (lon,), (lat,) = warp_transform(UTM_CRS, "EPSG:4326", [x], [y])
    return lon, lat


@pytest.mark.parametrize("cell", [(0, 0), (0, 399), (199, 200), (399, 0), (399, 399)])
def test_lonlat_to_cell_round_trips_cell_centers(cell):
    row, col = cell

    assert lonlat_to_cell(*_lonlat(row + 0.5, col + 0.5), UTM_CRS, UTM_TRANSFORM, UTM_SHAPE) == cell


def test_lonlat_to_cell_returns_none_outside_the_grid():
    assert lonlat_to_cell(*_lonlat(-0.5, 10.5), UTM_CRS, UTM_TRANSFORM, UTM_SHAPE) is None
    assert lonlat_to_cell(*_lonlat(10.5, 400.5), UTM_CRS, UTM_TRANSFORM, UTM_SHAPE) is None


def test_lonlat_to_cell_differs_from_linear_interpolation_over_the_wgs84_envelope():
    """Why the conversion reprojects: stretching the grid linearly over its lat/lon
    bounding box (what an axis-aligned web-map overlay does) misplaces a corner
    cell, because the UTM-north-up grid is rotated in lat/lon."""
    footprint = grid_footprint(UTM_CRS, UTM_TRANSFORM, UTM_SHAPE)
    lats = [lat for lat, _ in footprint]
    lons = [lon for _, lon in footprint]
    north, south, west, east = max(lats), min(lats), min(lons), max(lons)
    lon, lat = _lonlat(0.5, 399.5)  # the top-right cell's center

    linear_row = int((north - lat) / (north - south) * UTM_SHAPE[0])

    assert lonlat_to_cell(lon, lat, UTM_CRS, UTM_TRANSFORM, UTM_SHAPE) == (0, 399)
    assert linear_row >= 2  # the shortcut puts the top-right corner cell rows too far south


def test_grid_footprint_corners_are_the_grid_corners_in_wgs84():
    footprint = grid_footprint(UTM_CRS, UTM_TRANSFORM, UTM_SHAPE)

    expected = [_lonlat(0, 0), _lonlat(0, 400), _lonlat(400, 400), _lonlat(400, 0)]
    assert footprint == pytest.approx([(lat, lon) for lon, lat in expected])
