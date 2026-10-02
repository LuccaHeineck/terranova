import type { Neighborhood } from '../types/simulation'
import type { ModelInputs } from './modelInputs'

/** The engine's neighbor offsets as (row, col) deltas, in the order the inspector's 3x3 panel lays them out. */
const MOORE: readonly [number, number][] = [
  [-1, -1], [-1, 0], [-1, 1],
  [0, -1], [0, 1],
  [1, -1], [1, 0], [1, 1],
]

export function isNeighbor(dr: number, dc: number, neighborhood: Neighborhood): boolean {
  return (dr !== 0 || dc !== 0) && (neighborhood === 'moore' || dr === 0 || dc === 0)
}

export interface NeighborShare {
  dr: number
  dc: number
  /** Off the grid: the engine pads the grid with walls, so no water goes there. */
  wall: boolean
  /** Water-surface elevation of the cell minus this neighbor's, m (positive: the neighbor is lower). */
  drop: number
  /** Fraction of the cell's outflow this neighbor receives (0 for walls and neighbors at or above it). */
  share: number
}

export interface OutflowSplit {
  /** The cell's own water-surface elevation Z + H, m. */
  wse: number
  depth: number
  neighbors: NeighborShare[]
  /** Whether any neighbor is lower, i.e. water here moves at all. */
  flows: boolean
}

/**
 * How one cell splits its outflow among its neighbors, at the given depth grid's water surface: a client-side
 * mirror of the weighting in the backend's simulation/engine.py `_single_update`, for explaining the transition
 * rule, not for simulating. Each lower neighbor gets a weight sqrt(drop / distance) / n, with n the receiving
 * neighbor's Manning's n and diagonals one sqrt(2) farther away; the shares are the weights normalized. Keep it
 * in sync with the engine by hand.
 *
 * Two simplifications, both said on the panel: neighbors off the grid are walls, so a gauge-driven run's south
 * outlet (the engine's boundary override) is not mirrored; and this is the split at one frame's water surface,
 * where the engine re-weighs it on every one of its sub-steps between frames.
 */
export function outflowSplit(
  inputs: ModelInputs,
  depth: Float32Array | null,
  row: number,
  col: number,
  neighborhood: Neighborhood,
): OutflowSplit {
  const { rows, cols, elevation, roughness } = inputs
  const wseAt = (cell: number) => elevation[cell] + (depth ? depth[cell] : 0)
  const center = row * cols + col
  const wse = wseAt(center)
  let total = 0
  const neighbors: NeighborShare[] = MOORE.filter(([dr, dc]) => isNeighbor(dr, dc, neighborhood)).map(([dr, dc]) => {
    const r = row + dr
    const c = col + dc
    if (r < 0 || r >= rows || c < 0 || c >= cols) return { dr, dc, wall: true, drop: 0, share: 0 }
    const cell = r * cols + c
    const drop = wse - wseAt(cell)
    const weight = drop > 0 ? Math.sqrt(drop / Math.hypot(dr, dc)) / roughness[cell] : 0
    total += weight
    return { dr, dc, wall: false, drop, share: weight }
  })
  for (const n of neighbors) n.share = total > 0 ? n.share / total : 0
  return { wse, depth: depth ? depth[center] : 0, neighbors, flows: total > 0 }
}
