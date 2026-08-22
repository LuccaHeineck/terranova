"""Macroscopic cellular automaton engine for flood propagation.

Each cell holds a static terrain elevation (Z) and a dynamic water depth
(H). `step` advances H by one discrete iteration: water moves from each
cell to its 8 Moore neighbors in proportion to the local slope, never
uphill, and mass is conserved exactly (nothing enters or leaves the grid).

This module has no I/O and no geodata dependency on purpose - it operates
on plain NumPy arrays so it can be validated on small synthetic grids
before any real elevation data is involved.
"""

import numpy as np

MOORE_OFFSETS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 1),
    (1, -1), (1, 0), (1, 1),
]


def step(Z: np.ndarray, H: np.ndarray, outflow_fraction: float = 0.5) -> np.ndarray:
    """Advance the water depth grid H by one discrete time step.

    For each cell, water surface elevation is `Z + H`. The cell releases
    at most `outflow_fraction` of its current depth per step, split among
    its downhill Moore neighbors in proportion to slope (elevation drop
    divided by distance, with diagonal neighbors farther than orthogonal
    ones). Capping the release at `outflow_fraction` of the current depth
    keeps the scheme stable and guarantees H never goes negative.
    """
    if not (0 < outflow_fraction <= 1):
        raise ValueError("outflow_fraction must be in (0, 1]")

    rows, cols = H.shape
    Zp = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    Hp = np.pad(H, 1, mode="constant", constant_values=0.0)
    wse = Zp + Hp
    center = wse[1:-1, 1:-1]

    weights = []
    total_weight = np.zeros((rows, cols))
    for dr, dc in MOORE_OFFSETS:
        neighbor = wse[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols]
        distance = np.hypot(dr, dc)
        drop = np.maximum(center - neighbor, 0.0)
        weight = drop / distance
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
