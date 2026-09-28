"""Torres-inspired non-temporal fast flood classification (hybrid architecture,
see docs/tcc-deviations.md sections 17 and 19).

A second, separate engine alongside `simulation.engine` - not a replacement.
The temporal engine evolves `H` step by step under a CFL-bounded `dt`; this
one has no time at all: given a steady discharge entering through an inflow
mask, it classifies every cell's final state in one top-down,
elevation-ordered routing pass plus one lateral pass, and returns the
resulting depth/extent directly. It trades wave-front arrival timing (which
only the temporal engine can represent) for speed.

**Inspiration, not a reproduction.** The general approach - a top-down
evaluation of flow through DEM cells, ordered by elevation, classifying each
cell under a Moore neighborhood into four dynamic states with their own rules
- follows Torres, Chavez-Cifuentes & Reinoso (2022), "A conceptual flood model
based on cellular automata for probabilistic risk applications",
Environmental Modelling & Software 157:105530. That paper's own state
definitions and rules are not publicly available (paywalled full text), so
the four states and rules below are this project's own design, consistent
with its public description. Nothing here reproduces, or is validated
against, that paper's numbers.

The four states (`DRY`, `CONVEYING`, `INUNDATED`, `EXITING`):

- `CONVEYING` - the cell carries part of the routed inflow discharge `Q`. Its
  water surface is its outlet-conditioned elevation (see below - above its
  terrain only where it sits in a depression that must be full at steady
  state) plus the Manning normal depth that carries that `Q` across one cell
  width: `Q = (1/n) * h^(5/3) * sqrt(S) * w`, i.e.
  `h = (Q * n / (w * sqrt(S)))^(3/5)`, with `w = dx` (the same wide-channel,
  hydraulic-radius ~= depth simplification `engine.compute_stable_dt` uses,
  with the same *source-cell* `n` convention for a physical magnitude).
- `EXITING` - a `CONVEYING` cell that passes (some of) its `Q` out of the
  domain through an outlet boundary cell. Kept distinct so the outlet's role
  is visible in the classification, not only in the continuity total.
- `INUNDATED` - the cell carries no routed flow of its own, but its terrain
  lies below the water surface of the conveying cell its steepest-descent
  path first reaches (a Height-Above-Nearest-Drainage-style lateral rule): the
  river's water surface backs out sideways onto it. Depth is that water
  surface minus its own terrain.
- `DRY` - neither: no routed flow reaches it and it sits above the water
  surface of the conveying cell it drains to (or it drains to none).

**Why a steady discharge rather than a volume**: the domain has a real
outlet, so a volume routed downhill would simply drain out. Conveyance - how
deep water must be for Manning's equation to carry the river's discharge - is
what actually sets flood extent for a through-flowing river, so that is what
this engine computes.

**Outlet-conditioned routing surface.** `ingestion/dem.py`'s sink filling
guarantees every cell a non-ascending path to *some* border cell, but the
simulated domain is walled everywhere except its outlet, so the river's own
path can still dead-end against a wall. At steady state under continuous
inflow, any depression on the flow path is full to its spill level before
water moves on, so routing runs over a surface re-filled by a priority-flood
(Barnes et al. 2014, the same algorithm `ingestion/dem.py` uses) seeded from
the outlet cells alone: `Zf = max(Z, spill level toward the outlet)`. The
flood's own visitation order is the routing order (reversed: farthest-from-
outlet, highest cells first - the "top-down" pass), and every reachable cell
was pushed by an earlier, not-higher neighbor, so it provably has a
downstream path to the outlet. Cells the flood never reaches (walled off from
the outlet) cannot pass flow on; discharge reaching them is `retained_m3s`.

Routing rule: each visited cell with `Q > 0` splits its `Q` among its
downstream Moore neighbors - neighbors visited earlier by the flood with
`Zf <= its own`, plus any lower-or-equal outlet cell - weighted by
`sqrt(S) / n_dest` (the same weighting and destination-roughness convention
as `engine._single_update`). Flux only ever moves toward the outlet in flood
order, so one pass routes everything. Discharge continuity,
`outflow_m3s + retained_m3s == inflow`, is this engine's analogue of the
temporal engine's mass conservation.

No I/O, no geodata: plain NumPy arrays in, plain arrays out, like
`simulation.engine`. Both passes are inherently sequential (each cell depends
on cells processed before it), so they are plain Python loops rather than
vectorized NumPy/CuPy expressions - fast enough for this project's grids, but
not a candidate for the GPU path.
"""

