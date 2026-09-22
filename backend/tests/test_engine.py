import math

import numpy as np
import pytest

from simulation.engine import compute_stable_dt, seed_pool_at_lowest_point, step


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
