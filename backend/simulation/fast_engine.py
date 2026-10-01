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
  state) plus a stage set by one of two depth rules (`conveyance`):
  - `"cross_section"` (default, docs/tcc-deviations.md section 23): a
    HAND-style synthetic rating curve per reach (Zheng et al. 2018, "River
    channel geometry and rating curve estimation using height above the
    nearest drainage"). The channel is split into equal reaches at least
    `MIN_REACH_LENGTH_M` long; every cell draining to a reach's conveying
    cells is part of its cross-section, as a strip of width `dx^2 / L`. The
    reach's stage `h` above its channel surface is the one at which the
    divided-channel Manning sum
    `sqrt(S) * sum_k (1/n_k) * (dx^2/L) * (h - HAND_k)^(5/3)` over wet cells
    carries the discharge crossing the reach's downstream end. `S` is the
    least-squares fall of the channel surface across the reach. The
    floodplain conveys too, so the river spreads instead of stacking up.
  - `"single_cell"` (section 19's first result, kept reproducible): the
    Manning normal depth that carries the cell's own `Q` across one cell
    width, `h = (Q * n / (dx * sqrt(S)))^(3/5)` (the wide-channel,
    hydraulic-radius ~= depth simplification `engine.compute_stable_dt` uses,
    with the same *source-cell* `n` convention). With the whole river in a
    one-cell-wide channel this needs ~50 m of depth at the May 2024 peak.
- `EXITING` - a `CONVEYING` cell that passes (some of) its `Q` out of the
  domain through an outlet boundary cell. Kept distinct so the outlet's role
  is visible in the classification, not only in the continuity total.
- `INUNDATED` - the cell carries no routed flow of its own, but its terrain
  lies below the water surface of the conveying cell its steepest-descent
  path first reaches (a Height-Above-Nearest-Drainage, HAND, lateral rule): the
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

# The shortest reach the cross-section depth rule fits its own slope and
# rating curve over. TOPODATA heights are whole meters, so at a large lowland
# river's ~1e-4 slope a reach must span ~10 km before its bed falls by more
# than one quantization step; a shorter reach fits its slope and cross-section
# to DEM rounding, not to the river (docs/tcc-deviations.md section 23 has the
# sweep that shows it). The channel is split into equal reaches at least this
# long - on the Lajeado/Estrela ROI's ~8 km of river, a single reach.
MIN_REACH_LENGTH_M = 10_000.0

CONVEYANCE_RULES = ("cross_section", "single_cell")

_STAGE_BISECTION_STEPS = 60

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
    conveyance: str = "cross_section",
    min_reach_length_m: float = MIN_REACH_LENGTH_M,
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

    `conveyance` picks the channel depth rule (module docstring):
    `"cross_section"` (the default) or `"single_cell"`, the section-19 rule,
    kept so that first result stays reproducible. `min_reach_length_m` only
    applies to `"cross_section"`.
    """
    if dx <= 0:
        raise ValueError("dx must be positive")
    if conveyance not in CONVEYANCE_RULES:
        raise ValueError(f"conveyance must be one of {CONVEYANCE_RULES}")
    if min_reach_length_m <= 0:
        raise ValueError("min_reach_length_m must be positive")
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
    # Also records each cell's distance to the outlet along the flood's own
    # tree (the path it was reached by), which is what bins the channel into
    # reaches for the cross-section depth rule.
    Zf = flat_Z.astype(float).copy()
    visit = np.full(size, _UNREACHED, dtype=np.int64)  # flood visitation order
    channel_distance = np.full(size, np.inf)
    heap: list[tuple[float, int, int, float]] = []
    counter = 0
    seeded = set()
    for i in range(size):
        for j, pr, pc, dist in neighbors(i):
            if j is None and np.isfinite(Zp[pr, pc]) and i not in seeded:
                heapq.heappush(heap, (max(flat_Z[i], Zp[pr, pc]), counter, i, dist))
                counter += 1
                seeded.add(i)
    step = 0
    while heap:
        level, _, i, distance = heapq.heappop(heap)
        if visit[i] != _UNREACHED:
            continue
        Zf[i] = level
        visit[i] = step
        channel_distance[i] = distance
        step += 1
        for j, _, _, dist in neighbors(i):
            if j is not None and visit[j] == _UNREACHED:
                heapq.heappush(heap, (max(flat_Z[j], level), counter, j, distance + dist))
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
    routed: list[tuple[int, int, float]] = []  # (from, to or -1 for the outlet, m3/s)
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
            routed.append((i, -1 if j is None else j, share))
            if j is None:
                outflow += share
                exits[i] = True
            else:
                Q[j] += share

    conveying = Q > 0
    flat_N = N.ravel()

    # --- Drainage links, in flood order ----------------------------------------
    # drain[i] = the conveying cell a cell's steepest-descent path first
    # reaches (itself for a conveying cell, -1 if none). Flood order guarantees
    # each cell's downstream neighbors were resolved before it.
    drain = np.full(size, -1, dtype=np.int64)
    drain[conveying] = np.flatnonzero(conveying)
    for i in order[::-1]:
        i = int(i)
        if conveying[i] or visit[i] == _UNREACHED:
            continue
        interior = [(j, s) for j, _, _, s in downstream(i) if j is not None]
        if not interior:
            continue
        drain[i] = drain[max(interior, key=lambda js: js[1])[0]]

    # --- Channel water surface ---------------------------------------------------
    # Single-cell rule: the Manning normal depth that carries each conveying
    # cell's own Q across one cell width. Also the cross-section rule's
    # fallback for conveying cells the flood never reached.
    wse_channel = Zf.copy()
    manning = (Q[conveying] * flat_N[conveying] / (dx * np.sqrt(slope[conveying]))) ** 0.6
    wse_channel[conveying] = Zf[conveying] + manning
    on_slope_floor = conveying & (slope <= _MIN_SLOPE)
    channel_cells = np.flatnonzero(conveying & (visit != _UNREACHED))
    if conveyance == "cross_section" and channel_cells.size:
        # Equal reaches along the channel distance, each at least
        # min_reach_length_m long (a single reach on a short river).
        distance = channel_distance[channel_cells]
        start = distance.min()
        river_length = float(distance.max() - start) + dx
        n_reaches = max(1, int(river_length // min_reach_length_m))
        reach_length = river_length / n_reaches
        reach = np.full(size, -1, dtype=np.int64)
        reach[channel_cells] = np.minimum((distance - start) // reach_length, n_reaches - 1).astype(np.int64)
        # Each reach's discharge is what crosses its downstream end, into a
        # lower reach or out through the outlet.
        reach_discharge = np.zeros(n_reaches)
        for i, j, share in routed:
            if reach[i] >= 0 and (j < 0 or reach[j] < reach[i]):
                reach_discharge[reach[i]] += share
        members = np.flatnonzero(drain >= 0)
        member_reach = reach[drain[members]]
        for r in range(n_reaches):
            cells = members[member_reach == r]
            channel = drain[cells]
            reach_channel = cells[conveying[cells]]
            reach_slope = _reach_slope(channel_distance[reach_channel], Zf[reach_channel])
            stage = _solve_stage(
                reach_discharge[r],
                reach_slope,
                flat_Z[cells] - Zf[channel],
                flat_N[cells],
                dx * dx / reach_length,
            )
            wse_channel[reach_channel] = Zf[reach_channel] + stage
            on_slope_floor[reach_channel] = reach_slope <= _MIN_SLOPE

    # --- Pass 2: lateral (HAND-style) inundation ----------------------------------
    wse = flat_Z.astype(float).copy()
    wse[conveying] = wse_channel[conveying]
    lateral_idx = np.flatnonzero((~conveying) & (drain >= 0))
    surface = wse_channel[drain[lateral_idx]]
    wet = surface > flat_Z[lateral_idx]
    inundated_idx = lateral_idx[wet]
    wse[inundated_idx] = surface[wet]

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
        min_slope_cells=int(on_slope_floor.sum()),
    )


def _reach_slope(distances: np.ndarray, surface: np.ndarray) -> float:
    """Least-squares fall of the channel's conditioned surface per meter of
    channel distance across one reach, floored at `_MIN_SLOPE`."""
    if np.ptp(distances) == 0:
        return _MIN_SLOPE
    rise_per_meter = np.polyfit(distances, surface, 1)[0]
    return max(float(rise_per_meter), _MIN_SLOPE)


def _solve_stage(
    discharge: float,
    slope: float,
    bed_offset: np.ndarray,
    roughness: np.ndarray,
    strip_width: float,
) -> float:
    """Stage `h` above the channel surface at which a reach's cross-section
    conveys `discharge` (divided-channel method, one strip per cell).

    `bed_offset[k]` is cell k's height above the channel surface it drains to
    (its HAND); once `h` exceeds it, the cell is a strip of width
    `strip_width` and depth `h - bed_offset[k]` carrying
    `sqrt(S) / n_k * strip_width * depth^(5/3)`. Total conveyance is
    monotone in `h`, so bisection finds the root."""
    if discharge <= 0:
        return 0.0
    sqrt_slope = math.sqrt(slope)

    def conveyed(h: float) -> float:
        depth = h - bed_offset[bed_offset < h]
        return sqrt_slope * strip_width * float(np.sum(depth ** (5 / 3) / roughness[bed_offset < h]))

    low, high = 0.0, 1.0
    while conveyed(high) < discharge:
        low, high = high, 2 * high
    for _ in range(_STAGE_BISECTION_STEPS):
        mid = 0.5 * (low + high)
        if conveyed(mid) < discharge:
            low = mid
        else:
            high = mid
    return high