import heapq
import math
from dataclasses import dataclass

import numpy as np

DRY = 0
CONVEYING = 1
INUNDATED = 2
EXITING = 3

MOORE_OFFSETS = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 1),
    (1, -1), (1, 0), (1, 1),
]

# Floor for the slope used in both the routing weights and the Manning depth.
# The outlet-conditioned surface has real flats (filled depressions, and the
# plateaus sink filling already leaves), where Manning's equation would need
# infinite depth to carry any discharge. 1e-4 m/m is the order of magnitude of
# large lowland river bed slopes, so it caps the depth such a flat produces at
# a physically plausible value rather than an arbitrary one. Not tuned
# against CSI; `FastFloodResult.min_slope_cells` reports how often it binds.
_MIN_SLOPE = 1e-4

_UNREACHED = np.iinfo(np.int64).max


@dataclass
class FastFloodResult:
    state: np.ndarray  # int8, one of DRY/CONVEYING/INUNDATED/EXITING
    depth: np.ndarray  # m, water surface minus terrain
    discharge: np.ndarray  # m3/s routed through each cell
    wse: np.ndarray  # water surface elevation, m (== Z where depth is 0)
    flooded: np.ndarray  # bool, depth > depth_threshold_m
    inflow_m3s: float
    outflow_m3s: float
    retained_m3s: float
    min_slope_cells: int  # conveying cells whose slope hit _MIN_SLOPE


