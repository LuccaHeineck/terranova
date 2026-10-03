import { OVERLAY_OPACITY } from '../rendering/depthToImage'
import { arrivalBandLabel } from '../rendering/arrivalTime'
import type { ArrivalBand } from '../rendering/arrivalTime'
import type { FirstWetUnit } from '../rendering/firstWet'

/** Key for the arrival-time overlay, earliest band at the top. */
export function ArrivalLegend({ bands, unit }: { bands: readonly ArrivalBand[]; unit: FirstWetUnit }) {
  return (
    <div className="float-card max-w-56 rounded-xl px-3 py-2.5 text-xs text-ink">
      <div className="mb-2 text-[13px] font-semibold">
        {unit === 'seconds' ? 'First flooded (h into the event)' : 'First flooded (engine step)'}
      </div>
      <ul className="flex flex-col gap-1">
        {bands.map((band) => (
          <li key={band.min} className="flex items-center gap-2">
            {/* On a white backing, so the swatch shows the color as composited over the light map. */}
            <span className="inline-flex rounded-sm bg-white p-px">
              <span
                className="inline-block h-3 w-5 rounded-[1px]"
                style={{ background: band.color, opacity: OVERLAY_OPACITY }}
              />
            </span>
            <span className="tabular-nums">{arrivalBandLabel(band, unit)}</span>
          </li>
        ))}
      </ul>
      <div className="mt-1.5 text-[10.5px] leading-snug text-ink-muted">Cells wet by the timeline's t. Darker: reached sooner.</div>
    </div>
  )
}
