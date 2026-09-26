"""Characterize the False Positive region of a validate_may2024.py run
(roadmap step 10/11 exploratory tooling).

Prerequisite check for the depth-threshold sweep: visually inspecting the
outflow_fraction=0.085 confusion map (see docs/tcc-deviations.md section 16)
showed the FP cells aren't a thin fringe around the True Positive band (what
a threshold/registration artifact would look like) - they form one large,
geographically distinct blob, apparently a tributary branch separate from
the main Taquari channel. This script answers three questions directly from
already-saved data, no new simulation run:

1. Are FP depths shallow (near the 0.01m wet-cell cutoff, so raising the
   threshold could plausibly help) or comparable to TP depths (genuinely
   "confident" water, so no threshold choice fixes this)?
2. Is the FP region spatially one distinct blob, and does its terrain (Z)
   look like a separate tributary valley rather than an extension of the
   main channel's floodplain?
3. Does the real SGB ground-truth polygon actually cover that area (and
   determined it dry - a genuine model over-prediction) or does the area
   sit outside/at the fringe of where SGB has any polygon coverage at all
   (a data/mapping coverage gap rather than a confirmed-dry determination)?

Report only - no fix, no live default touched.

Run from the backend/ directory with the venv active:
    python -m examples.characterize_fp_region --npz PATH
"""

import argparse
from collections import deque
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import xy as transform_xy

from config import settings
from ingestion.flood_extent import load_raw_geojson, reproject_geometry


def _depth_stats(label: str, depths: np.ndarray) -> None:
    n = depths.size
    print(f"  {label} (n={n}):")
    if n == 0:
        print("    (no cells)")
        return
    print(f"    min={depths.min():.4f}m  median={np.median(depths):.4f}m  max={depths.max():.4f}m")
    for cutoff in (0.1, 0.5, 1.0):
        pct = 100 * (depths < cutoff).mean()
        print(f"    % under {cutoff}m: {pct:.1f}%")


def _connected_components(mask: np.ndarray) -> list[np.ndarray]:
    """4-connected BFS flood-fill over a boolean mask - a small pure-NumPy
    stand-in for scipy.ndimage.label (scipy is not a project dependency).
    Returns a list of boolean masks, one per component, largest first."""
    visited = np.zeros_like(mask, dtype=bool)
    rows, cols = mask.shape
    components = []

    for r0 in range(rows):
        for c0 in range(cols):
            if not mask[r0, c0] or visited[r0, c0]:
                continue
            component = np.zeros_like(mask, dtype=bool)
            queue = deque([(r0, c0)])
            visited[r0, c0] = True
            while queue:
                r, c = queue.popleft()
                component[r, c] = True
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and mask[nr, nc] and not visited[nr, nc]:
                        visited[nr, nc] = True
                        queue.append((nr, nc))
            components.append(component)

    components.sort(key=lambda c: c.sum(), reverse=True)
    return components


def _walk_points(coords) -> list[tuple[float, float]]:
    points = []

    def _walk(c):
        if isinstance(c[0], (float, int)):
            points.append((c[0], c[1]))
        else:
            for sub in c:
                _walk(sub)

    _walk(coords)
    return points


def _polygon_bbox(geometry: dict) -> tuple[float, float, float, float]:
    """(minx, miny, maxx, maxy) across every ring of a Polygon/MultiPolygon."""
    points = _walk_points(geometry["coordinates"])
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _ring_bboxes(geometry: dict) -> list[tuple[float, float, float, float]]:
    """One (minx, miny, maxx, maxy) per top-level polygon ring of a
    MultiPolygon - lets us find the single nearest sub-polygon to a point of
    interest, not just the combined envelope of all 18 rings together."""
    bboxes = []
    for polygon_coords in geometry["coordinates"]:
        points = _walk_points(polygon_coords)
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        bboxes.append((min(xs), min(ys), max(xs), max(ys)))
    return bboxes