def classify_steady_flood(
    Z: np.ndarray,
    N: np.ndarray,
    dx: float,
    peak_discharge_m3s: float,
    inflow_mask: np.ndarray,
    boundary_elevation: np.ndarray | None = None,
    boundary_roughness: np.ndarray | None = None,
    depth_threshold_m: float = 0.01,
) -> FastFloodResult:
    """Classify the steady-state flood extent for a constant discharge
    `peak_discharge_m3s` entering through `inflow_mask`, split uniformly across
    its cells. See the module docstring for the four states and both passes.

    Units: `Z`, `dx` in meters; `N` dimensionless Manning's n; discharge in m3/s.
    `boundary_elevation`/`boundary_roughness` are the same padded
    `(rows+2, cols+2)` overrides `engine.step` accepts (e.g. from
    `ingestion.hydrograph.find_boundary_outlet`): finite padded cells are
    outlets, `+inf` ones walls. When omitted the domain is walled on every
    side, so all routed discharge ends up in `retained_m3s`.
    """
    if dx <= 0:
        raise ValueError("dx must be positive")
    if peak_discharge_m3s < 0:
        raise ValueError("peak_discharge_m3s must be non-negative")
    if N.shape != Z.shape or inflow_mask.shape != Z.shape:
        raise ValueError("N and inflow_mask must have the same shape as Z")
    if np.any(N <= 0):
        raise ValueError("N (Manning roughness) must be strictly positive everywhere")
    if not inflow_mask.any():
        raise ValueError("inflow_mask has no True cells to inject discharge into")
    rows, cols = Z.shape
    padded_shape = (rows + 2, cols + 2)
    for name, arr in (("boundary_elevation", boundary_elevation), ("boundary_roughness", boundary_roughness)):
        if arr is not None and arr.shape != padded_shape:
            raise ValueError(f"{name} must have shape {padded_shape} (Z's shape padded by 1)")
    if boundary_roughness is not None and np.any(boundary_roughness <= 0):
        raise ValueError("boundary_roughness must be strictly positive everywhere")

    Zp = boundary_elevation if boundary_elevation is not None else np.pad(Z, 1, constant_values=np.inf)
    Np = boundary_roughness if boundary_roughness is not None else np.pad(N, 1, constant_values=1.0)
    flat_Z = Z.ravel()
    size = flat_Z.size
    distances = [math.hypot(dr, dc) * dx for dr, dc in MOORE_OFFSETS]

    def neighbors(i: int):
        """(flat index or None if outside the grid, padded row, padded col,
        distance in m) for each Moore neighbor of flat cell `i`."""
        r, c = divmod(i, cols)
        for (dr, dc), dist in zip(MOORE_OFFSETS, distances):
            rr, cc = r + dr, c + dc
            inside = 0 <= rr < rows and 0 <= cc < cols
            yield (rr * cols + cc if inside else None), rr + 1, cc + 1, dist

    # --- Outlet-conditioned surface: priority-flood seeded from outlets only --
    Zf = flat_Z.astype(float).copy()
    visit = np.full(size, _UNREACHED, dtype=np.int64)  # flood visitation order
    heap: list[tuple[float, int, int]] = []
    counter = 0
    seeded = set()
    for i in range(size):
        for j, pr, pc, _ in neighbors(i):
            if j is None and np.isfinite(Zp[pr, pc]) and i not in seeded:
                heapq.heappush(heap, (max(flat_Z[i], Zp[pr, pc]), counter, i))
                counter += 1
                seeded.add(i)
    step = 0
    while heap:
        level, _, i = heapq.heappop(heap)
        if visit[i] != _UNREACHED:
            continue
        Zf[i] = level
        visit[i] = step
        step += 1
        for j, _, _, _ in neighbors(i):
            if j is not None and visit[j] == _UNREACHED:
                heapq.heappush(heap, (max(flat_Z[j], level), counter, j))
                counter += 1

    def downstream(i: int) -> list[tuple[int | None, int, int, float]]:
        """(flat index or None for an outlet cell, padded row, padded col, slope)
        for every downstream neighbor of reachable flat cell `i`."""
        result = []
        for j, pr, pc, dist in neighbors(i):
            if j is None:
                zj = Zp[pr, pc]
                if np.isfinite(zj) and zj <= Zf[i]:
                    result.append((None, pr, pc, max((Zf[i] - zj) / dist, _MIN_SLOPE)))
            elif visit[j] < visit[i] and Zf[j] <= Zf[i]:
                result.append((j, pr, pc, max((Zf[i] - Zf[j]) / dist, _MIN_SLOPE)))
        return result

    # --- Pass 1: top-down routing of Q in reverse flood order -----------------
    order = np.argsort(-visit, kind="stable")  # unreached first, then farthest-from-outlet
    Q = np.zeros(size)
    Q[inflow_mask.ravel()] = peak_discharge_m3s / int(inflow_mask.sum())
    slope = np.full(size, _MIN_SLOPE)
    exits = np.zeros(size, dtype=bool)
    outflow = 0.0
    retained = 0.0
    for i in order:
        i = int(i)
        if Q[i] <= 0:
            continue
        targets = downstream(i) if visit[i] != _UNREACHED else []
        if not targets:
            retained += Q[i]
            continue
        weights = [math.sqrt(s) / Np[pr, pc] for _, pr, pc, s in targets]
        total = sum(weights)
        slope[i] = max(s for *_, s in targets)
        for (j, _, _, _), w in zip(targets, weights):
            share = Q[i] * (w / total)
            if j is None:
                outflow += share
                exits[i] = True
            else:
                Q[j] += share

    conveying = Q > 0
    flat_N = N.ravel()
    wse = flat_Z.astype(float).copy()
    manning = (Q[conveying] * flat_N[conveying] / (dx * np.sqrt(slope[conveying]))) ** 0.6
    wse[conveying] = Zf[conveying] + manning

    # --- Pass 2: lateral (HAND-style) inundation, in flood order --------------
    # drain[i] = the conveying cell a non-conveying cell's steepest-descent
    # path first reaches (-1 if none). Flood order guarantees each cell's
    # downstream neighbors were resolved before it.
    drain = np.full(size, -1, dtype=np.int64)
    for i in order[::-1]:
        i = int(i)
        if conveying[i] or visit[i] == _UNREACHED:
            continue
        interior = [(j, s) for j, _, _, s in downstream(i) if j is not None]
        if not interior:
            continue
        j = max(interior, key=lambda js: js[1])[0]
        drain[i] = j if conveying[j] else drain[j]
    lateral_idx = np.flatnonzero((~conveying) & (drain >= 0))
    backwater = wse[drain[lateral_idx]] - flat_Z[lateral_idx]
    inundated_idx = lateral_idx[backwater > 0]
    wse[inundated_idx] = flat_Z[inundated_idx] + backwater[backwater > 0]

    depth = wse - flat_Z
    state = np.full(size, DRY, dtype=np.int8)
    state[conveying] = CONVEYING
    state[exits] = EXITING
    state[inundated_idx] = INUNDATED

    return FastFloodResult(
        state=state.reshape(Z.shape),
        depth=depth.reshape(Z.shape),
        discharge=Q.reshape(Z.shape),
        wse=wse.reshape(Z.shape),
        flooded=(depth > depth_threshold_m).reshape(Z.shape),
        inflow_m3s=float(peak_discharge_m3s),
        outflow_m3s=float(outflow),
        retained_m3s=float(retained),
        min_slope_cells=int(np.sum(conveying & (slope <= _MIN_SLOPE))),
    )
