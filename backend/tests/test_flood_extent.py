import json

import numpy as np
import pytest
import rasterio
from affine import Affine

from ingestion.flood_extent import (
    build_observed_flood_mask,
    build_validation_reference,
    classify_far_bank,
    coverage_gap_mask,
    dem_channel_col,
    load_raw_geojson,
    rasterize_flood_extent,
    reproject_geometry,
)

_BOX_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[2, 2], [5, 2], [5, 5], [2, 5], [2, 2]]],
}


def _write_feature_collection(path, geometries):
    features = [{"type": "Feature", "properties": {}, "geometry": geom} for geom in geometries]
    with open(path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)


def test_load_raw_geojson_returns_single_feature_geometry(tmp_path):
    raw_path = tmp_path / "flood.geojson"
    _write_feature_collection(raw_path, [_BOX_GEOMETRY])

    geometry = load_raw_geojson(raw_path)

    assert geometry == _BOX_GEOMETRY


def test_load_raw_geojson_rejects_multiple_features(tmp_path):
    raw_path = tmp_path / "flood.geojson"
    _write_feature_collection(raw_path, [_BOX_GEOMETRY, _BOX_GEOMETRY])

    with pytest.raises(ValueError, match="2"):
        load_raw_geojson(raw_path)


def test_reproject_geometry_identity_crs_preserves_coordinates():
    """Reprojecting within the same CRS shouldn't move any coordinate -
    avoids needing to hand-verify real projection math in a unit test; real
    cross-CRS reprojection is exercised end-to-end by the real downloaded
    data in `examples/validate_may2024.py`."""
    reprojected = reproject_geometry(_BOX_GEOMETRY, "EPSG:31982", "EPSG:31982")

    assert np.allclose(reprojected["coordinates"], _BOX_GEOMETRY["coordinates"])


def test_rasterize_flood_extent_burns_polygon_onto_grid():
    """A box polygon from (2,2) to (5,5) on an identity-transform grid (pixel
    (row, col) center at (col+0.5, row+0.5)) must burn exactly the 3x3 block
    of cells whose centers fall inside it - rows/cols 2, 3, 4."""
    mask = rasterize_flood_extent(_BOX_GEOMETRY, Affine.identity(), (10, 10))

    assert mask.dtype == bool
    assert mask.shape == (10, 10)
    assert mask[2:5, 2:5].all()
    assert mask.sum() == 9


def test_build_observed_flood_mask_full_pipeline(tmp_path):
    """Uses a reference grid in the same CRS as the source geometry
    (FLOOD_EXTENT_SOURCE_CRS), so reprojection is a no-op and the rasterized
    result is hand-predictable, like `test_rasterize_flood_extent_...` above -
    real cross-CRS reprojection is exercised by the real downloaded data."""
    from config import settings

    raw_path = tmp_path / "flood.geojson"
    reference_path = tmp_path / "reference_z.tif"
    processed_path = tmp_path / "flood_mask.tif"

    _write_feature_collection(raw_path, [_BOX_GEOMETRY])

    with rasterio.open(
        reference_path, "w", driver="GTiff", height=10, width=10, count=1, dtype="float64",
        crs=settings.FLOOD_EXTENT_SOURCE_CRS, transform=Affine.identity(),
    ) as dst:
        dst.write(np.zeros((10, 10)), 1)

    mask = build_observed_flood_mask(raw_path, reference_path, processed_path)

    assert mask.dtype == bool
    assert mask.shape == (10, 10)
    assert mask[2:5, 2:5].all()
    assert mask.sum() == 9
    assert processed_path.exists()

    with rasterio.open(processed_path) as saved:
        assert saved.read(1).astype(bool).tolist() == mask.tolist()


# A 4x5 valley whose channel (lowest cell per row) runs down column 2, so
# columns 0-1 are the west bank and columns 3-4 the east bank.
_VALLEY_Z = np.array(
    [
        [9.0, 5.0, 1.0, 5.0, 9.0],
        [9.0, 5.0, 1.0, 5.0, 9.0],
        [9.0, 5.0, 1.0, 5.0, 9.0],
        [9.0, 5.0, 1.0, 5.0, 9.0],
    ]
)


