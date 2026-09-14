"""Real-DEM, real-roughness proof of concept for the CA flood engine (roadmap
steps 3-4).

Loads the real Lajeado/Estrela elevation matrix built by `ingestion.dem` (run
`scripts/download_dem.py` first to fetch the raw tile) and the real Manning
roughness matrix built by `ingestion.landcover` from MapBiomas land-cover data
(run `scripts/download_landcover.py` first), seeds a concentrated water pool
at the terrain's lowest point (the river channel), then runs
`simulation.engine.step` for a fixed number of closed-system steps exactly
like `poc_grid.py` does - proving the already-validated engine behaves
correctly on real terrain with real roughness, not just synthetic Gaussian
bumps or a uniform `N`.

Water depth is still an abstract per-cell quantity, not true cubic meters -
the engine has no concept of cell area/dx yet (see docs/project-plan.md's
step-2 notes) - so "volume" here means "sum of the H array", same as the
synthetic PoC.

Run from the backend/ directory with the venv active:
    python -m examples.poc_real_dem
"""

import time

import matplotlib.pyplot as plt
import numpy as np

from config import settings
from ingestion.dem import build_elevation_matrix
from ingestion.landcover import build_roughness_matrix
from simulation.engine import compute_stable_dt, seed_pool_at_lowest_point, step

STEPS = 100
SEED_VOLUME = 400.0
OUTPUT_PATH = "poc_real_dem_result.png"
SNAPSHOT_STEPS = (0, 5, 10, 15, 50)


def main() -> None:
    if not settings.DEM_RAW_PATH.exists():
        raise FileNotFoundError(
            f"{settings.DEM_RAW_PATH} not found - run "
            "`.venv/bin/python -m scripts.download_dem` first."
        )
    if not settings.LANDCOVER_RAW_PATH.exists():
        raise FileNotFoundError(
            f"{settings.LANDCOVER_RAW_PATH} not found - run "
            "`.venv/bin/python -m scripts.download_landcover` first."
        )

    Z = build_elevation_matrix()
    N = build_roughness_matrix()
    H = np.zeros_like(Z)
    seed_pool_at_lowest_point(Z, H, SEED_VOLUME)

    initial_volume = H.sum()
    snapshots = {}
    if 0 in SNAPSHOT_STEPS:
        snapshots[0] = H.copy()

    elapsed_time = 0.0
    dt_values = []

    start = time.perf_counter()
    for t in range(1, STEPS + 1):
        dt = compute_stable_dt(Z, H, N, dx=settings.TARGET_RESOLUTION_METERS)
        H = step(Z, H, N)
        elapsed_time += dt
        dt_values.append(dt)
        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        assert abs(H.sum() - initial_volume) < 1e-6, (
            f"volume drifted at step {t}: {H.sum()} vs {initial_volume}"
        )
        if t in SNAPSHOT_STEPS:
            snapshots[t] = H.copy()
            print(f"step {t}: dt={dt:.2f}s, elapsed={elapsed_time / 60:.1f} min")
    elapsed = time.perf_counter() - start

    flooded = H > 1e-6
    print(f"grid shape: {Z.shape}")
    print(f"discrete steps simulated: {STEPS}")
    print(f"flooded cells: {flooded.sum()}")
    print(f"average depth over flooded cells: {H[flooded].mean():.4f}")
    print(f"total volume (conservation check): {H.sum():.4f} (initial: {initial_volume:.4f})")
    print(f"total simulated elapsed time: {elapsed_time / 60:.1f} min over {STEPS} discrete steps")
    print(f"dt range across run: {min(dt_values):.2f}s - {max(dt_values):.2f}s")
    print(f"execution time: {elapsed:.4f} s")

    n_panels = 1 + len(SNAPSHOT_STEPS)
    fig, axes = plt.subplots(1, n_panels, figsize=(5 * n_panels, 5))
    axes[0].imshow(Z, cmap="terrain")
    axes[0].set_title("Real terrain (Lajeado/Estrela)")
    for ax, t in zip(axes[1:], SNAPSHOT_STEPS):
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
