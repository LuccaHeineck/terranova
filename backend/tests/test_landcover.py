import numpy as np
import pytest
import rasterio
from affine import Affine

from ingestion.landcover import align_to_reference_grid, build_roughness_matrix, classes_to_roughness


def test_classes_to_roughness_maps_known_classes():
    classes = np.array([[15, 33, 24]])  # Pasture, Water, Urban Area

    n = classes_to_roughness(classes)

    assert n.tolist() == [[0.030, 0.040, 0.150]]


def test_classes_to_roughness_raises_on_unmapped_class():
    classes = np.array([[15, 999]])  # 999 isn't in MANNING_N_BY_CLASS

    with pytest.raises(ValueError, match="999"):
        classes_to_roughness(classes)


def test_align_to_reference_grid_preserves_discrete_classes(tmp_path):
    """Regression for the nearest-vs-bilinear resampling decision: reprojecting
    a categorical class raster onto a different-resolution reference grid must
    never introduce class values that didn't exist in the source (which
    bilinear interpolation between e.g. class 15 and class 24 would)."""
    raw_path = tmp_path / "raw_landcover.tif"
    reference_path = tmp_path / "reference_z.tif"

    src_classes = np.full((10, 10), 15, dtype=np.uint8)  # Pasture
    src_classes[:, 5:] = 24  # Urban Area, right half
    src_transform = Affine.translation(700_000, 6_700_000) * Affine.scale(1.0, -1.0)
    with rasterio.open(
        raw_path, "w", driver="GTiff", height=10, width=10, count=1, dtype="uint8",
        crs="EPSG:31982", transform=src_transform,
    ) as dst:
        dst.write(src_classes, 1)

    # A reference grid at a different resolution/shape than the source, like
    # the real pipeline's DEM-derived grid would be relative to the raw
    # land-cover clip.
    ref_transform = Affine.translation(700_000, 6_700_000) * Affine.scale(1.4, -1.4)
    with rasterio.open(
        reference_path, "w", driver="GTiff", height=7, width=7, count=1, dtype="float64",
        crs="EPSG:31982", transform=ref_transform,
    ) as dst:
        dst.write(np.zeros((7, 7)), 1)

    aligned = align_to_reference_grid(raw_path, reference_path)

    assert aligned.shape == (7, 7)
    assert set(np.unique(aligned)).issubset({15, 24})


def test_build_roughness_matrix_matches_reference_shape(tmp_path):
    raw_path = tmp_path / "raw_landcover.tif"
    reference_path = tmp_path / "reference_z.tif"
    processed_path = tmp_path / "n.tif"

    transform = Affine.translation(0, 0) * Affine.scale(30.0, -30.0)
    with rasterio.open(
        raw_path, "w", driver="GTiff", height=5, width=5, count=1, dtype="uint8",
        crs="EPSG:31982", transform=transform,
    ) as dst:
        dst.write(np.full((5, 5), 33, dtype=np.uint8), 1)  # water

    with rasterio.open(
        reference_path, "w", driver="GTiff", height=5, width=5, count=1, dtype="float64",
        crs="EPSG:31982", transform=transform,
    ) as dst:
        dst.write(np.zeros((5, 5)), 1)

    n = build_roughness_matrix(raw_path, reference_path, processed_path)

    assert n.shape == (5, 5)
    assert np.allclose(n, 0.040)
    assert processed_path.exists()
