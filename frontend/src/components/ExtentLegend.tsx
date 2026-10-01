import { FAST_EXTENT_COLOR, FLOODED_DEPTH_THRESHOLD_M, OVERLAY_OPACITY } from '../rendering/depthToImage'

/** Key for the fast overlay: one flat color, because the fast mode's depths are not calibrated. */
export function ExtentLegend() {
  return (
    <div className="max-w-52 rounded bg-basalt/95 px-3 py-2 text-xs text-mist shadow-lg">
      <div className="mb-1.5 font-display text-[13px] font-semibold">Fast mode</div>
      <div className="flex items-center gap-2">
        {/* On a white backing, so the swatch shows the color as composited over the light map. */}
        <span className="inline-flex shrink-0 rounded-sm bg-white p-px">
          <span
            className="inline-block h-3 w-5 rounded-[1px]"
            style={{ background: FAST_EXTENT_COLOR, opacity: OVERLAY_OPACITY }}
          />
        </span>
        <span>Flooded (depth &gt; {FLOODED_DEPTH_THRESHOLD_M} m)</span>
      </div>
      <div className="mt-1.5 text-mist-muted">Extent only: the fast mode's depths are not calibrated.</div>
    </div>
  )
}
