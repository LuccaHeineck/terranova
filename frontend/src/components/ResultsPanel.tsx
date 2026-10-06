import { useMemo } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { NEIGHBORHOOD_LABEL } from '../types/simulation'
import type { Bounds, HydrographRecord } from '../types/simulation'
import type { CompactFrame } from '../rendering/depthGrid'
import type { ResultLayer, ResultLayers, SimulationStatus } from '../hooks/useSimulationRun'
import {
  compareExtents,
  countFlooded,
  DEPTH_BANDS,
  FAST_EXTENT_COLOR,
  FLOODED_DEPTH_THRESHOLD_M,
} from '../rendering/depthToImage'
import type { ExtentAgreement } from '../rendering/depthToImage'
import { scoreAgainstObserved } from '../rendering/observed'
import type { ObservedMasks } from '../rendering/observed'
import { int, messages, num, useI18n } from '../i18n'
import { HydrographChart } from './HydrographChart'
import { Callout } from './ui/Callout'
import { Section } from './ui/Section'

interface ResultsPanelProps {
  status: SimulationStatus
  gridShape: [number, number] | null
  bounds: Bounds | null
  layers: ResultLayers
  /** The temporal frame the timeline has selected; the comparison describes that one, as the map does. */
  temporalFrame: CompactFrame | null
  /** Whether that is the newest frame (following live / latest) rather than one scrubbed back to. */
  followingLatest: boolean
  error: string | null
  /** The observed May 2024 extent, if the API serves it; scored only against runs on its grid. */
  observed: ObservedMasks | null
  /** The May 2024 gauge record, if the API serves it; charted while a real-event run is shown. */
  hydrograph: HydrographRecord | null
  onGoToSetup: () => void
}

/** A mid-ramp depth blue for "temporal only", so the bar reads in the overlay's own colors. */
const TEMPORAL_COLOR = DEPTH_BANDS[1].color
const BOTH_FILL = `repeating-linear-gradient(135deg, ${TEMPORAL_COLOR} 0 4px, ${FAST_EXTENT_COLOR} 4px 8px)`

function formatDuration(seconds: number): string {
  if (seconds < 1) return `${num(seconds * 1000)} ms`
  if (seconds < 120) return `${num(seconds, 1)} s`
  return `${num(seconds / 60, 1)} min`
}

function wallClock(layer: ResultLayer): string {
  return `${formatDuration(layer.wallClockSeconds)}${layer.finished ? '' : messages().results.soFar}`
}

type Compass = keyof ReturnType<typeof messages>['common']['compass']

function degrees(value: number, positive: Compass, negative: Compass): string {
  const { compass } = messages().common
  return `${num(Math.abs(value), 4)}° ${compass[value < 0 ? negative : positive]}`
}

/** A label/value row of a definition list. */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-right text-ink tabular-nums">{children}</dd>
    </div>
  )
}

