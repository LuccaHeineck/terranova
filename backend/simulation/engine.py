"""Macroscopic cellular automaton engine for flood propagation.

Each cell holds a static terrain elevation (Z), a dynamic water depth (H),
and a static Manning roughness coefficient (N). `step` advances H by one
discrete iteration: water moves from each cell to its 8 Moore neighbors,
weighted by slope and by the roughness of the neighbor being flowed into,
never uphill. The grid is closed and walled on all sides by default (nothing
enters or leaves, mass conserved exactly) but can be made an open system via
`step`'s optional `inflow` source term (e.g. boundary inflow standing in for
upstream river discharge, in which case volume grows by exactly the injected
amount each step instead of staying constant) and/or its optional
`boundary_elevation`/`boundary_roughness` parameters, which turn specific
boundary cells into a real outlet water can permanently leave through instead
of a wall.

This module has no I/O and no geodata dependency on purpose - it operates
on plain NumPy arrays so it can be validated on small synthetic grids
before any real elevation/roughness data is involved.
"""

import math

import numpy as np

MOORE_OFFSETS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 1),
    (1, -1), (1, 0), (1, 1),
]

# All cells release their capped outflow simultaneously (a synchronous/Jacobi
# update, required for CA parallelism). If a single release moves too large a
# fraction of a cell's depth at once, neighboring cells overshoot past each
# other step to step, producing a checkerboard/speckle artifact - the same
# family of instability as violating a CFL condition in explicit diffusion
# schemes. Empirically, per-substep fractions above ~0.01 visibly speckle;
# below that, remaining unevenness flattens out to the residual directional
# grain inherent to a Moore-neighborhood lattice (real anisotropy, not
# further reducible by shrinking this constant). `step` transparently
# decomposes a larger requested outflow_fraction into enough sub-updates to
# stay under this bound.
#
# Re-swept once in roadmap step 11 (performance benchmarking) and deliberately
# reverted back to 0.01: raising this to 0.02 passed both of test_engine.py's
# calibrated synthetic checkerboard regressions (the varying-roughness grid
# and the flat-water control), but a visual check against a real gauge-driven
# run on real terrain - specifically requested before trusting the synthetic
# tests alone - showed a real, visible mottled/branching artifact by ~step
# 60000 that neither synthetic scenario reproduced (real boundary inflow
# entering continuously through a few channel cells over tens of thousands of
# steps, on real heterogeneous roughness, isn't represented by either
# calibrated grid). Isolated by re-running the same real scenario with only
# the substep fraction changed: 0.02 alone reproduces the artifact, 0.01
# alone (with outflow_fraction_for_dt's dt-scaling still applied) is clean.
# So this constant stays at its original, real-data-validated value. Neither
# this relaxation nor outflow_fraction_for_dt below survived as a validated
# performance win in the end (the latter measured to have no significant
# effect either, at real 90m resolution - dt is rarely capped below the CFL
# bound during the fast/wet part of a real event, which is where most of the
# runtime actually goes) - see docs/tcc-deviations.md for the full writeup of
# this investigation as a negative result, not abandoned work.
_MAX_STABLE_SUBSTEP_FRACTION = 0.01


def _single_update(Zp: np.ndarray, Np: np.ndarray, H: np.ndarray, outflow_fraction: float) -> np.ndarray:
    """One synchronous Moore-neighborhood redistribution pass."""
    rows, cols = H.shape
    Hp = np.pad(H, 1, mode="constant", constant_values=0.0)
    wse = Zp + Hp
    center = wse[1:-1, 1:-1]

    weights = []
    total_weight = np.zeros((rows, cols))
    for dr, dc in MOORE_OFFSETS:
        neighbor = wse[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols]
        neighbor_n = Np[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols]
        distance = math.hypot(dr, dc)
        drop = np.maximum(center - neighbor, 0.0)
        slope = drop / distance
        # Manning's Q_i = (1/n_i) * h_i^(5/3) * sqrt(S_i). h_i (the source
        # cell's own depth) is the same in all 8 directions, so it's a
        # constant factor that cancels out once weights are normalized below
        # - it's intentionally omitted here rather than computed and thrown
        # away. n_i is the destination neighbor's roughness (the surface the
        # water is entering), not the source cell's - the TCC's summary
        # doesn't pin this down explicitly, so this is a documented modeling
        # choice, not a literal transcription.
        weight = np.sqrt(slope) / neighbor_n
        weights.append(weight)
        total_weight += weight

    has_outflow = total_weight > 0
    safe_total_weight = np.where(has_outflow, total_weight, 1.0)
    total_outflow = np.where(has_outflow, outflow_fraction * H, 0.0)

    inflow = np.zeros((rows + 2, cols + 2))
    for (dr, dc), weight in zip(MOORE_OFFSETS, weights):
        outflow = total_outflow * (weight / safe_total_weight)
        inflow[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols] += outflow

    return H - total_outflow + inflow[1:-1, 1:-1]


