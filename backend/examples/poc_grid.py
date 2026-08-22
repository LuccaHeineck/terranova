"""Small artificial-grid proof of concept for the CA flood engine.

Builds a synthetic terrain (one hill acting as a barrier, one basin where
water should pool), drops a concentrated pool of water at the basin, runs
the engine for a fixed number of closed-system steps (no rain, no
infiltration), and checks that mass is conserved and depth never goes
negative. Saves a before/after plot for a quick visual sanity check.

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


def synthetic_terrain(rows: int, cols: int) -> np.ndarray:
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    cy, cx = rows / 2, cols / 2
    basin = ((x - cx) ** 2 + (y - cy) ** 2) / (rows * cols) * 3.0
    hill = 2.0 * np.exp(
        -(((x - cols * 0.3) ** 2 + (y - rows * 0.35) ** 2) / (2 * (cols * 0.1) ** 2))
    )
    return basin + hill


def seed_pool(H: np.ndarray, volume: float) -> None:
    rows, cols = H.shape
    cy, cx = rows // 2, cols // 2
    patch = H[cy - 2: cy + 3, cx - 2: cx + 3]
    patch[:] = volume / patch.size


def main() -> None:
    Z = synthetic_terrain(GRID_SIZE, GRID_SIZE)
    H = np.zeros((GRID_SIZE, GRID_SIZE))
    seed_pool(H, SEED_VOLUME)

    initial_volume = H.sum()

    start = time.perf_counter()
    for t in range(STEPS):
        H = step(Z, H)
        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        assert abs(H.sum() - initial_volume) < 1e-6, (
            f"volume drifted at step {t}: {H.sum()} vs {initial_volume}"
        )
    elapsed = time.perf_counter() - start

    flooded = H > 1e-6
    print(f"discrete steps simulated: {STEPS}")
    print(f"flooded cells: {flooded.sum()}")
    print(f"average depth over flooded cells: {H[flooded].mean():.4f}")
    print(f"total volume (conservation check): {H.sum():.4f} (initial: {initial_volume:.4f})")
    print(f"execution time: {elapsed:.4f} s")

    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    axes[0].imshow(Z, cmap="terrain")
    axes[0].set_title("Terrain (t = 0)")
    axes[1].imshow(H, cmap="Blues")
    axes[1].set_title(f"Water depth (t = {STEPS})")
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=150)
    print(f"saved plot to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
