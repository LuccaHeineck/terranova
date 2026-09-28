import { DEPTH_BANDS, FLOODED_DEPTH_THRESHOLD_M, OVERLAY_OPACITY } from '../rendering/depthToImage'

function bandLabel(min: number, max: number | null): string {
  return max === null ? `≥ ${min}` : `${min}–${max}`
}

/** Depth -> color key for the flood overlay, read from the same DEPTH_BANDS the rasterizer uses. */
export function DepthLegend() {
  return (
    <div className="rounded-md bg-white/95 px-3 py-2 text-xs text-gray-700 shadow-md">
      <div className="mb-1.5 font-semibold text-gray-900">Water depth (m)</div>
      <ul className="flex flex-col gap-1">
        {[...DEPTH_BANDS].reverse().map(({ min, max, color }) => (
          <li key={min} className="flex items-center gap-2">
            <span
              className="inline-block h-3 w-5 rounded-sm"
              style={{ background: color, opacity: OVERLAY_OPACITY }}
            />
            <span className="tabular-nums">{bandLabel(min, max)}</span>
          </li>
        ))}
      </ul>
      <div className="mt-1.5 text-gray-500">Under {FLOODED_DEPTH_THRESHOLD_M} m: dry</div>
    </div>
  )
}
