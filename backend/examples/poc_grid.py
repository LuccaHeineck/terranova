"""Small artificial-grid proof of concept for the CA flood engine.

Builds a synthetic terrain (one hill acting as a barrier, one basin where
water should pool) and a synthetic Manning roughness field (a smoother
diagonal "channel" through a rougher background), drops a concentrated pool
of water at the basin, runs the engine for a fixed number of closed-system
steps (no rain, no infiltration), and checks that mass is conserved and
depth never goes negative. Saves a plot of terrain/roughness/depth snapshots
over time for a quick visual sanity check.

Run from the backend/ directory with the venv active:
    python -m scripts.poc_grid
"""

import time

import matplotlib.pyplot as plt
import numpy as np

from simulation.engine import step

GRID_SIZE = 50
STEPS = 100
SEED_VOLUME = 400.0
OUTPUT_PATH = "poc_grid_result.png"
SNAPSHOT_STEPS = (0, 5, 10, 15, 50)


def synthetic_terrain(rows: int, cols: int) -> np.ndarray:
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    cy, cx = rows / 2, cols / 2
    basin = ((x - cx) ** 2 + (y - cy) ** 2) / (rows * cols) * 3.0
    hill = 2.0 * np.exp(
        -(((x - cols * 0.3) ** 2 + (y - rows * 0.35) ** 2) / (2 * (cols * 0.1) ** 2))
    )
    return basin + hill


def synthetic_roughness(rows: int, cols: int) -> np.ndarray:
    """A smooth Manning roughness field: a low-n "channel" band running along
    the top-left-to-bottom-right diagonal, blended into a higher-n
    background. Deliberately smooth (no sharp edges) - a hard discontinuity
    here would risk the same kind of head-difference instability that a
    sharp-edged initial water patch causes (see engine.py's stability note).
    Oriented diagonally, independent of the terrain's basin/hill asymmetry,
    so its effect on the flood shape is visually distinguishable from
    terrain-driven spread alone.
    """
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    diagonal = (x - y) / max(rows, cols)
    channel = np.exp(-(diagonal ** 2) / (2 * 0.15 ** 2))
    n_min, n_max = 0.02, 0.09
    return n_max - (n_max - n_min) * channel


def seed_pool(H: np.ndarray, volume: float) -> None:
    rows, cols = H.shape
    cy, cx = rows // 2, cols // 2
    patch = H[cy - 2: cy + 3, cx - 2: cx + 3]
    patch[:] = volume / patch.size


def main() -> None:
    Z = synthetic_terrain(GRID_SIZE, GRID_SIZE)
    N = synthetic_roughness(GRID_SIZE, GRID_SIZE)
    H = np.zeros((GRID_SIZE, GRID_SIZE))
    seed_pool(H, SEED_VOLUME)

    initial_volume = H.sum()
    snapshots = {}
    if 0 in SNAPSHOT_STEPS:
        snapshots[0] = H.copy()

    start = time.perf_counter()
    for t in range(1, STEPS + 1):
        H = step(Z, H, N)
        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        assert abs(H.sum() - initial_volume) < 1e-6, (
            f"volume drifted at step {t}: {H.sum()} vs {initial_volume}"
        )
        if t in SNAPSHOT_STEPS:
            snapshots[t] = H.copy()
    elapsed = time.perf_counter() - start

    flooded = H > 1e-6
    print(f"discrete steps simulated: {STEPS}")
    print(f"flooded cells: {flooded.sum()}")
    print(f"average depth over flooded cells: {H[flooded].mean():.4f}")
    print(f"total volume (conservation check): {H.sum():.4f} (initial: {initial_volume:.4f})")
    print(f"execution time: {elapsed:.4f} s")

    n_panels = 2 + len(SNAPSHOT_STEPS)
    fig, axes = plt.subplots(1, n_panels, figsize=(5 * n_panels, 5))
    axes[0].imshow(Z, cmap="terrain")
    axes[0].set_title("Terrain")
    axes[1].imshow(N, cmap="viridis_r")
    axes[1].set_title("Roughness (N)")
    for ax, t in zip(axes[2:], SNAPSHOT_STEPS):
        ax.imshow(snapshots[t], cmap="Blues", vmin=0, vmax=H.max())
        ax.set_title(f"Water depth (t = {t})")
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=150)
    print(f"saved plot to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
