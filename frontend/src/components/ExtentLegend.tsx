import { FAST_EXTENT_COLOR, FLOODED_DEPTH_THRESHOLD_M, OVERLAY_OPACITY } from '../rendering/depthToImage'
import { useI18n } from '../i18n'

/** Key for the fast overlay: one flat color, because only the fast mode's extent is validated. */
export function ExtentLegend() {
  const { t } = useI18n()
  return (
    <div className="float-card max-w-56 rounded-xl px-3 py-2.5 text-xs text-ink">
      <div className="mb-2 text-[13px] font-semibold">{t.common.fastMode}</div>
      <div className="flex items-center gap-2">
        {/* On a white backing, so the swatch shows the color as composited over the light map. */}
        <span className="inline-flex shrink-0 rounded-[3px] bg-white p-px">
          <span
            className="inline-block h-3 w-5 rounded-[2px]"
            style={{ background: FAST_EXTENT_COLOR, opacity: OVERLAY_OPACITY }}
          />
        </span>
        <span>{t.legends.fastFlooded(FLOODED_DEPTH_THRESHOLD_M)}</span>
      </div>
      <div
        className="mt-1.5 text-[10.5px] text-ink-muted"
        title={t.legends.fastExtentOnlyTitle}
      >
        {t.legends.fastExtentOnly}
      </div>
    </div>
  )
}
