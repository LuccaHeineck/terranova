import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from ingestion.dem import build_elevation_matrix, crop_nodata_border, fill_sinks, reproject_to_target_crs


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
