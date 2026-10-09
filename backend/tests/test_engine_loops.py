"""Bit-identity of the plain-Python loop engine (simulation/engine_loops.py) with the live vectorized one.

The loop engine is the baseline of the vectorized-vs-loops timing comparison (docs/tcc-deviations.md
section 25), and that comparison is only fair if both compute the same thing. Exact equality, not allclose,
for the reason tests/test_engine_regression.py gives: section 18 found the engine amplifies a single-ulp
difference into ~0.2 m within ~50 steps. Both trajectories run free, each on its own output.
"""

import numpy as np
import pytest

import simulation.engine as engine
import simulation.engine_loops as engine_loops

_INFLOW_CAP_SECONDS = 900.0  # api/routers/simulations.py::_run_gauge_driven's cap


def _closed_bowl():
    rows, cols = 12, 12
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    Z = ((x - cols / 2) ** 2 + (y - rows / 2) ** 2) / (rows * cols) + 0.3 * np.exp(-((x - 8) ** 2 + (y - 4) ** 2) / 4)
    N = 0.03 + 0.04 * (x > cols / 2)
    H = np.zeros((rows, cols))
    H[2:5, 2:5] = 5.0
    return Z, H, N


@pytest.mark.parametrize("neighborhood", ["moore", "von_neumann"])
@pytest.mark.parametrize("outflow_fraction", [0.005, engine.DEFAULT_OUTFLOW_FRACTION, 0.5], ids=["1-substep", "default", "50-substeps"])
def test_loop_engine_is_bit_identical_closed_system(outflow_fraction, neighborhood):
    Z, H0, N = _closed_bowl()
    H_vec, H_loop = H0.copy(), H0.copy()
    for t in range(1, 31):
        H_vec = engine.step(Z, H_vec, N, outflow_fraction=outflow_fraction, neighborhood=neighborhood)
        H_loop = engine_loops.step(Z, H_loop, N, outflow_fraction=outflow_fraction, neighborhood=neighborhood)
        assert np.array_equal(H_loop, H_vec), f"H diverged at step {t}: max |diff| {np.abs(H_loop - H_vec).max()}"
    assert abs(H_loop.sum() - H0.sum()) < 1e-9
    # Guard against a vacuous pass: the pool must actually have spread.
    assert np.count_nonzero(H_loop > 1e-6) > np.count_nonzero(H0)


def _open_valley():
    """A smaller test_engine_regression.py::_synthetic_scenario: channelled valley, varying roughness,
    inflow on the north channel cells, an outlet on the south edge."""
    rows, cols = 16, 16
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    channel_col = cols / 2 + 2 * np.sin(y / 3)
    Z = 12.0 - 0.5 * y + 0.08 * (x - channel_col) ** 2
    N = 0.03 + 0.05 * (np.abs(x - channel_col) > 2)
    inflow_mask = np.zeros((rows, cols), dtype=bool)
    inflow_mask[0, int(channel_col[0, 0]) - 1: int(channel_col[0, 0]) + 2] = True
    boundary_elevation = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    outlet_col = int(channel_col[-1, 0]) + 1
    boundary_elevation[-1, outlet_col - 1: outlet_col + 2] = Z[-1].min() - 2.0
    boundary_roughness = np.pad(N, 1, mode="constant", constant_values=1.0)
    boundary_roughness[-1, outlet_col - 1: outlet_col + 2] = 0.04
    return Z, N, 30.0, inflow_mask, boundary_elevation, boundary_roughness


@pytest.mark.parametrize("neighborhood", ["moore", "von_neumann"])
def test_loop_engine_is_bit_identical_open_system(neighborhood):
    """The gauge-driven macro step (CFL dt, inflow, outlet), with dt from the vectorized trajectory fed
    to both so the comparison isolates step()."""
    Z, N, dx, inflow_mask, boundary_elevation, boundary_roughness = _open_valley()
    H_vec = np.zeros_like(Z)
    H_loop = np.zeros_like(Z)
    left_through_outlet = 0.0
    for t in range(1, 51):
        dt_cfl = engine.compute_stable_dt(Z, H_vec, N, dx, neighborhood=neighborhood)
        dt = min(dt_cfl, _INFLOW_CAP_SECONDS)
        f_eff = engine.outflow_fraction_for_dt(engine.DEFAULT_OUTFLOW_FRACTION, dt, dt_cfl)
        inflow = np.zeros_like(Z)
        inflow[inflow_mask] = 50.0 * dt / (inflow_mask.sum() * dx**2)
        kwargs = dict(
            outflow_fraction=f_eff,
            inflow=inflow,
            boundary_elevation=boundary_elevation,
            boundary_roughness=boundary_roughness,
            neighborhood=neighborhood,
        )
        volume_before = H_vec.sum()
        H_vec = engine.step(Z, H_vec, N, **kwargs)
        H_loop = engine_loops.step(Z, H_loop, N, **kwargs)
        assert np.array_equal(H_loop, H_vec), f"H diverged at step {t}: max |diff| {np.abs(H_loop - H_vec).max()}"
        left_through_outlet += volume_before + inflow.sum() - H_vec.sum()
    # Non-vacuous: water entered, spread down the valley, and some left through the outlet.
    assert (H_loop > 0.01).sum() > inflow_mask.sum()
    assert left_through_outlet > 0


def test_loop_engine_validates_like_the_engine():
    Z, H, N = _closed_bowl()
    with pytest.raises(ValueError):
        engine_loops.step(Z, H, N, outflow_fraction=0.0)
    with pytest.raises(ValueError):
        engine_loops.step(Z, H, np.zeros_like(N))
    with pytest.raises(ValueError):
        engine_loops.step(Z, H, N, neighborhood="hex")
