"""Bit-identity of the fused-kernel CuPy engine (simulation/engine_cupy_fused.py) with the NumPy engine.

Skipped without CuPy or a CUDA device (CuPy is an optional dependency, docs/tcc-deviations.md section 18).
Exact equality, as in tests/test_engine_loops.py. dt is computed on the host by NumPy from the NumPy
trajectory and fed to both engines: section 18 found `compute_stable_dt` itself can differ by one ulp
across backends (its `power`), which would make the trajectories separate for a reason unrelated to
the fused step.
"""

import numpy as np
import pytest

import simulation.engine as engine
from tests.test_engine_loops import _INFLOW_CAP_SECONDS, _closed_bowl, _open_valley

cp = pytest.importorskip("cupy")
try:
    cp.cuda.runtime.getDeviceCount()
except cp.cuda.runtime.CUDARuntimeError:  # pragma: no cover - machine-dependent
    pytest.skip("no CUDA device", allow_module_level=True)

import simulation.engine_cupy_fused as fused  # noqa: E402


@pytest.mark.parametrize("neighborhood", ["moore", "von_neumann"])
@pytest.mark.parametrize("outflow_fraction", [0.005, engine.DEFAULT_OUTFLOW_FRACTION, 0.5], ids=["1-substep", "default", "50-substeps"])
def test_fused_engine_is_bit_identical_closed_system(outflow_fraction, neighborhood):
    Z, H0, N = _closed_bowl()
    Z_dev, N_dev = cp.asarray(Z), cp.asarray(N)
    H_np, H_dev = H0.copy(), cp.asarray(H0)
    for t in range(1, 101):
        H_np = engine.step(Z, H_np, N, outflow_fraction=outflow_fraction, neighborhood=neighborhood)
        H_dev = fused.step(Z_dev, H_dev, N_dev, outflow_fraction=outflow_fraction, neighborhood=neighborhood)
        H_got = cp.asnumpy(H_dev)
        assert np.array_equal(H_got, H_np), f"H diverged at step {t}: max |diff| {np.abs(H_got - H_np).max()}"
    assert np.count_nonzero(H_np > 1e-6) > np.count_nonzero(H0)


@pytest.mark.parametrize("neighborhood", ["moore", "von_neumann"])
def test_fused_engine_is_bit_identical_open_system(neighborhood):
    """500 gauge-style macro steps with inflow and an outlet."""
    Z, N, dx, inflow_mask, boundary_elevation, boundary_roughness = _open_valley()
    Z_dev, N_dev = cp.asarray(Z), cp.asarray(N)
    be_dev, br_dev = cp.asarray(boundary_elevation), cp.asarray(boundary_roughness)
    H_np = np.zeros_like(Z)
    H_dev = cp.zeros_like(Z_dev)
    for t in range(1, 501):
        dt_cfl = engine.compute_stable_dt(Z, H_np, N, dx, neighborhood=neighborhood)
        dt = min(dt_cfl, _INFLOW_CAP_SECONDS)
        f_eff = engine.outflow_fraction_for_dt(engine.DEFAULT_OUTFLOW_FRACTION, dt, dt_cfl)
        inflow = np.zeros_like(Z)
        inflow[inflow_mask] = 50.0 * dt / (inflow_mask.sum() * dx**2)
        H_np = engine.step(
            Z, H_np, N, outflow_fraction=f_eff, inflow=inflow,
            boundary_elevation=boundary_elevation, boundary_roughness=boundary_roughness, neighborhood=neighborhood,
        )
        H_dev = fused.step(
            Z_dev, H_dev, N_dev, outflow_fraction=f_eff, inflow=cp.asarray(inflow),
            boundary_elevation=be_dev, boundary_roughness=br_dev, neighborhood=neighborhood,
        )
        H_got = cp.asnumpy(H_dev)
        assert np.array_equal(H_got, H_np), f"H diverged at step {t}: max |diff| {np.abs(H_got - H_np).max()}"
    assert (H_np > 0.01).sum() > inflow_mask.sum()


def test_fused_engine_matches_on_a_non_square_grid_with_default_walls():
    """Exercises the kernels' row/column indexing on rows != cols, without boundary overrides."""
    rng = np.random.default_rng(0)
    Z = rng.uniform(0, 5, size=(23, 41))
    N = rng.uniform(0.02, 0.1, size=Z.shape)
    H = rng.uniform(0, 2, size=Z.shape)
    expected = engine.step(Z, H, N)
    got = cp.asnumpy(fused.step(cp.asarray(Z), cp.asarray(H), cp.asarray(N)))
    assert np.array_equal(got, expected)
