import { DepthGrid } from './depthGrid'
import type { CompactFrame } from './depthGrid'

/**
 * The maximum-depth envelope after `frame`: per cell, the deepest water any received frame had there. Recorded as
 * frames arrive, like the first-wet grid (firstWet.ts), rather than derived from the timeline's buffer, which thins
 * old frames and could drop the one at a cell's peak. A new grid whenever a cell got deeper (most frames while the
 * flood rises), else `previous` itself.
 *
 * Gauge-driven runs push the whole river's discharge into the few inflow-mask cells on step 1 (see DEPTH_BANDS in
 * depthToImage.ts), so those cells' envelope stays in the top band for the rest of the run.
 */
export function recordMaxDepth(previous: DepthGrid | null, frame: CompactFrame): DepthGrid {
  const { rows, cols, values: depth } = frame.depth
  if (!previous) return new DepthGrid(depth.slice(), rows, cols)
  const max = previous.values
  let values: Float32Array | null = null
  for (let cell = 0; cell < depth.length; cell++) {
    if (depth[cell] <= max[cell]) continue
    values ??= max.slice()
    values[cell] = depth[cell]
  }
  return values ? new DepthGrid(values, rows, cols) : previous
}
