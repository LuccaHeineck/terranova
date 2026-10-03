import { DEPTH_BANDS, FLOODED_DEPTH_THRESHOLD_M, OVERLAY_OPACITY } from '../rendering/depthToImage'

/**
 * Depth -> color key for the flood overlay as one stepped scale, read from the same DEPTH_BANDS the rasterizer
 * uses. The maximum-depth envelope shares the scale, under its own title and note.
 */
export function DepthLegend({ title = 'Water depth', note }: { title?: string; note?: string }) {
  const last = DEPTH_BANDS[DEPTH_BANDS.length - 1]
  return (
    <div className="float-card w-60 rounded-xl px-3 py-2.5 text-xs text-ink">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-[13px] font-semibold">{title}</span>
        <span className="text-ink-muted">metres</span>
      </div>
      {/* On a white backing, so the swatches show the colors as composited over the light map. */}
      <div className="flex gap-px overflow-hidden rounded-[3px] bg-white p-px">
        {DEPTH_BANDS.map(({ min, color }) => (
          <span key={min} className="h-2.5 flex-1 first:rounded-l-[2px] last:rounded-r-[2px]" style={{ background: color, opacity: OVERLAY_OPACITY }} />
        ))}
      </div>
      <div className="mt-1 flex text-[10.5px] text-ink-muted tabular-nums">
        {DEPTH_BANDS.map(({ min }) => (
          <span key={min} className="flex-1">
            {min === last.min ? `${min}+` : min}
          </span>
        ))}
      </div>
      <div className="mt-1 text-[10.5px] text-ink-muted">
        Dry below {FLOODED_DEPTH_THRESHOLD_M} m{note ? `. ${note}` : ''}
      </div>
    </div>
  )
}