def step(
    Z: np.ndarray,
    H: np.ndarray,
    N: np.ndarray,
    outflow_fraction: float = 0.5,
    inflow: np.ndarray | None = None,
    boundary_elevation: np.ndarray | None = None,
    boundary_roughness: np.ndarray | None = None,
) -> np.ndarray:
    """Advance the water depth grid H by one discrete time step.

    For each cell, water surface elevation is `Z + H`. Over the step, the
    cell releases at most `outflow_fraction` of its current depth in total,
    split among its downhill Moore neighbors weighted by `sqrt(slope) / n`
    (slope = elevation drop divided by distance, with diagonal neighbors
    farther than orthogonal ones; `n` = the receiving neighbor's Manning
    roughness coefficient from `N`, so smoother neighbors draw proportionally
    more of the outflow). That total release is carried out as several
    smaller synchronous sub-updates (see `_MAX_STABLE_SUBSTEP_FRACTION`)
    rather than one single release, which keeps the scheme numerically
    stable (H never goes negative, no checkerboard artifacts) without
    changing how much water moves over the step.

    Roughness only steers *where* the capped outflow goes, not *how much*
    leaves the cell - see `docs/project-plan.md`'s step 2 notes for why.

    The grid is closed (no rain/infiltration) and walled on all four sides by
    default (`Z` is padded with `+inf`, so no real cell ever has a downhill
    neighbor across the boundary - see `boundary_elevation` below to change
    this). `inflow`, if given, is a per-cell external source term (e.g. a
    boundary inflow standing in for upstream river discharge) added to H once
    after the redistribution above - newly-arrived water starts redistributing
    on the *next* step rather than mid-step, an explicit simplification of the
    same kind as the substep decomposition. With `inflow`, total volume is no
    longer conserved outright: it grows by exactly `inflow.sum()` per step,
    which is still exactly checkable rather than merely approximate.

    `boundary_elevation`/`boundary_roughness`, if given, replace the default
    all-wall padded `Z`/`N` arrays outright (shape `(rows+2, cols+2)`, i.e.
    `H`'s shape plus one cell of padding on every side) - this is how a caller
    can turn specific boundary cells into a real outlet instead of a wall:
    where the override elevation is lower than a real interior cell's water
    surface, water flows toward it exactly like any other downhill neighbor
    through the same weighted-redistribution math, and (since `_single_update`
    already only returns the *cropped* interior of its scratch padding array -
    true even in the unmodified default case, it just never mattered before
    because a `+inf` wall never receives outflow) that water simply leaves the
    tracked domain rather than bouncing back. When omitted, behavior is
    byte-identical to a plain `np.pad(Z, 1, constant_values=np.inf)`/
    `np.pad(N, 1, constant_values=1.0)` wall on every side, exactly as before
    this parameter existed. With an outlet, total volume is no longer
    conserved *or* simply additive: a caller can still get an exact invariant
    by bookkeeping the difference itself -
    `outflow_this_step = H_before.sum() + inflow.sum() - H_after.sum()` - since
    `step()`'s return value already reflects whatever left through the outlet;
    no separate return value is needed. See `docs/tcc-deviations.md` for why
    this extension exists (TCC1's base model is otherwise fully closed) and
    `ingestion/hydrograph.py`'s boundary-outlet builder for how the real ROI's
    override arrays are actually constructed from the DEM.
    """
    if not (0 < outflow_fraction <= 1):
        raise ValueError("outflow_fraction must be in (0, 1]")
    if np.any(N <= 0):
        raise ValueError("N (Manning roughness) must be strictly positive everywhere")
    if inflow is not None:
        if inflow.shape != H.shape:
            raise ValueError("inflow must have the same shape as H")
        if np.any(inflow < 0):
            raise ValueError("inflow must be non-negative everywhere")
    padded_shape = (H.shape[0] + 2, H.shape[1] + 2)
    if boundary_elevation is not None and boundary_elevation.shape != padded_shape:
        raise ValueError(f"boundary_elevation must have shape {padded_shape} (H's shape padded by 1)")
    if boundary_roughness is not None:
        if boundary_roughness.shape != padded_shape:
            raise ValueError(f"boundary_roughness must have shape {padded_shape} (H's shape padded by 1)")
        if np.any(boundary_roughness <= 0):
            raise ValueError("boundary_roughness must be strictly positive everywhere")

    n_substeps = math.ceil(outflow_fraction / _MAX_STABLE_SUBSTEP_FRACTION)
    # Per-substep fraction chosen so that n_substeps of sequential depletion
    # at this rate remove the same total fraction as one release of
    # outflow_fraction would (1 - (1 - f) = compounding decay identity).
    substep_fraction = 1 - (1 - outflow_fraction) ** (1 / n_substeps)

    if boundary_elevation is not None:
        Zp = boundary_elevation
    else:
        Zp = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    if boundary_roughness is not None:
        Np = boundary_roughness
    else:
        # Boundary N value is physically irrelevant for a wall - boundary
        # weights are always multiplied by drop=0 since no real cell exceeds
        # the +inf-padded wall - but must be positive to avoid 0 * inf = nan
        # corrupting the array.
        Np = np.pad(N, 1, mode="constant", constant_values=1.0)
    for _ in range(n_substeps):
        H = _single_update(Zp, Np, H, substep_fraction)
    if inflow is not None:
        H = H + inflow
    return H


