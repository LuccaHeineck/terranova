import { DEPTH_BANDS, FLOODED_DEPTH_THRESHOLD_M, OVERLAY_OPACITY } from '../rendering/depthToImage'

function bandLabel(min: number, max: number | null): string {
  return max === null ? `≥ ${min}` : `${min}–${max}`
}

/**
 * Depth -> color key for the flood overlay, read from the same DEPTH_BANDS the rasterizer uses. The maximum-depth
 * envelope shares the scale, under its own title and note.
 */
export function DepthLegend({ title = 'Water depth (m)', note }: { title?: string; note?: string }) {
  return (
    <div className="rounded bg-basalt/95 px-3 py-2 text-xs text-mist shadow-lg">
      <div className="mb-1.5 font-display text-[13px] font-semibold">{title}</div>
      <ul className="flex flex-col gap-1">
        {[...DEPTH_BANDS].reverse().map(({ min, max, color }) => (
          <li key={min} className="flex items-center gap-2">
            {/* On a white backing, so the swatch shows the color as composited over the light map. */}
            <span className="inline-flex rounded-sm bg-white p-px">
              <span className="inline-block h-3 w-5 rounded-[1px]" style={{ background: color, opacity: OVERLAY_OPACITY }} />
            </span>
            <span className="tabular-nums">{bandLabel(min, max)}</span>
          </li>
        ))}
      </ul>
      <div className="mt-1.5 max-w-48 text-mist-muted">
        Under {FLOODED_DEPTH_THRESHOLD_M} m: dry{note ? `. ${note}` : ''}
      </div>
    </div>
  )
}
