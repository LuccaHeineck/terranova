"""Plain-Python, cell-by-cell version of `simulation.engine.step` - the baseline for
TCC1's "vectorized NumPy vs. naive loops" performance comparison (roadmap step 11,
docs/tcc-deviations.md section 25).

Benchmark-only: nothing in `api/` uses it. It exists so the speedup NumPy buys can be
measured against the same model written without vectorization, so it must compute
exactly what `engine.step` computes - not merely something close. `tests/test_engine_loops.py`
pins that with exact equality (section 18: the engine amplifies a single-ulp difference
into ~0.2 m within ~50 steps, so "close" would say nothing about a long run).

Bit-identity comes from doing the same IEEE operations in the same order as
`engine._single_update`:
- weights are accumulated over the offsets in list order, starting from 0.0;
- incoming outflow is *gathered* per destination cell, again in offset order, which is
  the order the vectorized code's per-offset `inflow[...] += outflow` adds them in. A
  source-major scatter would add the same terms in a different order and round
  differently.

Works on nested Python lists (converted once per call, inside any timed region), the
fastest honest pure-Python form, so the measured NumPy speedup is a conservative one.
`compute_stable_dt` is not ported: `step()` is ~95% of a macro step's wall-clock
(docs/tcc-deviations.md section 13's profile), and it is what the comparison is about.
"""

import math

import numpy as np

from simulation.engine import DEFAULT_OUTFLOW_FRACTION, _max_stable_substep_fraction, _neighborhood_offsets


def _single_update(
    Zp: list[list[float]],
    Np: list[list[float]],
    H: list[list[float]],
    outflow_fraction: float,
    offsets: list[tuple[int, int]],
) -> list[list[float]]:
    """One synchronous redistribution pass - `engine._single_update`, one cell at a time."""
    rows, cols = len(H), len(H[0])
    distances = [math.hypot(dr, dc) for dr, dc in offsets]

    # Water surface elevation over the padded grid (H is padded with 0.0, as in the engine).
    wse = [row[:] for row in Zp]
    for r in range(rows):
        wse_row, h_row = wse[r + 1], H[r]
        for c in range(cols):
            wse_row[c + 1] = wse_row[c + 1] + h_row[c]

    # Pass 1, per source cell: weights, total release, and the release toward each offset.
    total_outflow = [[0.0] * cols for _ in range(rows)]
    outflows = [[None] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            center = wse[r + 1][c + 1]
            weights = []
            total_weight = 0.0
            for (dr, dc), distance in zip(offsets, distances):
                drop = center - wse[r + 1 + dr][c + 1 + dc]
                if drop < 0.0:
                    drop = 0.0
                weight = math.sqrt(drop / distance) / Np[r + 1 + dr][c + 1 + dc]
                weights.append(weight)
                total_weight += weight
            if total_weight > 0:
                released = outflow_fraction * H[r][c]
                safe_total_weight = total_weight
            else:
                released = 0.0
                safe_total_weight = 1.0
            total_outflow[r][c] = released
            outflows[r][c] = [released * (weight / safe_total_weight) for weight in weights]

    # Pass 2, per destination cell: gather what each neighbor sent here, in offset order.
    # Releases toward the padding ring are never gathered, so they leave the grid (an outlet).
    new_H = [[0.0] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            received = 0.0
            for k, (dr, dc) in enumerate(offsets):
                sr, sc = r - dr, c - dc
                if 0 <= sr < rows and 0 <= sc < cols:
                    received += outflows[sr][sc][k]
            new_H[r][c] = H[r][c] - total_outflow[r][c] + received
    return new_H


def step(
    Z: np.ndarray,
    H: np.ndarray,
    N: np.ndarray,
    outflow_fraction: float = DEFAULT_OUTFLOW_FRACTION,
    inflow: np.ndarray | None = None,
    boundary_elevation: np.ndarray | None = None,
    boundary_roughness: np.ndarray | None = None,
    neighborhood: str = "moore",
) -> np.ndarray:
    """`engine.step`, computed cell by cell in plain Python. Same arguments, same
    validation, bit-identical result - see `engine.step` for what each argument means."""
    offsets = _neighborhood_offsets(neighborhood)
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

    n_substeps = math.ceil(outflow_fraction / _max_stable_substep_fraction(neighborhood))
    substep_fraction = 1 - (1 - outflow_fraction) ** (1 / n_substeps)

    if boundary_elevation is None:
        boundary_elevation = np.pad(Z, 1, mode="constant", constant_values=np.inf)
    if boundary_roughness is None:
        boundary_roughness = np.pad(N, 1, mode="constant", constant_values=1.0)
    Zp = boundary_elevation.tolist()
    Np = boundary_roughness.tolist()
    H_cells = H.tolist()
    for _ in range(n_substeps):
        H_cells = _single_update(Zp, Np, H_cells, substep_fraction, offsets)
    if inflow is not None:
        inflow_cells = inflow.tolist()
        H_cells = [
            [h + added for h, added in zip(h_row, inflow_row)]
            for h_row, inflow_row in zip(H_cells, inflow_cells)
        ]
    return np.array(H_cells, dtype=np.float64)
