import { FAST_EXTENT_COLOR, FLOODED_DEPTH_THRESHOLD_M, OVERLAY_OPACITY } from '../rendering/depthToImage'

/** Key for the fast overlay: one flat color, because the fast mode's depths are not calibrated. */
export function ExtentLegend() {
  return (
    <div className="max-w-52 rounded-md bg-white/95 px-3 py-2 text-xs text-gray-700 shadow-md">
      <div className="mb-1.5 font-semibold text-gray-900">Fast mode</div>
      <div className="flex items-center gap-2">
        <span
          className="inline-block h-3 w-5 shrink-0 rounded-sm"
          style={{ background: FAST_EXTENT_COLOR, opacity: OVERLAY_OPACITY }}
        />
        <span>Flooded (depth &gt; {FLOODED_DEPTH_THRESHOLD_M} m)</span>
      </div>
      <div className="mt-1.5 text-gray-500">Extent only: the fast mode's depths are not calibrated.</div>
    </div>
  )
}
