import { OVERLAY_OPACITY } from '../rendering/depthToImage'
import { AGREEMENT_COLORS, OBSERVED_COLOR } from '../rendering/observed'

function Swatch({ color }: { color: string }) {
  return (
    // On a white backing, so the swatch shows the color as composited over the light map.
    <span className="inline-flex shrink-0 rounded-sm bg-white p-px">
      <span className="inline-block h-3 w-5 rounded-[1px]" style={{ background: color, opacity: OVERLAY_OPACITY }} />
    </span>
  )
}

const ROWS = [
  { color: AGREEMENT_COLORS.hit, label: 'Hit: flooded in both' },
  { color: AGREEMENT_COLORS.missed, label: 'Missed: observed only' },
  { color: AGREEMENT_COLORS.falseAlarm, label: 'False alarm: simulated only' },
  { color: AGREEMENT_COLORS.notScored, label: 'Not scored: reference gap' },
]

/** Key for a pane drawn against the observed May 2024 extent, or for the observed extent alone. */
export function AgreementLegend({ mode, stageM }: { mode: 'agreement' | 'observed'; stageM: number }) {
  return (
    <div className="max-w-60 float-card rounded-xl px-3 py-2.5 text-xs text-ink">
      <div className="mb-2 text-[13px] font-semibold">
        {mode === 'agreement' ? 'Against the observed flood' : 'Observed flood, May 2024'}
      </div>
      {mode === 'agreement' ? (
        <ul className="flex flex-col gap-1">
          {ROWS.map(({ color, label }) => (
            <li key={label} className="flex items-center gap-2">
              <Swatch color={color} />
              {label}
            </li>
          ))}
        </ul>
      ) : (
        <div className="flex items-center gap-2">
          <Swatch color={OBSERVED_COLOR} />
          Flooded in the reference
        </div>
      )}
      <div className="mt-1.5 text-[10.5px] leading-snug text-ink-muted">
        SGB/CPRM extent at the {stageM.toFixed(2)} m peak stage.
        {mode === 'agreement' && ' Estrela-side cells the reference never modeled are not scored.'}
      </div>
    </div>
  )
}
