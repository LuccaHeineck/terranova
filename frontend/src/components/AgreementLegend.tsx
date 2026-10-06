import { OVERLAY_OPACITY } from '../rendering/depthToImage'
import { AGREEMENT_COLORS, OBSERVED_COLOR } from '../rendering/observed'
import { useI18n } from '../i18n'

function Swatch({ color }: { color: string }) {
  return (
    // On a white backing, so the swatch shows the color as composited over the light map.
    <span className="inline-flex shrink-0 rounded-sm bg-white p-px">
      <span className="inline-block h-3 w-5 rounded-[1px]" style={{ background: color, opacity: OVERLAY_OPACITY }} />
    </span>
  )
}

const ROWS = [
  { color: AGREEMENT_COLORS.hit, key: 'hit' },
  { color: AGREEMENT_COLORS.missed, key: 'missed' },
  { color: AGREEMENT_COLORS.falseAlarm, key: 'falseAlarm' },
  { color: AGREEMENT_COLORS.notScored, key: 'notScored' },
] as const

/** Key for a pane drawn against the observed May 2024 extent, or for the observed extent alone. */
export function AgreementLegend({ mode, stageM }: { mode: 'agreement' | 'observed'; stageM: number }) {
  const { t } = useI18n()
  return (
    <div className="max-w-60 float-card rounded-xl px-3 py-2.5 text-xs text-ink">
      <div className="mb-2 text-[13px] font-semibold">
        {mode === 'agreement' ? t.legends.agreement : t.legends.observed}
      </div>
      {mode === 'agreement' ? (
        <ul className="flex flex-col gap-1">
          {ROWS.map(({ color, key }) => (
            <li key={key} className="flex items-center gap-2">
              <Swatch color={color} />
              {t.legends[key]}
            </li>
          ))}
        </ul>
      ) : (
        <div className="flex items-center gap-2">
          <Swatch color={OBSERVED_COLOR} />
          {t.legends.floodedInReference}
        </div>
      )}
      <div className="mt-1.5 text-[10.5px] leading-snug text-ink-muted">
        {t.legends.observedNote(stageM)}
        {mode === 'agreement' && t.legends.gapNote}
      </div>
    </div>
  )
}
