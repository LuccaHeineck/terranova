"""Bit-identity regression: the live engine's default (Moore) path vs. a frozen copy of the engine as it
was before the neighborhood option existed (tests/engine_moore_reference.py).

Exact equality, not allclose, on purpose: docs/tcc-deviations.md section 18 found that the engine amplifies
a single-ulp difference in H or dt into ~0.2 m within ~50 steps, so "close" at step 1 says nothing about
step 500. Both trajectories run free from the same initial state, each on its own output, through the same
gauge-driven macro step the API and examples/validate_may2024.py use (CFL dt, 900s cap,
outflow_fraction_for_dt, boundary inflow, outlet).
"""

from pathlib import Path

import numpy as np
import pytest

import simulation.engine as engine
import tests.engine_moore_reference as reference
from config import settings

_INFLOW_CAP_SECONDS = 900.0  # api/routers/simulations.py::_run_gauge_driven's cap


def _gauge_step(module, Z, H, N, dx, inflow_for_dt, boundary_elevation, boundary_roughness, **neighborhood):
    dt_cfl = module.compute_stable_dt(Z, H, N, dx, **neighborhood)
    dt = min(dt_cfl, _INFLOW_CAP_SECONDS)
    H = module.step(
        Z,
        H,
        N,
        outflow_fraction=module.outflow_fraction_for_dt(engine.DEFAULT_OUTFLOW_FRACTION, dt, dt_cfl),
        inflow=inflow_for_dt(dt),
        boundary_elevation=boundary_elevation,
        boundary_roughness=boundary_roughness,
        **neighborhood,
    )
    return H, dt_cfl


def _assert_identical_trajectories(Z, N, dx, inflow_for_dt, boundary_elevation, boundary_roughness, n_steps, **neighborhood):
    H_ref = np.zeros_like(Z)
    H_new = np.zeros_like(Z)
    wet_steps = 0
    for t in range(1, n_steps + 1):
        H_ref, dt_ref = _gauge_step(reference, Z, H_ref, N, dx, inflow_for_dt, boundary_elevation, boundary_roughness)
        H_new, dt_new = _gauge_step(
            engine, Z, H_new, N, dx, inflow_for_dt, boundary_elevation, boundary_roughness, **neighborhood
        )
        assert dt_new == dt_ref, f"dt diverged at step {t}: {dt_new!r} vs {dt_ref!r}"
        assert np.array_equal(H_new, H_ref), f"H diverged at step {t}: max |diff| {np.abs(H_new - H_ref).max()}"
        wet_steps += bool((H_ref > 0.01).any())
    # Guard against a vacuous pass (e.g. water never entering the grid).
    assert wet_steps > n_steps // 2


def _synthetic_scenario():
    """A 40x40 north-high/south-low valley with a meandering low channel, spatially varying roughness,
    inflow along the north edge's channel cells and an outlet on the south edge - small, but exercising
    every path the real gauge-driven loop does."""
    rows, cols = 40, 40
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    channel_col = cols / 2 + 6 * np.sin(y / 6)
    Z = 30.0 - 0.5 * y + 0.08 * (x - channel_col) ** 2
    N = 0.03 + 0.05 * (np.abs(x - channel_col) > 3)
    inflow_mask = np.zeros((rows, cols), dtype=bool)
    inflow_mask[0, int(channel_col[0, 0]) - 1: int(channel_col[0, 0]) + 2] = True
    boundary_elevation = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    outlet_col = int(channel_col[-1, 0]) + 1
    boundary_elevation[-1, outlet_col - 1: outlet_col + 2] = Z[-1].min() - 2.0
    boundary_roughness = np.pad(N, 1, mode="constant", constant_values=1.0)
    boundary_roughness[-1, outlet_col - 1: outlet_col + 2] = 0.04
    dx = 30.0

    def inflow_for_dt(dt):
        # 50 m3/s spread over the inflow cells, as depth added over dt (ingestion.hydrograph.discharge_to_inflow).
        inflow = np.zeros((rows, cols))
        inflow[inflow_mask] = 50.0 * dt / (inflow_mask.sum() * dx**2)
        return inflow

    return Z, N, dx, inflow_for_dt, boundary_elevation, boundary_roughness


@pytest.mark.parametrize("neighborhood", [{}, {"neighborhood": "moore"}], ids=["default", "explicit-moore"])
def test_moore_path_is_bit_identical_to_the_pre_change_engine_synthetic(neighborhood):
    if neighborhood and "neighborhood" not in engine.step.__code__.co_varnames:
        pytest.skip("engine has no neighborhood parameter yet")
    _assert_identical_trajectories(*_synthetic_scenario(), n_steps=500, **neighborhood)


_RAW_FILES = [settings.DEM_RAW_PATH, settings.LANDCOVER_RAW_PATH, settings.HYDROGRAPH_RAW_PATH]


@pytest.mark.skipif(not all(Path(p).exists() for p in _RAW_FILES), reason="real May 2024 raw data not downloaded")
@pytest.mark.parametrize("neighborhood", [{}, {"neighborhood": "moore"}], ids=["default", "explicit-moore"])
def test_moore_path_is_bit_identical_to_the_pre_change_engine_real_may2024(neighborhood):
    """1,000 real gauge-driven steps on the 90m validation grid (real terrain, roughness, hydrograph,
    inflow edge and outlet). Rebuilds data/processed/*_90m.tif as a side effect, like test_fast_engine.py's
    May 2024 regression."""
    if neighborhood and "neighborhood" not in engine.step.__code__.co_varnames:
        pytest.skip("engine has no neighborhood parameter yet")
    from ingestion.dem import build_elevation_matrix
    from ingestion.hydrograph import build_hydrograph, discharge_to_inflow, find_boundary_inflow_mask, find_boundary_outlet
    from ingestion.landcover import build_roughness_matrix

    Z = build_elevation_matrix(
        processed_path=settings.DEM_VALIDATION_PROCESSED_PATH, resolution=settings.VALIDATION_RESOLUTION_METERS
    )
    N = build_roughness_matrix(
        reference_path=settings.DEM_VALIDATION_PROCESSED_PATH,
        processed_path=settings.LANDCOVER_VALIDATION_PROCESSED_PATH,
    )
    dx = settings.VALIDATION_RESOLUTION_METERS
    hydrograph = build_hydrograph()
    inflow_mask = find_boundary_inflow_mask(Z, settings.HYDROGRAPH_INFLOW_EDGE)
    boundary_elevation, boundary_roughness = find_boundary_outlet(Z, N, settings.HYDROGRAPH_OUTLET_EDGE)

    # Both trajectories must read the hydrograph at the same elapsed time each step; since their dts are
    # asserted equal every step, one shared clock advanced by the reference's dt is exact for both.
    clock = {"elapsed": 0.0, "calls": 0}

    def inflow_for_dt(dt):
        inflow = discharge_to_inflow(hydrograph.discharge_at(clock["elapsed"]), dt, inflow_mask, dx**2)
        clock["calls"] += 1
        if clock["calls"] % 2 == 0:  # the reference, then the live engine: advance after both
            clock["elapsed"] += dt
        return inflow

    _assert_identical_trajectories(
        Z, N, dx, inflow_for_dt, boundary_elevation, boundary_roughness, n_steps=1000, **neighborhood
    )
