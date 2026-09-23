import json

import numpy as np
import pytest
import rasterio
from affine import Affine

from ingestion.flood_extent import (
    build_observed_flood_mask,
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
