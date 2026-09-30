import math
from unittest import mock

import numpy as np
import pytest

import simulation.engine as engine
from simulation.engine import compute_stable_dt, outflow_fraction_for_dt, seed_pool_at, seed_pool_at_lowest_point, step


def test_mass_conservation_and_nonnegative_depth():
    """Regression of the ad hoc checks from examples/poc_grid.py: over many
    steps, in a closed system, total volume must stay exactly constant and
    depth must never go negative."""
    rows, cols = 20, 20
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    Z = ((x - cols / 2) ** 2 + (y - rows / 2) ** 2) / (rows * cols)
    N = np.full((rows, cols), 0.05)
    H = np.zeros((rows, cols))
    H[rows // 2 - 1: rows // 2 + 2, cols // 2 - 1: cols // 2 + 2] = 5.0
    initial_volume = H.sum()

    for t in range(50):
        H = step(Z, H, N)
        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        assert abs(H.sum() - initial_volume) < 1e-6, (
            f"volume drifted at step {t}: {H.sum()} vs {initial_volume}"
        )


def test_step_rejects_nonpositive_roughness():
    rows, cols = 5, 5
    Z = np.zeros((rows, cols))
    H = np.zeros((rows, cols))
    H[2, 2] = 1.0
    N = np.full((rows, cols), 0.05)
    N[3, 3] = 0.0

    with pytest.raises(ValueError):
        step(Z, H, N)


def test_step_rejects_invalid_outflow_fraction():
    rows, cols = 3, 3
    Z = np.zeros((rows, cols))
    H = np.zeros((rows, cols))
    N = np.full((rows, cols), 0.05)

    with pytest.raises(ValueError):
        step(Z, H, N, outflow_fraction=0.0)
    with pytest.raises(ValueError):
        step(Z, H, N, outflow_fraction=1.5)


def test_manning_roughness_steers_flow_toward_smoother_neighbor():
    """Two downhill neighbors at equal slope and distance (both orthogonal,
    same elevation drop) but different roughness: more volume should flow
    toward the smoother (lower-N) one."""
    rows, cols = 3, 3
    Z = np.full((rows, cols), 10.0)
    Z[0, 1] = 0.0  # north neighbor: downhill
    Z[1, 2] = 0.0  # east neighbor: equally downhill (same drop, same distance)

    N = np.full((rows, cols), 0.05)
    N[0, 1] = 0.02  # smoother north neighbor
    N[1, 2] = 0.08  # rougher east neighbor

    H = np.zeros((rows, cols))
    H[1, 1] = 10.0

    H_after = step(Z, H, N, outflow_fraction=0.1)

    assert H_after[0, 1] > H_after[1, 2], (
        "more water should flow toward the smoother (lower-N) neighbor"
    )


def test_no_checkerboard_artifact_with_varying_roughness():
    """Regression for the checkerboard/speckle instability fixed this
    session: confirms a spatially-varying N (a new multiplicative term in
    the weights) doesn't reintroduce it. Uses the same neighbor-roughness
    metric used to diagnose the original bug."""
    rows, cols = 40, 40
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    cy, cx = rows / 2, cols / 2
    Z = ((x - cx) ** 2 + (y - cy) ** 2) / (rows * cols) * 3.0
    diagonal = (x - y) / max(rows, cols)
    N = 0.09 - 0.07 * np.exp(-(diagonal ** 2) / (2 * 0.15 ** 2))

    H = np.zeros((rows, cols))
    cy_i, cx_i = rows // 2, cols // 2
    H[cy_i - 2: cy_i + 3, cx_i - 2: cx_i + 3] = 400.0 / 25

    for _ in range(60):
        H = step(Z, H, N)

    padded = np.pad(H, 1, mode="edge")
    neighbor_mean = sum(
        padded[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols]
        for dr in (-1, 0, 1) for dc in (-1, 0, 1) if not (dr == 0 and dc == 0)
    ) / 8.0
    flooded = H > 1e-6
    roughness = np.abs(H[flooded] - neighbor_mean[flooded]).mean()

    assert roughness < 0.05, f"speckle artifact detected: roughness={roughness:.5f}"


def test_inflow_adds_exact_volume_and_stays_nonnegative():
    """An open system (constant per-step inflow at one cell): total volume
    must grow by exactly the injected amount each step, and depth must still
    never go negative."""
    rows, cols = 10, 10
    Z = np.zeros((rows, cols))
    N = np.full((rows, cols), 0.05)
    H = np.zeros((rows, cols))

    inflow = np.zeros((rows, cols))
    inflow[0, 3] = 2.0  # off-center edge cell

    initial_volume = H.sum()
    for t in range(1, 21):
        H = step(Z, H, N, inflow=inflow)
        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        expected = initial_volume + t * inflow.sum()
        assert H.sum() == pytest.approx(expected), (
            f"volume mismatch at step {t}: {H.sum()} vs {expected}"
        )


def test_step_rejects_mismatched_inflow_shape():
    rows, cols = 5, 5
    Z = np.zeros((rows, cols))
    H = np.zeros((rows, cols))
    N = np.full((rows, cols), 0.05)
    inflow = np.zeros((rows + 1, cols))

    with pytest.raises(ValueError):
        step(Z, H, N, inflow=inflow)


def test_step_rejects_negative_inflow():
    rows, cols = 5, 5
    Z = np.zeros((rows, cols))
    H = np.zeros((rows, cols))
    N = np.full((rows, cols), 0.05)
    inflow = np.zeros((rows, cols))
    inflow[2, 2] = -1.0

    with pytest.raises(ValueError):
        step(Z, H, N, inflow=inflow)


def test_inflow_propagates_downhill_from_injection_point():
    """Water injected at an edge cell on sloped terrain should spread to its
    downhill neighbor over subsequent steps, not stay stuck at the
    injection point."""
    rows, cols = 5, 5
    Z = np.zeros((rows, cols))
    Z[0, :] = 10.0  # top row is high ground
    for r in range(1, rows):
        Z[r, :] = 10.0 - r  # slopes down away from the top edge

    N = np.full((rows, cols), 0.05)
    H = np.zeros((rows, cols))
    inflow = np.zeros((rows, cols))
    inflow[0, 2] = 5.0

    for _ in range(5):
        H = step(Z, H, N, inflow=inflow)

    assert H[1, 2] > 0.0, "water should have spread downhill from the injection point"


def test_default_boundary_params_reproduce_wall_behavior():
    """Explicitly constructing the same all-wall padded arrays `step()` builds
    internally by default (`boundary_elevation`/`boundary_roughness` omitted)
    and passing them in must reproduce byte-identical output - proves the new
    override mechanism is a strict superset of the old behavior, not a
    separate code path that happens to agree."""
    rows, cols = 10, 10
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    Z = ((x - cols / 2) ** 2 + (y - rows / 2) ** 2) / (rows * cols)
    N = np.full((rows, cols), 0.05)
    H = np.zeros((rows, cols))
    H[4:7, 4:7] = 5.0

    boundary_elevation = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    boundary_roughness = np.pad(N, 1, mode="constant", constant_values=1.0)

    H_default = step(Z, H.copy(), N)
    H_explicit = step(Z, H.copy(), N, boundary_elevation=boundary_elevation, boundary_roughness=boundary_roughness)

    np.testing.assert_array_equal(H_default, H_explicit)


def test_boundary_outlet_drains_volume_over_time():
    """A closed basin except for one designated low-elevation outlet cell on
    its south edge: water should actually leave the domain over time (total
    volume strictly decreasing, with no inflow to offset it), unlike the
    default all-wall boundary where volume stays exactly constant."""
    rows, cols = 8, 8
    Z = np.zeros((rows, cols))
    N = np.full((rows, cols), 0.05)
    H = np.zeros((rows, cols))
    H[3:5, 3:5] = 10.0
    initial_volume = H.sum()

    boundary_elevation = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    boundary_elevation[-1, 4] = -5.0  # one outlet cell, south edge, below any real terrain
    boundary_roughness = np.pad(N, 1, mode="constant", constant_values=1.0)
    boundary_roughness[-1, 4] = 0.04  # water's own Manning's n, not the wall placeholder

    for t in range(30):
        H = step(Z, H, N, boundary_elevation=boundary_elevation, boundary_roughness=boundary_roughness)
        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"

    assert H.sum() < initial_volume, "volume should have decreased through the outlet"


def test_boundary_outlet_mass_balance_is_exact():
    """The caller-side bookkeeping invariant (no new return value from step()
    itself): summing `H_before.sum() - H_after.sum()` every step must exactly
    equal how much total volume was actually lost, to floating-point
    precision - proving outflow can be tracked exactly without step() needing
    to report it directly."""
    rows, cols = 8, 8
    Z = np.zeros((rows, cols))
    N = np.full((rows, cols), 0.05)
    H = np.zeros((rows, cols))
    H[3:5, 3:5] = 10.0
    initial_volume = H.sum()

    boundary_elevation = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    boundary_elevation[-1, 4] = -5.0
    boundary_roughness = np.pad(N, 1, mode="constant", constant_values=1.0)
    boundary_roughness[-1, 4] = 0.04

    cumulative_outflow = 0.0
    for _ in range(30):
        before = H.sum()
        H = step(Z, H, N, boundary_elevation=boundary_elevation, boundary_roughness=boundary_roughness)
        cumulative_outflow += before - H.sum()

    assert H.sum() == pytest.approx(initial_volume - cumulative_outflow)


def test_step_rejects_wrong_shape_boundary_overrides():
    rows, cols = 5, 5
    Z = np.zeros((rows, cols))
    H = np.zeros((rows, cols))
    N = np.full((rows, cols), 0.05)

    with pytest.raises(ValueError):
        step(Z, H, N, boundary_elevation=np.zeros((rows, cols)))  # missing the +2 padding
    with pytest.raises(ValueError):
        step(Z, H, N, boundary_roughness=np.zeros((rows, cols)))


def test_step_rejects_nonpositive_boundary_roughness():
    rows, cols = 5, 5
    Z = np.zeros((rows, cols))
    H = np.zeros((rows, cols))
    N = np.full((rows, cols), 0.05)
    boundary_roughness = np.pad(N, 1, mode="constant", constant_values=1.0)
    boundary_roughness[-1, 2] = 0.0

    with pytest.raises(ValueError):
        step(Z, H, N, boundary_roughness=boundary_roughness)


def test_seed_pool_at_lowest_point_seeds_full_volume_at_the_minimum():
    rows, cols = 10, 10
    Z = np.full((rows, cols), 10.0)
    Z[7, 3] = 0.0  # the terrain's lowest point, off-center on purpose
    H = np.zeros((rows, cols))

    seed_pool_at_lowest_point(Z, H, volume=50.0)

    assert H.sum() == pytest.approx(50.0)
    assert H[7, 3] > 0.0


def _single_downhill_neighbor_grid(drop: float, depth: float):
    """3x3 grid with exactly one downhill neighbor (north of center, orthogonal,
    distance 1): every other neighbor is higher than the center, so it
    contributes zero slope/velocity and can't affect the result. Only the
    center cell has nonzero depth, so it's the only cell with nonzero velocity
    - this makes the grid's `v_max` fully determined by one known cell/direction,
    which is what makes a hand-derived expected value possible."""
    rows, cols = 3, 3
    Z = np.full((rows, cols), 20.0)  # every other neighbor: fixed, safely higher than center
    Z[1, 1] = drop  # center
    Z[0, 1] = 0.0  # north neighbor: downhill from center by exactly `drop`
    N = np.full((rows, cols), 0.05)
    H = np.zeros((rows, cols))
    H[1, 1] = depth
    return Z, H, N


def test_compute_stable_dt_matches_hand_derived_value():
    """Proves the formula is wired correctly end-to-end (dx placement, sqrt,
    exponent, courant factor) by comparing against a value computed
    independently via the textbook Manning/CFL formulas, not by calling any
    internals of compute_stable_dt itself. Slope drives off water surface
    elevation (Z + H), matching step()'s own WSE-based transition rule - the
    north neighbor here is dry, so its WSE is just its bare Z."""
    drop, depth, n, dx = 5.0, 2.0, 0.05, 30.0
    Z, H, N = _single_downhill_neighbor_grid(drop, depth)

    wse_drop = (drop + depth) - 0.0  # (Z_center + H_center) - (Z_north + H_north)
    slope = wse_drop / (1.0 * dx)  # orthogonal neighbor, distance = 1 cell
    v_max = (1.0 / n) * depth ** (2.0 / 3.0) * math.sqrt(slope)
    expected_dt = 1.0 * dx / v_max  # courant_number default = 1.0

    assert compute_stable_dt(Z, H, N, dx=dx) == pytest.approx(expected_dt)


def test_compute_stable_dt_shrinks_as_slope_steepens():
    """A steeper downhill drop means faster Manning velocity, so the CFL-
    stable dt must be smaller."""
    Z_gentle, H, N = _single_downhill_neighbor_grid(drop=1.0, depth=2.0)
    Z_steep, _, _ = _single_downhill_neighbor_grid(drop=8.0, depth=2.0)

    dt_gentle = compute_stable_dt(Z_gentle, H, N, dx=30.0)
    dt_steep = compute_stable_dt(Z_steep, H, N, dx=30.0)

    assert dt_steep < dt_gentle


def test_compute_stable_dt_shrinks_as_depth_increases():
    """Deeper water moves faster under Manning's equation (the h^(2/3) term),
    independent of slope, so the CFL-stable dt must be smaller."""
    Z, H_shallow, N = _single_downhill_neighbor_grid(drop=5.0, depth=0.5)
    _, H_deep, _ = _single_downhill_neighbor_grid(drop=5.0, depth=5.0)

    dt_shallow = compute_stable_dt(Z, H_shallow, N, dx=30.0)
    dt_deep = compute_stable_dt(Z, H_deep, N, dx=30.0)

    assert dt_deep < dt_shallow


def test_compute_stable_dt_scales_as_dx_to_the_three_halves():
    """Holding Z/H/N fixed, slope S is inversely proportional to dx, so
    velocity v ~ sqrt(S) is proportional to dx^(-1/2), making
    dt = courant*dx/v scale exactly as dx^(3/2) - an algebraic identity, not
    just an empirical trend."""
    Z, H, N = _single_downhill_neighbor_grid(drop=5.0, depth=2.0)

    dt_30 = compute_stable_dt(Z, H, N, dx=30.0)
    dt_120 = compute_stable_dt(Z, H, N, dx=120.0)

    assert dt_120 == pytest.approx(dt_30 * 4 ** 1.5)


def test_compute_stable_dt_scales_linearly_with_courant_number():
    """courant_number is a direct multiplier on the CFL bound - halving it
    must exactly halve the returned dt."""
    Z, H, N = _single_downhill_neighbor_grid(drop=5.0, depth=2.0)

    dt_full = compute_stable_dt(Z, H, N, dx=30.0, courant_number=1.0)
    dt_half = compute_stable_dt(Z, H, N, dx=30.0, courant_number=0.5)

    assert dt_half == pytest.approx(0.5 * dt_full)


def test_compute_stable_dt_returns_fallback_when_no_flow():
    """No cell has any downhill velocity (either no water at all, or water
    present but the surface is perfectly flat) - the CFL bound is vacuous
    (v_max == 0 would divide by zero), so a documented finite fallback must
    be returned instead of nan/inf/a crash."""
    rows, cols = 5, 5
    N = np.full((rows, cols), 0.05)

    dry_Z = np.zeros((rows, cols))
    dry_H = np.zeros((rows, cols))
    assert compute_stable_dt(dry_Z, dry_H, N, dx=30.0) == 3600.0

    flat_Z = np.zeros((rows, cols))
    flat_H = np.full((rows, cols), 3.0)  # water present, but WSE is flat everywhere
    assert compute_stable_dt(flat_Z, flat_H, N, dx=30.0) == 3600.0


def test_compute_stable_dt_rejects_nonpositive_dx():
    Z, H, N = _single_downhill_neighbor_grid(drop=5.0, depth=2.0)

    with pytest.raises(ValueError):
        compute_stable_dt(Z, H, N, dx=0.0)
    with pytest.raises(ValueError):
        compute_stable_dt(Z, H, N, dx=-30.0)


def test_compute_stable_dt_rejects_invalid_courant_number():
    Z, H, N = _single_downhill_neighbor_grid(drop=5.0, depth=2.0)

    with pytest.raises(ValueError):
        compute_stable_dt(Z, H, N, dx=30.0, courant_number=0.0)
    with pytest.raises(ValueError):
        compute_stable_dt(Z, H, N, dx=30.0, courant_number=1.5)


def test_compute_stable_dt_rejects_nonpositive_roughness():
    Z, H, N = _single_downhill_neighbor_grid(drop=5.0, depth=2.0)
    N[2, 2] = 0.0

    with pytest.raises(ValueError):
        compute_stable_dt(Z, H, N, dx=30.0)


def test_outflow_fraction_for_dt_returns_full_value_when_dt_equals_dt_cfl():
    """The calibration anchor: dt == dt_cfl must reproduce outflow_fraction
    exactly (today's byte-identical behavior in the uncapped/CFL-bound regime),
    not just approximately."""
    assert outflow_fraction_for_dt(0.5, dt=17.79, dt_cfl=17.79) == 0.5


def test_outflow_fraction_for_dt_scales_down_proportionally_when_dt_is_smaller_than_dt_cfl():
    result = outflow_fraction_for_dt(0.5, dt=0.25 * 900.0, dt_cfl=900.0)
    assert result == pytest.approx(0.25 * 0.5)


def test_outflow_fraction_for_dt_clamps_to_full_value_when_dt_exceeds_dt_cfl():
    """Defensive case: dt shouldn't normally exceed dt_cfl (it's derived as a
    bound on dt), but if it does, the result must not exceed the requested
    outflow_fraction."""
    assert outflow_fraction_for_dt(0.5, dt=200.0, dt_cfl=100.0) == 0.5


def test_outflow_fraction_for_dt_stays_strictly_positive_for_a_very_small_dt_ratio():
    result = outflow_fraction_for_dt(0.5, dt=1e-12, dt_cfl=1.0)
    assert result > 0.0


def test_outflow_fraction_for_dt_rejects_invalid_outflow_fraction():
    with pytest.raises(ValueError):
        outflow_fraction_for_dt(0.0, dt=1.0, dt_cfl=1.0)
    with pytest.raises(ValueError):
        outflow_fraction_for_dt(1.5, dt=1.0, dt_cfl=1.0)


def test_outflow_fraction_for_dt_rejects_nonpositive_dt():
    with pytest.raises(ValueError):
        outflow_fraction_for_dt(0.5, dt=0.0, dt_cfl=1.0)
    with pytest.raises(ValueError):
        outflow_fraction_for_dt(0.5, dt=-1.0, dt_cfl=1.0)


def test_outflow_fraction_for_dt_rejects_nonpositive_dt_cfl():
    with pytest.raises(ValueError):
        outflow_fraction_for_dt(0.5, dt=1.0, dt_cfl=0.0)
    with pytest.raises(ValueError):
        outflow_fraction_for_dt(0.5, dt=1.0, dt_cfl=-1.0)


def test_step_calls_fewer_substep_passes_for_a_smaller_outflow_fraction():
    """Proxy for the wall-clock win: a dt-scaled (smaller) outflow_fraction must
    result in strictly fewer internal _single_update passes than the unscaled
    default - the same call-count evidence cProfile used to diagnose the
    original bottleneck, made into a fast, deterministic regression test."""
    rows, cols = 10, 10
    Z = np.zeros((rows, cols))
    N = np.full((rows, cols), 0.05)
    H = np.zeros((rows, cols))
    H[4:7, 4:7] = 5.0

    with mock.patch("simulation.engine._single_update", wraps=engine._single_update) as spy:
        step(Z, H.copy(), N, outflow_fraction=0.5)
        full_calls = spy.call_count

    scaled_fraction = outflow_fraction_for_dt(0.5, dt=0.1, dt_cfl=1.0)
    with mock.patch("simulation.engine._single_update", wraps=engine._single_update) as spy:
        step(Z, H.copy(), N, outflow_fraction=scaled_fraction)
        scaled_calls = spy.call_count

    assert scaled_calls < full_calls


@pytest.mark.parametrize("dt_ratio", [1.0, 0.5, 0.1, 0.01])
def test_no_checkerboard_artifact_with_dt_scaled_outflow_fraction(dt_ratio):
    """Regression, extending test_no_checkerboard_artifact_with_varying_roughness:
    the dt-scaled outflow_fraction must not reintroduce the checkerboard/speckle
    instability at any dt ratio the new mechanism can actually produce.

    Macro-step count is scaled inversely with the resulting (smaller) fraction so
    every case gets a comparable *cumulative* amount of redistribution by the end
    - a fixed step count for all ratios was tried first and produced false
    positives: at a tiny fraction, 60 macro steps just hasn't moved much water
    yet, so the still-mostly-concentrated pool's sharp edge against its dry
    neighbors reads as "rough" under this metric even with zero real
    instability (confirmed by checking H.max()/flooded-cell-count alongside the
    metric during this test's own construction - not a checkerboard, just an
    under-spread pool). Scaling steps so cumulative fraction*n_steps stays
    comparable to the original 60-step/0.5-fraction case removes that
    confound and isolates the actual question: does a smaller per-macro-step
    release, at a comparable total amount of water moved, still avoid the
    speckle artifact. Capped at 4000 steps to keep the test fast; ratios
    smaller than 0.01 would need more steps than that to reach comparable
    spread and are covered instead by the monotonicity argument in
    outflow_fraction_for_dt's docstring (a smaller requested fraction can only
    ever produce an equal-or-smaller per-substep release than an
    already-validated larger one, never a larger one)."""
    rows, cols = 40, 40
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    cy, cx = rows / 2, cols / 2
    Z = ((x - cx) ** 2 + (y - cy) ** 2) / (rows * cols) * 3.0
    diagonal = (x - y) / max(rows, cols)
    N = 0.09 - 0.07 * np.exp(-(diagonal ** 2) / (2 * 0.15 ** 2))

    H = np.zeros((rows, cols))
    cy_i, cx_i = rows // 2, cols // 2
    H[cy_i - 2: cy_i + 3, cx_i - 2: cx_i + 3] = 400.0 / 25

    fraction = outflow_fraction_for_dt(0.5, dt=dt_ratio, dt_cfl=1.0)
    n_steps = min(max(60, round(30 / fraction)), 4000)
    for _ in range(n_steps):
        H = step(Z, H, N, outflow_fraction=fraction)

    padded = np.pad(H, 1, mode="edge")
    neighbor_mean = sum(
        padded[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols]
        for dr in (-1, 0, 1) for dc in (-1, 0, 1) if not (dr == 0 and dc == 0)
    ) / 8.0
    flooded = H > 1e-6
    roughness = np.abs(H[flooded] - neighbor_mean[flooded]).mean()

    assert roughness < 0.05, f"speckle artifact detected at dt_ratio={dt_ratio}: roughness={roughness:.5f}"


def test_step_output_identical_to_unscaled_outflow_fraction_when_dt_ratio_is_one():
    """Proves the calibration point is exact, not merely close - same spirit as
    test_default_boundary_params_reproduce_wall_behavior."""
    rows, cols = 10, 10
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    Z = ((x - cols / 2) ** 2 + (y - rows / 2) ** 2) / (rows * cols)
    N = np.full((rows, cols), 0.05)
    H = np.zeros((rows, cols))
    H[4:7, 4:7] = 5.0

    scaled_fraction = outflow_fraction_for_dt(0.5, dt=123.456, dt_cfl=123.456)

    H_default = step(Z, H.copy(), N, outflow_fraction=0.5)
    H_scaled = step(Z, H.copy(), N, outflow_fraction=scaled_fraction)

    np.testing.assert_array_equal(H_default, H_scaled)


def test_max_stable_substep_fraction_stays_at_the_real_data_validated_value():
    """Pins _MAX_STABLE_SUBSTEP_FRACTION at its original 0.01, not the 0.02 a
    roadmap-step-11 performance pass tried and reverted: raising it to 0.02
    passed both of this file's calibrated synthetic checkerboard regressions
    (this test's own flat-water control included), but produced a real,
    visible mottled/branching artifact on an actual gauge-driven run against
    real terrain around step 60000 - a scenario neither synthetic grid here
    reproduces (continuous real boundary inflow through a few channel cells,
    real heterogeneous roughness, tens of thousands of steps). See engine.py's
    comment on this constant and docs/tcc-deviations.md for the full writeup
    of the investigation that caught it. This test exists so
    a future change to this constant can't silently reintroduce that already-
    seen failure mode without a human re-running the same real-terrain check -
    passing the synthetic scenarios below is necessary but was already proven
    insufficient on its own."""
    assert engine._MAX_STABLE_SUBSTEP_FRACTION == pytest.approx(0.01)

    # Flat-water-everywhere control (the original step-1 diagnostic test,
    # stricter than the varying-roughness grid below).
    rows, cols = 20, 20
    Z = np.zeros((rows, cols))
    N = np.full((rows, cols), 0.05)
    H = np.full((rows, cols), 2.0)
    H[10, 10] += 0.5
    for _ in range(30):
        H = step(Z, H, N)
    padded = np.pad(H, 1, mode="edge")
    neighbor_mean = sum(
        padded[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols]
        for dr in (-1, 0, 1) for dc in (-1, 0, 1) if not (dr == 0 and dc == 0)
    ) / 8.0
    flooded = H > 1e-6
    roughness = np.abs(H[flooded] - neighbor_mean[flooded]).mean()
    assert roughness < 0.05, f"flat-water control regression: roughness={roughness:.5f}"


def test_seed_pool_at_centers_a_5x5_patch_on_the_chosen_cell():
    H = np.zeros((10, 10))

    seed_pool_at(H, volume=50.0, row=4, col=6)

    assert H.sum() == pytest.approx(50.0)
    assert np.array_equal(np.argwhere(H > 0).min(axis=0), [2, 4])
    assert np.array_equal(np.argwhere(H > 0).max(axis=0), [6, 8])


def test_seed_pool_at_clips_the_patch_at_an_edge_instead_of_moving_it():
    H = np.zeros((10, 10))

    seed_pool_at(H, volume=50.0, row=0, col=9)

    assert H.sum() == pytest.approx(50.0)
    # The 3x3 corner remnant of the patch, still around (0, 9) - not shifted inward.
    assert np.array_equal(np.argwhere(H > 0).min(axis=0), [0, 7])
    assert np.array_equal(np.argwhere(H > 0).max(axis=0), [2, 9])


def test_seed_pool_at_rejects_a_cell_outside_the_grid():
    with pytest.raises(ValueError):
        seed_pool_at(np.zeros((10, 10)), volume=50.0, row=10, col=0)


# --- neighborhood option (docs/tcc-deviations.md section 22) -----------------------------------------------

NEIGHBORHOODS = ["moore", "von_neumann"]


@pytest.mark.parametrize("neighborhood", NEIGHBORHOODS)
def test_closed_system_conserves_mass_and_depth_stays_nonnegative(neighborhood):
    rows, cols = 20, 20
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    Z = ((x - cols / 2) ** 2 + (y - rows / 2) ** 2) / (rows * cols)
    N = 0.03 + 0.04 * (x > cols / 2)
    H = np.zeros((rows, cols))
    H[8:12, 3:7] = 5.0
    initial_volume = H.sum()

    for t in range(80):
        H = step(Z, H, N, neighborhood=neighborhood)
        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
        assert abs(H.sum() - initial_volume) <= 1e-12 * initial_volume, f"volume drifted at step {t}"


@pytest.mark.parametrize("neighborhood", NEIGHBORHOODS)
def test_inflow_and_outlet_bookkeeping_is_exact(neighborhood):
    """Open system: final volume == inflow - outflow, with outflow booked from H before/after each step."""
    rows, cols = 12, 12
    Z = np.add.outer(np.linspace(6.0, 0.0, rows), np.zeros(cols))
    N = np.full((rows, cols), 0.05)
    H = np.zeros((rows, cols))
    inflow = np.zeros((rows, cols))
    inflow[0, 5:7] = 0.5
    boundary_elevation = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    boundary_elevation[-1, 6] = -5.0
    boundary_roughness = np.pad(N, 1, mode="constant", constant_values=1.0)
    boundary_roughness[-1, 6] = 0.04

    cumulative_inflow = cumulative_outflow = 0.0
    for t in range(200):
        before = H.sum()
        H = step(Z, H, N, inflow=inflow, boundary_elevation=boundary_elevation,
                 boundary_roughness=boundary_roughness, neighborhood=neighborhood)
        cumulative_inflow += inflow.sum()
        cumulative_outflow += before + inflow.sum() - H.sum()
        assert H.min() >= -1e-9, f"negative depth at step {t}: {H.min()}"
    assert cumulative_outflow > 0, "the outlet should have drained something"
    assert H.sum() == pytest.approx(cumulative_inflow - cumulative_outflow, rel=1e-12)


def _point_source(neighborhood, steps, outflow_fraction=engine.DEFAULT_OUTFLOW_FRACTION, n=81):
    Z = np.zeros((n, n))
    N = np.full((n, n), 0.05)
    H = np.zeros((n, n))
    H[n // 2, n // 2] = 100.0
    for _ in range(steps):
        H = step(Z, H, N, outflow_fraction=outflow_fraction, neighborhood=neighborhood)
    return H


def _reach_and_fill(wet):
    """Axial reach `a`, diagonal reach `d` (in cells, from the center) and the fraction of the enclosing
    (2a+1)^2 square the wet set fills: 1 for a square, ~0.83 for a regular octagon, 0.785 for a disc and
    ~0.5 for a diamond."""
    c = wet.shape[0] // 2
    a = max(k for k in range(c + 1) if wet[c, c + k])
    d = max(k for k in range(c + 1) if wet[c + k, c + k])
    return a, d, wet.sum() / (2 * a + 1) ** 2


def test_single_substep_support_is_the_neighborhood_geometry():
    """The stencil itself: with one substep per step, water reaches exactly the L-infinity ball (a square)
    under Moore and exactly the L1 ball (a diamond) under von Neumann after k steps."""
    k = 6
    rr, cc = np.mgrid[0:81, 0:81] - 40
    moore = _point_source("moore", k, outflow_fraction=0.01) > 0
    von_neumann = _point_source("von_neumann", k, outflow_fraction=0.01) > 0

    assert np.array_equal(moore, np.maximum(abs(rr), abs(cc)) <= k)
    assert np.array_equal(von_neumann, abs(rr) + abs(cc) <= k)


def test_spread_shape_is_octagon_like_under_moore_and_diamond_like_under_von_neumann():
    """Isotropy on a flat grid with a point source, at the default outflow fraction (9 substeps/step).

    The lattice shape shows in the spreading front - the low-depth tail, here 1e-9 of the peak depth:
    Moore's contour fills ~0.87 of its square with diagonal reach ~0.75 of axial (octagon-like), von
    Neumann's ~0.65 with ~0.6 (leaning to a diamond). The bulk of the pool (1% of the peak) is near-round
    under both after enough steps - the many substeps diffuse the stencil's anisotropy out of the core -
    so a 4-neighbor run's flood *bulk* is not a diamond; only its fringe is. Thresholds measured once
    (docs/tcc-deviations.md section 22) with margin.
    """
    moore = _point_source("moore", 20)
    von_neumann = _point_source("von_neumann", 20)

    a_m, d_m, fill_m = _reach_and_fill(moore > 1e-9 * moore.max())
    a_v, d_v, fill_v = _reach_and_fill(von_neumann > 1e-9 * von_neumann.max())
    assert fill_m > 0.8 and d_m / a_m > 0.7, (a_m, d_m, fill_m)
    assert fill_v < 0.72 and d_v / a_v < 0.68, (a_v, d_v, fill_v)
    assert a_v <= a_m  # 4 neighbors: fewer ways out, so the front advances no farther

    # The developed bulk is round under both (a disc fills 0.785).
    for neighborhood in NEIGHBORHOODS:
        H = _point_source(neighborhood, 80)
        _, _, fill = _reach_and_fill(H > 0.01 * H.max())
        assert 0.7 < fill < 0.85, (neighborhood, fill)


def test_compute_stable_dt_uses_the_same_neighbors_as_step():
    """A pit whose only lower neighbor is diagonal: Moore's step() drains it there and its CFL search sees
    that slope (finite dt); under von Neumann step() can't move the water at all, and the CFL search mustn't
    count the diagonal slope either (no-flow fallback)."""
    Z = np.array([[9.0, 9.0, 9.0], [9.0, 5.0, 9.0], [9.0, 9.0, 0.0]])
    H = np.zeros((3, 3))
    H[1, 1] = 1.0
    N = np.full((3, 3), 0.05)

    assert compute_stable_dt(Z, H, N, dx=30.0) < engine._NO_FLOW_FALLBACK_DT_SECONDS
    assert step(Z, H, N)[2, 2] > 0
    assert compute_stable_dt(Z, H, N, dx=30.0, neighborhood="von_neumann") == engine._NO_FLOW_FALLBACK_DT_SECONDS
    assert np.array_equal(step(Z, H, N, neighborhood="von_neumann"), H)


def test_neighborhood_rejects_unknown_values():
    Z = np.zeros((3, 3))
    H = np.zeros((3, 3))
    N = np.full((3, 3), 0.05)
    with pytest.raises(ValueError):
        step(Z, H, N, neighborhood="hexagonal")
    with pytest.raises(ValueError):
        compute_stable_dt(Z, H, N, dx=30.0, neighborhood="hexagonal")


def _moore8_roughness(H):
    """test_no_checkerboard_artifact_with_varying_roughness's metric: mean |H - mean(8 neighbors)| over wet cells."""
    rows, cols = H.shape
    padded = np.pad(H, 1, mode="edge")
    neighbor_mean = sum(
        padded[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols]
        for dr in (-1, 0, 1) for dc in (-1, 0, 1) if not (dr == 0 and dc == 0)
    ) / 8.0
    flooded = H > 1e-6
    return np.abs(H[flooded] - neighbor_mean[flooded]).mean()


def test_von_neumann_substep_fraction_stays_at_the_real_data_validated_value():
    """Pins _MAX_STABLE_SUBSTEP_FRACTION_VON_NEUMANN at the value measured on real terrain (docs/tcc-deviations.md
    section 22) - not assumed from Moore's. Like the Moore pin above, passing the synthetic control below is
    necessary but not sufficient: changing this constant needs the real-terrain check re-run."""
    assert engine._MAX_STABLE_SUBSTEP_FRACTION_VON_NEUMANN == pytest.approx(0.01)

    # The flat-water control, under von Neumann (0.013 measured; Moore's is 0.015 at the same fraction).
    Z = np.zeros((20, 20))
    N = np.full((20, 20), 0.05)
    H = np.full((20, 20), 2.0)
    H[10, 10] += 0.5
    for _ in range(30):
        H = step(Z, H, N, neighborhood="von_neumann")
    roughness = _moore8_roughness(H)
    assert roughness < 0.05, f"flat-water control regression (von Neumann): roughness={roughness:.5f}"


def test_von_neumann_varying_roughness_grid_is_converged_in_the_substep_fraction():
    """The varying-roughness checkerboard grid under von Neumann. Its Moore-8 roughness sits at ~0.050 whatever
    the substep fraction (0.0503 at 0.005, 0.0505 at 0.01): that level is the 4-neighbor lattice's own
    anisotropy as read by an 8-neighbor metric, not an instability, so the Moore-calibrated 0.05 cutoff doesn't
    transfer. What an instability would show is dependence on the fraction - so assert that halving it
    changes nothing material."""
    rows, cols = 40, 40
    y, x = np.mgrid[0:rows, 0:cols].astype(float)
    Z = ((x - cols / 2) ** 2 + (y - rows / 2) ** 2) / (rows * cols) * 3.0
    diagonal = (x - y) / max(rows, cols)
    N = 0.09 - 0.07 * np.exp(-(diagonal ** 2) / (2 * 0.15 ** 2))

    def roughness_at(fraction):
        H = np.zeros((rows, cols))
        H[rows // 2 - 2: rows // 2 + 3, cols // 2 - 2: cols // 2 + 3] = 400.0 / 25
        with mock.patch.object(engine, "_MAX_STABLE_SUBSTEP_FRACTION_VON_NEUMANN", fraction):
            for _ in range(60):
                H = step(Z, H, N, neighborhood="von_neumann")
        return _moore8_roughness(H)

    chosen = engine._MAX_STABLE_SUBSTEP_FRACTION_VON_NEUMANN
    assert roughness_at(chosen) <= 1.02 * roughness_at(chosen / 2)