# No downhill velocity anywhere (dry grid, or perfectly flat/still water) means the
# Manning-derived CFL bound is vacuous (v_max == 0 would divide by zero). Falls back to
# a fixed, documented sentinel rather than math.inf, which would poison any caller
# accumulating elapsed real time (`elapsed_time += dt`) the moment it's hit.
_NO_FLOW_FALLBACK_DT_SECONDS = 3600.0


def compute_stable_dt(
    Z: np.ndarray,
    H: np.ndarray,
    N: np.ndarray,
    dx: float,
    courant_number: float = 1.0,
) -> float:
    """Derive the real elapsed time (in seconds) that one `step()` call should be
    considered to represent, from the current water depth `H`, under a CFL-style
    stability condition: `dt <= courant_number * dx / v_max`, where `v_max` is the
    fastest Manning overland-flow velocity anywhere on the grid right now.

    Units: `dx`, `Z`, `H` in meters; `N` dimensionless Manning's n; return value in
    seconds. `dx` must be the real physical cell size (e.g.
    `config.settings.TARGET_RESOLUTION_METERS`) - this function has no way to detect
    a wrong unit, it will just silently produce a physically meaningless `dt`.

    Velocity is estimated per cell via the standard wide-channel/overland-flow
    simplification (hydraulic radius R ~= depth h), using the SI form of Manning's
    equation (coefficient 1, not the US customary 1.49, since everything here is
    metric): `v = (1/n) * h^(2/3) * sqrt(S)`, where `S` is the cell's steepest real
    downhill slope (`drop / (distance_cells * dx)`, over the 8 Moore neighbors).
    `drop` is a water-surface-elevation (`WSE = Z + H`) difference, matching
    `_single_update`'s own head-driven convention, not bare terrain elevation - a
    cell already carrying deep water has a shallower effective WSE drop to a dry
    neighbor than its bare terrain slope alone would suggest.

    Deliberate deviation from `_single_update`'s convention: both `n` and `h` here
    are the *source* cell's own values, not a destination neighbor's. That's a
    different quantity than `_single_update`'s direction-weighting (which uses the
    destination neighbor's `n` - an arbitrary, documented modeling choice for that
    unrelated purpose). Velocity is a physical magnitude at the source cell, so `n`
    and `h` must be co-located there, not mixed across cells.

    This is recomputed fresh from whatever `H` currently is - not a one-time
    constant - because real flow velocity (and thus the physically meaningful `dt`)
    changes throughout an event as depths rise and fall. A caller building a real
    elapsed-time timeline (e.g. for step 9's gauge-driven hydrograph) is expected to
    call this once per simulation step and accumulate `elapsed_time += dt`.

    Fully decoupled from `step()`'s `outflow_fraction`/substep decomposition - that
    machinery is a separate, already-solved numerical-stability hack for the
    synchronous Jacobi update, unrelated to this physical real-time mapping. Nothing
    here constrains, or is constrained by, how much depth `step()` actually releases
    per call - see `docs/project-plan.md`'s step 8 notes for the known gap this
    leaves for later steps to reconcile.
    """
    if dx <= 0:
        raise ValueError("dx must be positive")
    if not (0 < courant_number <= 1):
        raise ValueError("courant_number must be in (0, 1]")
    if np.any(N <= 0):
        raise ValueError("N (Manning roughness) must be strictly positive everywhere")

    rows, cols = H.shape
    Zp = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    Hp = np.pad(H, 1, mode="constant", constant_values=0.0)
    wse = Zp + Hp
    center = wse[1:-1, 1:-1]

    max_slope = np.zeros((rows, cols))
    for dr, dc in MOORE_OFFSETS:
        neighbor = wse[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols]
        distance = math.hypot(dr, dc)
        drop = np.maximum(center - neighbor, 0.0)
        slope = drop / (distance * dx)
        max_slope = np.maximum(max_slope, slope)

    # H should never be meaningfully negative (step()'s own tested invariant keeps it
    # within -1e-9 of zero), but a fractional exponent on a negative float is nan.
    velocity = (1.0 / N) * np.power(np.maximum(H, 0.0), 2.0 / 3.0) * np.sqrt(max_slope)
    v_max = velocity.max()

    if v_max <= 0:
        return _NO_FLOW_FALLBACK_DT_SECONDS

    return courant_number * dx / v_max


