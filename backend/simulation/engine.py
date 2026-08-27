"""Macroscopic cellular automaton engine for flood propagation.

Each cell holds a static terrain elevation (Z), a dynamic water depth (H),
and a static Manning roughness coefficient (N). `step` advances H by one
discrete iteration: water moves from each cell to its 8 Moore neighbors,
weighted by slope and by the roughness of the neighbor being flowed into,
never uphill, and mass is conserved exactly (nothing enters or leaves the
grid).

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


def step(Z: np.ndarray, H: np.ndarray, N: np.ndarray, outflow_fraction: float = 0.5) -> np.ndarray:
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
    """
    if not (0 < outflow_fraction <= 1):
        raise ValueError("outflow_fraction must be in (0, 1]")
    if np.any(N <= 0):
        raise ValueError("N (Manning roughness) must be strictly positive everywhere")

    n_substeps = math.ceil(outflow_fraction / _MAX_STABLE_SUBSTEP_FRACTION)
    # Per-substep fraction chosen so that n_substeps of sequential depletion
    # at this rate remove the same total fraction as one release of
    # outflow_fraction would (1 - (1 - f) = compounding decay identity).
    substep_fraction = 1 - (1 - outflow_fraction) ** (1 / n_substeps)

    Zp = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    # Boundary N value is physically irrelevant - boundary weights are always
    # multiplied by drop=0 since no real cell exceeds the +inf-padded wall -
    # but must be positive to avoid 0 * inf = nan corrupting the array.
    Np = np.pad(N, 1, mode="constant", constant_values=1.0)
    for _ in range(n_substeps):
        H = _single_update(Zp, Np, H, substep_fraction)
    return H


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