def _bbox_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """0.0 if the two bounding boxes overlap; otherwise the straight-line gap
    between their nearest edges/corners."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = max(bx0 - ax1, ax0 - bx1, 0.0)
    dy = max(by0 - ay1, ay0 - by1, 0.0)
    return float(np.hypot(dx, dy))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--npz",
        type=Path,
        default=Path("../data/sweep_outputs/of_0.085.npz"),
        help="Path to a validate_may2024.py --save-masks .npz file.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    data = np.load(args.npz)
    simulated_mask = data["simulated_mask"]
    observed_mask = data["observed_mask"]
    Z = data["Z"]
    H = data["H"]

    fp_mask = np.logical_and(simulated_mask, ~observed_mask)
    tp_mask = np.logical_and(simulated_mask, observed_mask)
    print(f"FP cells: {int(fp_mask.sum())}  TP cells: {int(tp_mask.sum())}")

    print("\n=== 1. Depth histograms: FP vs TP ===")
    _depth_stats("FP (simulated flooded, observed dry)", H[fp_mask])
    _depth_stats("TP (simulated flooded, observed flooded)", H[tp_mask])

    print("\n=== 2. Spatial characterization of the FP region ===")
    components = _connected_components(fp_mask)
    print(f"number of connected FP components (4-connected): {len(components)}")
    largest = components[0]
    largest_frac = 100 * largest.sum() / fp_mask.sum()
    rows, cols = np.where(largest)
    row_min, row_max, col_min, col_max = rows.min(), rows.max(), cols.min(), cols.max()
    print(f"largest component: {int(largest.sum())} cells ({largest_frac:.1f}% of all FP cells)")
    print(f"  bounding box: rows [{row_min}, {row_max}], cols [{col_min}, {col_max}]")
    z_in_blob = Z[largest]
    print(f"  Z (terrain) in blob: min={z_in_blob.min():.2f}m mean={z_in_blob.mean():.2f}m max={z_in_blob.max():.2f}m")
    tp_row_min, tp_row_max = np.where(tp_mask)[0].min(), np.where(tp_mask)[0].max()
    tp_col_min, tp_col_max = np.where(tp_mask)[1].min(), np.where(tp_mask)[1].max()
    print(f"  (for comparison) TP bounding box: rows [{tp_row_min}, {tp_row_max}], cols [{tp_col_min}, {tp_col_max}]")
    z_in_tp = Z[tp_mask]
    print(f"  (for comparison) Z in TP band: min={z_in_tp.min():.2f}m mean={z_in_tp.mean():.2f}m max={z_in_tp.max():.2f}m")

    print("\n=== 3. Cross-check against the raw SGB polygon ===")
    with rasterio.open(settings.DEM_VALIDATION_PROCESSED_PATH) as ref:
        transform, crs = ref.transform, ref.crs
    corners_rc = [(row_min, col_min), (row_min, col_max), (row_max, col_min), (row_max, col_max)]
    corners_xy = [transform_xy(transform, r, c) for r, c in corners_rc]
    blob_minx = min(x for x, y in corners_xy)
    blob_maxx = max(x for x, y in corners_xy)
    blob_miny = min(y for x, y in corners_xy)
    blob_maxy = max(y for x, y in corners_xy)
    print(f"FP blob bounding box in grid CRS ({crs}): x [{blob_minx:.1f}, {blob_maxx:.1f}], y [{blob_miny:.1f}, {blob_maxy:.1f}]")

    geometry = load_raw_geojson(settings.FLOOD_EXTENT_RAW_PATH)
    reprojected = reproject_geometry(geometry, settings.FLOOD_EXTENT_SOURCE_CRS, crs)
    poly_minx, poly_miny, poly_maxx, poly_maxy = _polygon_bbox(reprojected)
    print(f"raw SGB polygon overall bounding envelope in grid CRS: x [{poly_minx:.1f}, {poly_maxx:.1f}], y [{poly_miny:.1f}, {poly_maxy:.1f}]")

    inside_x = poly_minx <= blob_minx and blob_maxx <= poly_maxx
    inside_y = poly_miny <= blob_miny and blob_maxy <= poly_maxy
    print(f"FP blob bounding box fully inside SGB polygon's overall envelope: {inside_x and inside_y}")
    print(
        "  margins to the overall envelope edge (m): "
        f"west={blob_minx - poly_minx:.1f} east={poly_maxx - blob_maxx:.1f} "
        f"south={blob_miny - poly_miny:.1f} north={poly_maxy - blob_maxy:.1f} "
        f"(cell size={settings.VALIDATION_RESOLUTION_METERS:.0f}m)"
    )
    if not (inside_x and inside_y):
        print("  -> the FP blob extends outside where SGB's own polygon data reaches at all in at least one axis -")
        print("     consistent with a coverage/mapping gap, not necessarily a confirmed-dry determination.")
    else:
        print("  -> the FP blob sits entirely within SGB's mapped envelope, so its polygon had the opportunity")
        print("     to cover this area and did not - consistent with a genuine dry determination there.")

    blob_bbox = (blob_minx, blob_miny, blob_maxx, blob_maxy)
    ring_bboxes = _ring_bboxes(reprojected)
    gaps = [_bbox_gap(blob_bbox, rb) for rb in ring_bboxes]
    nearest_idx = int(np.argmin(gaps))
    print(f"nearest of the 18 SGB sub-polygon rings to the FP blob: ring #{nearest_idx}, gap={gaps[nearest_idx]:.1f}m")
    print(f"  ring #{nearest_idx} bbox: {ring_bboxes[nearest_idx]}")
    overlapping_idx = [i for i, g in enumerate(gaps) if g == 0.0]
    print(f"  rings whose bbox overlaps the FP blob's bbox: {len(overlapping_idx)} of {len(ring_bboxes)}")
    for i in overlapping_idx:
        minx, miny, maxx, maxy = ring_bboxes[i]
        print(f"    ring #{i}: bbox area={(maxx - minx) * (maxy - miny) / 1e6:.2f} km^2")


if __name__ == "__main__":
    main()
