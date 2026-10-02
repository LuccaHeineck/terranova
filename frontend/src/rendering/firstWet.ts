import type { CompactFrame } from './depthGrid'
import { isWet } from './depthToImage'

/** What a first-wet time is measured in: real elapsed seconds (gauge-driven runs) or engine steps (seeded pool). */
export type FirstWetUnit = 'seconds' | 'step'

/**
 * When each cell of a temporal run first got wet (NaN: not yet), as of the frames received so far. Recorded as
 * frames arrive rather than derived from the timeline's buffer, since the buffer thins old frames: the time is
 * that of the first streamed frame the cell was wet in, so it is exact to within one frame interval. The array
 * sits in a private field for the same reason as DepthGrid's.
 */
export class FirstWetGrid {
  readonly rows: number
  readonly cols: number
  readonly unit: FirstWetUnit
  readonly #values: Float32Array

  constructor(values: Float32Array, rows: number, cols: number, unit: FirstWetUnit) {
    this.#values = values
    this.rows = rows
    this.cols = cols
    this.unit = unit
  }

  get values(): Float32Array {
    return this.#values
  }
}

/** A frame's time in `unit`. */
export function frameTime(frame: CompactFrame, unit: FirstWetUnit): number {
  return unit === 'seconds' ? (frame.elapsed_time ?? 0) : frame.step
}

/**
 * The first-wet grid after `frame`: a copy with the newly wet cells stamped, or `previous` itself if no cell got
 * wet for the first time (most frames, once the extent settles), so a long run doesn't copy it every frame.
 */
export function recordFirstWet(previous: FirstWetGrid | null, frame: CompactFrame, unit: FirstWetUnit): FirstWetGrid {
  const { rows, cols, values: depth } = frame.depth
  const time = frameTime(frame, unit)
  let values = previous?.values ?? null
  let copied = false
  for (let cell = 0; cell < depth.length; cell++) {
    if (!isWet(depth[cell]) || (values && !Number.isNaN(values[cell]))) continue
    if (!copied) {
      values = values ? values.slice() : new Float32Array(rows * cols).fill(NaN)
      copied = true
    }
    values![cell] = time
  }
  if (!copied) return previous ?? new FirstWetGrid(new Float32Array(rows * cols).fill(NaN), rows, cols, unit)
  return new FirstWetGrid(values!, rows, cols, unit)
}
