import type { GridShape, SimulationFrame } from '../types/simulation'

/**
 * A depth grid as the client keeps it: row-major in one Float32Array (4 bytes per cell) instead of the wire
 * format's nested number[][].
 *
 * The array sits in a private field on purpose. React 19's dev-mode performance tracks diff every changed prop
 * with for...in, up to three levels deep, and a typed array reached that shallowly is enumerated element by
 * element into a performance.measure entry the browser keeps. With the grid as a plain `depth` property of
 * the timeline's frame, one 30m run (35,136 cells) retained 8.3 million such rows after 40 frames, and the tab
 * ran out of memory after ~1,200. A private field is invisible to for...in, so any object walk sees only
 * rows/cols.
 */
export class DepthGrid implements GridShape {
  readonly rows: number
  readonly cols: number
  readonly #values: Float32Array

  constructor(values: Float32Array, rows: number, cols: number) {
    this.#values = values
    this.rows = rows
    this.cols = cols
  }

  get values(): Float32Array {
    return this.#values
  }
}

/** A frame as the client keeps it: the wire frame with its depth grid compacted. */
export type CompactFrame = Omit<SimulationFrame, 'depth'> & { depth: DepthGrid }

/** Converts a wire frame once, on arrival; the nested arrays JSON.parse built are garbage right after. */
export function toCompactFrame(frame: SimulationFrame): CompactFrame {
  const rows = frame.depth.length
  const cols = frame.depth[0]?.length ?? 0
  const values = new Float32Array(rows * cols)
  for (let r = 0; r < rows; r++) values.set(frame.depth[r], r * cols)
  return { ...frame, depth: new DepthGrid(values, rows, cols) }
}