/** The two flooded extents' overlap as one bar, each segment sized by its cell count. */
function AgreementBar({ agreement }: { agreement: ExtentAgreement }) {
  const { t } = useI18n()
  const total = agreement.both + agreement.temporalOnly + agreement.fastOnly
  const parts: { key: string; label: string; cells: number; fill: CSSProperties }[] = [
    { key: 'both', label: t.results.both, cells: agreement.both, fill: { background: BOTH_FILL } },
    { key: 'temporal', label: t.results.temporalOnly, cells: agreement.temporalOnly, fill: { background: TEMPORAL_COLOR } },
    { key: 'fast', label: t.results.fastOnly, cells: agreement.fastOnly, fill: { background: FAST_EXTENT_COLOR } },
  ]
  return (
    <div className="flex flex-col gap-2">
      <div className="flex h-2.5 overflow-hidden rounded-full bg-line" role="img" aria-label={t.results.agreement}>
        {total > 0 &&
          parts.map(({ key, cells, fill }) => (
            <span key={key} style={{ ...fill, width: `${(cells / total) * 100}%` }} className="h-full" />
          ))}
      </div>
      <dl className="flex flex-col gap-1 text-xs">
        {parts.map(({ key, label, cells, fill }) => (
          <div key={key} className="flex items-center gap-2">
            <span aria-hidden="true" className="h-2.5 w-2.5 shrink-0 rounded-sm" style={fill} />
            <dt className="text-ink-muted">{label}</dt>
            <dd className="ml-auto text-ink tabular-nums">
              {t.common.cells(cells)}
              {total > 0 && <span className="ml-1.5 text-ink-muted">{Math.round((cells / total) * 100)}%</span>}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function metric(value: number | null): string {
  return value === null ? messages().common.na : num(value, 2)
}

interface ScoredRun {
  key: string
  name: string
  /** When in the event the scored frame is. */
  when: string
  frame: CompactFrame
}

/** One run's frame scored against the observed extent: gap-corrected CSI first, then its parts. */
function ScoreCard({ run, observed }: { run: ScoredRun; observed: ObservedMasks }) {
  const { t } = useI18n()
  const agreement = useMemo(() => scoreAgainstObserved(run.frame.depth, observed), [run.frame, observed])
  if (!agreement) return null
  const { corrected, naive } = agreement
  return (
    <div className="flex flex-col gap-1.5 rounded-xl bg-surface px-3 py-2.5 text-xs ring-1 ring-line">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[13px] font-semibold text-ink">{run.name}</span>
        <span className="text-ink-muted">{run.when}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-serif text-[40px] leading-none text-ink tabular-nums">{metric(corrected.csi)}</span>
        <span className="text-ink-muted">{t.results.csiCorrected}</span>
      </div>
      <dl className="mt-1 flex flex-col gap-0.5 border-t border-line pt-1.5">
        <Row label={t.results.hitRate}>{metric(corrected.hitRate)}</Row>
        <Row label={t.results.falseAlarmRate}>{metric(corrected.falseAlarmRate)}</Row>
        <Row label={t.results.hitMissedFalse}>
          {int(corrected.tp)} / {int(corrected.fn)} / {int(corrected.fp)}
        </Row>
        <Row label={t.results.naiveCsi}>{metric(naive.csi)}</Row>
      </dl>
    </div>
  )
}

interface ObservedScoresProps {
  temporal: ResultLayer | null
  fast: ResultLayer | null
  temporalFrame: CompactFrame | null
  observed: ObservedMasks
}

/**
 * The runs on the map scored against the observed May 2024 extent, live: the temporal one at the frame the
 * timeline has selected. Only real-event runs are scored (a synthetic seeded pool has nothing to match), and
 * only on the grid the observation is on.
 */
function ObservedScores({ temporal, fast, temporalFrame, observed }: ObservedScoresProps) {
  const { t } = useI18n()
  const runs: ScoredRun[] = []
  const scorable = (layer: ResultLayer | null) => layer && layer.mode !== 'seeded_pool'
  if (scorable(temporal) && temporalFrame) {
    runs.push({
      key: 'temporal',
      name: t.common.temporalCa,
      when: t.common.tHours((temporalFrame.elapsed_time ?? 0) / 3600),
      frame: temporalFrame,
    })
  }
  if (scorable(fast) && fast!.frame) runs.push({ key: 'fast', name: t.common.fast, when: t.results.atPeak, frame: fast!.frame })

  const resolutions = [temporal, fast].filter(scorable).map((layer) => layer!.resolution)
  if (runs.length === 0 && resolutions.length === 0) return null
  const onGrid = resolutions.every((r) => r === observed.resolution)

  return (
    <Section title={t.results.observed}>
      <p className="-mt-1 text-xs leading-snug text-ink-muted">{t.results.observedIntro(observed.stageM, observed.excludedCount)}</p>
      {onGrid ? (
        runs.map((run) => <ScoreCard key={run.key} run={run} observed={observed} />)
      ) : (
        <Callout tone="info">
          {t.results.wrongGrid(observed.resolution, resolutions.find((r) => r !== observed.resolution))}
        </Callout>
      )}
    </Section>
  )
}

interface ComparisonProps {
  temporal: ResultLayer
  fast: ResultLayer
  temporalFrame: CompactFrame
  followingLatest: boolean
}

/** Shown only when both engines have a result for the same scenario and grid (see useSimulationRun). */
function Comparison({ temporal, fast, temporalFrame, followingLatest }: ComparisonProps) {
  const { t } = useI18n()
  const fastFrame = fast.frame!
  const agreement = useMemo(
    () => compareExtents(temporalFrame.depth, fastFrame.depth),
    [temporalFrame, fastFrame],
  )
  const temporalFlooded = useMemo(() => countFlooded(temporalFrame.depth), [temporalFrame])
  const elapsedHours = (temporalFrame.elapsed_time ?? 0) / 3600
  const peakHours = (fastFrame.peak_elapsed_time ?? 0) / 3600
  // The temporal run's final frame lands exactly on the peak; allow float noise.
  const reachedPeak = elapsedHours >= peakHours - 1e-6

  return (
    <Section title={t.results.comparison}>
      <p className="-mt-1 text-xs text-ink-muted">
        {t.results.comparisonIntro(temporal.resolution, followingLatest, FLOODED_DEPTH_THRESHOLD_M)}
      </p>
      {agreement && <AgreementBar agreement={agreement} />}

      <div className="flex flex-col gap-2 text-xs">
        <div className="flex flex-col gap-1 rounded-xl bg-surface px-3 py-2.5 ring-1 ring-line">
          <span className="text-[13px] font-semibold text-ink">{t.common.temporalCa}</span>
          <dl className="flex flex-col gap-0.5">
            <Row label={t.results.flooded}>{t.results.floodedAt(temporalFlooded, elapsedHours)}</Row>
            <Row label={t.results.wallClock}>{wallClock(temporal)}</Row>
          </dl>
        </div>
        <div className="flex flex-col gap-1 rounded-xl bg-surface px-3 py-2.5 ring-1 ring-line">
          <span className="text-[13px] font-semibold text-ink">{t.common.fast}</span>
          <dl className="flex flex-col gap-0.5">
            <Row label={t.results.flooded}>{t.results.floodedAtPeak(fastFrame.flooded_cells ?? 0, peakHours)}</Row>
            <Row label={t.results.engineTime}>{formatDuration(fastFrame.compute_seconds ?? 0)}</Row>
            <Row label={t.results.wallClock}>{wallClock(fast)}</Row>
          </dl>
        </div>
      </div>

      {temporal.neighborhood !== fast.neighborhood && (
        <Callout tone="warn">
          {t.results.differentNeighborhoods(NEIGHBORHOOD_LABEL[temporal.neighborhood], NEIGHBORHOOD_LABEL[fast.neighborhood])}
        </Callout>
      )}
      {!reachedPeak && (
        <Callout tone="warn">
          {t.results.notAtPeak(elapsedHours, peakHours)}
        </Callout>
      )}
    </Section>
  )
}

/** The Results tab: what ran, on which grid, and - with both engines - how their extents agree. */
export function ResultsPanel({
  status,
  gridShape,
  bounds,
  layers,
  temporalFrame,
  followingLatest,
  error,
  observed,
  hydrograph,
  onGoToSetup,
}: ResultsPanelProps) {
  const { t } = useI18n()
  const { temporal, fast } = layers
  const ran = [temporal && t.results.ranTemporal(NEIGHBORHOOD_LABEL[temporal.neighborhood]), fast && t.common.fast].filter(
    Boolean,
  )
  const resolution = (temporal ?? fast)?.resolution
  const empty = status === 'idle' && !temporal && !fast && !error

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-4 pt-1 pb-5">
      {error && <Callout tone="error">{error}</Callout>}

      {empty ? (
        <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-line p-5">
          <p className="text-[13px] leading-snug text-ink-muted">
            {t.results.empty}
          </p>
          <button
            type="button"
            onClick={onGoToSetup}
            className="rounded-lg bg-surface px-3 py-1.5 text-[13px] font-medium text-ink ring-1 ring-line hover:bg-sunken"
          >
            {t.results.goToSetup}
          </button>
        </div>
      ) : (
        <Section title={t.results.thisRun}>
          <dl className="flex flex-col gap-1 text-xs">
            {ran.length > 0 && <Row label={ran.length > 1 ? t.results.engines : t.results.engine}>{ran.join(', ')}</Row>}
            {resolution && <Row label={t.results.grid}>{resolution} m</Row>}
            {gridShape && (
              <Row label={t.results.cells}>
                {int(gridShape[0])} × {int(gridShape[1])}{' '}
                <span className="text-ink-muted">({int(gridShape[0] * gridShape[1])})</span>
              </Row>
            )}
            {bounds && (
              <>
                <Row label={t.results.westEast}>
                  {degrees(bounds.west, 'E', 'W')} – {degrees(bounds.east, 'E', 'W')}
                </Row>
                <Row label={t.results.southNorth}>
                  {degrees(bounds.south, 'N', 'S')} – {degrees(bounds.north, 'N', 'S')}
                </Row>
              </>
            )}
          </dl>
        </Section>
      )}

      {hydrograph && (temporal?.mode === 'gauge_driven' || fast) && (
        <Section title={t.results.hydrograph}>
          <HydrographChart
            record={hydrograph}
            markerSeconds={temporal?.mode === 'gauge_driven' ? (temporalFrame?.elapsed_time ?? null) : null}
          />
        </Section>
      )}

      {observed && <ObservedScores temporal={temporal} fast={fast} temporalFrame={temporalFrame} observed={observed} />}

      {temporal && temporalFrame && fast?.frame && (
        <Comparison temporal={temporal} fast={fast} temporalFrame={temporalFrame} followingLatest={followingLatest} />
      )}
    </div>
  )
}