def outflow_fraction_for_dt(outflow_fraction: float, dt: float, dt_cfl: float) -> float:
    """Scale a requested `outflow_fraction` down when the `dt` actually used for a
    macro step is smaller than the raw CFL bound `compute_stable_dt` would allow
    (`dt_cfl`, i.e. its return value with `courant_number=1.0`, before any
    application-level cap - e.g. the 900s inflow-burst cap or a hydrograph's
    remaining-duration clip in `api/routers/simulations.py::_run_gauge_driven`).

    Rationale: `step()`'s own `outflow_fraction` has no notion of elapsed time -
    it's a step-1-era heuristic ("release this fraction of depth per macro step"),
    while `dt_cfl` is a real physical elapsed-time bound derived in step 8. When a
    caller's `dt` is capped well below `dt_cfl`, physically far less time (and thus
    far less real depth transfer) should be considered to have happened in that
    macro step than `outflow_fraction` alone assumes - so scale it down
    proportionally. Anchored so `dt == dt_cfl` reproduces `outflow_fraction`
    unchanged (today's exact behavior in that regime); `dt < dt_cfl` scales down;
    `dt > dt_cfl` (shouldn't happen if `dt_cfl` truly bounds `dt`, but handled
    defensively) clamps back to `outflow_fraction`, never scaling up.

    Does NOT help when `dt == dt_cfl` (velocity itself, not an application cap, is
    what's driving `dt` down - the wet/fast-flow part of a real event). That
    regime was swept empirically (see `_MAX_STABLE_SUBSTEP_FRACTION`'s comment
    above) and found to still need close to the full substep count for stability
    - a real, documented limitation, not an oversight. In practice, measured
    against the real May 2024 gauge-driven event at 90m resolution, this function
    was found to have no significant effect on step count, wall-clock time, or
    CSI relative to not using it at all - `dt` is rarely capped below `dt_cfl`
    during the fast/wet part of a real event, which is where most of the runtime
    goes. Kept because it's correct and harmless, not because it's a validated
    performance win; see `docs/tcc-deviations.md` for the full investigation.
    """
    if not (0 < outflow_fraction <= 1):
        raise ValueError("outflow_fraction must be in (0, 1]")
    if dt <= 0:
        raise ValueError("dt must be positive")
    if dt_cfl <= 0:
        raise ValueError("dt_cfl must be positive")
    return outflow_fraction * min(1.0, dt / dt_cfl)


def seed_pool_at_lowest_point(Z: np.ndarray, H: np.ndarray, volume: float) -> None:
    """Seed a concentrated water pool centered on the terrain's lowest point
    (e.g. a river channel), in place on `H`.

    Shared by every caller that needs a sensible default starting condition on
    real terrain (`examples/poc_real_dem.py`, `api/`'s simulation route) rather
    than each defining its own copy.
    """
    ry, rx = np.unravel_index(np.argmin(Z), Z.shape)
    ry = int(np.clip(ry, 2, Z.shape[0] - 3))
    rx = int(np.clip(rx, 2, Z.shape[1] - 3))
    patch = H[ry - 2: ry + 3, rx - 2: rx + 3]
    patch[:] = volume / patch.size