def test_dem_channel_col_is_each_rows_lowest_cell():
    Z = _VALLEY_Z.copy()
    Z[3, 2], Z[3, 3] = 4.0, 0.5  # the channel bends east in the last row
    assert dem_channel_col(Z).tolist() == [2, 2, 2, 3]


@pytest.mark.parametrize(
    "gauge_col, far_cols",
    [(0, [2, 3, 4]), (4, [0, 1])],  # the channel column itself counts as east (not west of the channel)
)
def test_classify_far_bank_is_the_side_opposite_the_gauge(gauge_col, far_cols):
    far = classify_far_bank(_VALLEY_Z, gauge_row=1, gauge_col=gauge_col)
    assert far.shape == _VALLEY_Z.shape
    assert all(np.flatnonzero(row).tolist() == far_cols for row in far)


def test_coverage_gap_mask_excludes_far_bank_cells_dry_at_every_stage():
    low = np.zeros(_VALLEY_Z.shape, dtype=bool)
    low[:, 2] = True  # the permanent channel
    peak = low.copy()
    peak[:, 1] = True  # the gauge's (west) bank floods at the peak
    peak[0, 3] = True  # one far-bank cell floods at the peak only
    excluded = coverage_gap_mask(_VALLEY_Z, [low, peak], gauge_row=1, gauge_col=0)

    expected = np.zeros(_VALLEY_Z.shape, dtype=bool)
    expected[:, 3:] = True  # the far (east) bank...
    expected[0, 3] = False  # ...except the cell the reference does flood at some stage
    assert excluded.tolist() == expected.tolist()


def test_build_validation_reference_returns_peak_extent_and_gap(tmp_path):
    """Same no-op-reprojection setup as the full-pipeline test above. Two stages:
    the channel column alone, then the channel plus the west bank at the peak.
    With the gauge on the west bank, the east bank is never flooded and is the gap."""
    from config import settings

    reference_path = tmp_path / "reference_z.tif"
    with rasterio.open(
        reference_path, "w", driver="GTiff", height=4, width=5, count=1, dtype="float64",
        crs=settings.FLOOD_EXTENT_SOURCE_CRS, transform=Affine.identity(),
    ) as dst:
        dst.write(_VALLEY_Z, 1)

    # Polygons in (x=col, y=row) units, covering whole cells.
    channel = {"type": "Polygon", "coordinates": [[[2, 0], [3, 0], [3, 4], [2, 4], [2, 0]]]}
    channel_and_west = {"type": "Polygon", "coordinates": [[[0, 0], [3, 0], [3, 4], [0, 4], [0, 0]]]}
    low_path, peak_path = tmp_path / "low.geojson", tmp_path / "peak.geojson"
    _write_feature_collection(low_path, [channel])
    _write_feature_collection(peak_path, [channel_and_west])

    observed, excluded = build_validation_reference(
        _VALLEY_Z,
        reference_path=reference_path,
        stage_layers={1: (19.0, low_path), 2: (33.67, peak_path)},
        peak_layer_id=2,
        gauge_row=1,
        gauge_col=0,
    )

    assert np.flatnonzero(observed[0]).tolist() == [0, 1, 2]
    assert observed.sum() == 12
    assert excluded[:, 3:].all() and excluded.sum() == 8


def test_build_validation_reference_rejects_mismatched_elevation(tmp_path):
    from config import settings

    reference_path = tmp_path / "reference_z.tif"
    with rasterio.open(
        reference_path, "w", driver="GTiff", height=4, width=5, count=1, dtype="float64",
        crs=settings.FLOOD_EXTENT_SOURCE_CRS, transform=Affine.identity(),
    ) as dst:
        dst.write(_VALLEY_Z, 1)

    with pytest.raises(ValueError, match="shape"):
        build_validation_reference(np.zeros((3, 3)), reference_path=reference_path, stage_layers={})
