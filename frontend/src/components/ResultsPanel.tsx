import { useMemo } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { NEIGHBORHOOD_LABEL } from '../types/simulation'
import type { Bounds } from '../types/simulation'
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
  onGoToSetup: () => void
}

/** A mid-ramp depth blue for "temporal only", so the bar reads in the overlay's own colors. */
const TEMPORAL_COLOR = DEPTH_BANDS[1].color
const BOTH_FILL = `repeating-linear-gradient(135deg, ${TEMPORAL_COLOR} 0 4px, ${FAST_EXTENT_COLOR} 4px 8px)`

function formatDuration(seconds: number): string {
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`
  if (seconds < 120) return `${seconds.toFixed(1)} s`
  return `${(seconds / 60).toFixed(1)} min`
}

function wallClock(layer: ResultLayer): string {
  return `${formatDuration(layer.wallClockSeconds)}${layer.finished ? '' : ' so far'}`
}

function count(n: number): string {
  return n.toLocaleString('en-US')
}

function degrees(value: number, positive: string, negative: string): string {
  return `${Math.abs(value).toFixed(4)}° ${value < 0 ? negative : positive}`
}

/** A label/value row of a definition list. */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-mist-muted">{label}</dt>
      <dd className="text-right text-mist tabular-nums">{children}</dd>
    </div>
  )
}

/** The two flooded extents' overlap as one bar, each segment sized by its cell count. */
function AgreementBar({ agreement }: { agreement: ExtentAgreement }) {
  const total = agreement.both + agreement.temporalOnly + agreement.fastOnly
  const parts: { key: string; label: string; cells: number; fill: CSSProperties }[] = [
    { key: 'both', label: 'Both', cells: agreement.both, fill: { background: BOTH_FILL } },
    { key: 'temporal', label: 'Temporal only', cells: agreement.temporalOnly, fill: { background: TEMPORAL_COLOR } },
    { key: 'fast', label: 'Fast only', cells: agreement.fastOnly, fill: { background: FAST_EXTENT_COLOR } },
  ]
  return (
    <div className="flex flex-col gap-2">
      <div className="flex h-3 overflow-hidden rounded-sm bg-basalt-line" role="img" aria-label="Flooded-cell agreement">
        {total > 0 &&
          parts.map(({ key, cells, fill }) => (
            <span key={key} style={{ ...fill, width: `${(cells / total) * 100}%` }} className="h-full" />
          ))}
      </div>
      <dl className="flex flex-col gap-1 text-xs">
        {parts.map(({ key, label, cells, fill }) => (
          <div key={key} className="flex items-center gap-2">
            <span aria-hidden="true" className="h-2.5 w-2.5 shrink-0 rounded-sm" style={fill} />
            <dt className="text-mist-muted">{label}</dt>
            <dd className="ml-auto text-mist tabular-nums">
              {count(cells)} cells
              {total > 0 && <span className="ml-1.5 text-mist-muted">{Math.round((cells / total) * 100)}%</span>}
            </dd>
          </div>
        ))}
      </dl>
    </div>
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
    <Section title="Comparison">
      <p className="-mt-1 text-xs text-mist-muted">
        {temporal.resolution} m grid{followingLatest ? '' : ', temporal frame selected on the timeline'}. Flooded
        means depth &gt; {FLOODED_DEPTH_THRESHOLD_M} m.
      </p>
      {agreement && <AgreementBar agreement={agreement} />}

      <div className="flex flex-col gap-2 text-xs">
        <div className="flex flex-col gap-0.5 rounded bg-basalt-raised px-2.5 py-2">
          <span className="font-display text-sm font-semibold text-mist">Temporal CA</span>
          <dl className="flex flex-col gap-0.5">
            <Row label="Flooded">
              {count(temporalFlooded)} cells at t = {elapsedHours.toFixed(1)} h
            </Row>
            <Row label="Wall-clock">{wallClock(temporal)}</Row>
          </dl>
        </div>
        <div className="flex flex-col gap-0.5 rounded bg-basalt-raised px-2.5 py-2">
          <span className="font-display text-sm font-semibold text-mist">Fast</span>
          <dl className="flex flex-col gap-0.5">
            <Row label="Flooded">
              {count(fastFrame.flooded_cells ?? 0)} cells at the peak (t = {peakHours.toFixed(1)} h)
            </Row>
            <Row label="Engine">{formatDuration(fastFrame.compute_seconds ?? 0)}</Row>
            <Row label="Wall-clock">{wallClock(fast)}</Row>
          </dl>
        </div>
      </div>

      {temporal.neighborhood !== fast.neighborhood && (
        <Callout tone="warn">
          Different neighborhoods: the temporal run used {NEIGHBORHOOD_LABEL[temporal.neighborhood]}; the fast engine
          is {NEIGHBORHOOD_LABEL[fast.neighborhood]}-based. The validated agreement numbers are for Moore only.
        </Callout>
      )}
      {!reachedPeak && (
        <Callout tone="warn">
          The temporal run is at t = {elapsedHours.toFixed(1)} h of the {peakHours.toFixed(1)} h to the peak that the
          fast mode models, so the two extents are from different moments of the event.
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
  onGoToSetup,
}: ResultsPanelProps) {
  const { temporal, fast } = layers
  const ran = [
    temporal && `Temporal CA (${NEIGHBORHOOD_LABEL[temporal.neighborhood]})`,
    fast && 'Fast',
  ].filter(Boolean)
  const resolution = (temporal ?? fast)?.resolution
  const empty = status === 'idle' && !temporal && !fast && !error

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pt-1 pb-4">
      {error && <Callout tone="error">{error}</Callout>}

      {empty ? (
        <div className="flex flex-col items-start gap-3 rounded-md border border-dashed border-basalt-line p-4">
          <p className="text-[13px] leading-snug text-mist-muted">
            No results yet. Set up a run, or replay the May 2024 flood.
          </p>
          <button
            type="button"
            onClick={onGoToSetup}
            className="rounded border border-basalt-line px-3 py-1.5 text-[13px] text-mist hover:border-mist-muted"
          >
            Go to setup
          </button>
        </div>
      ) : (
        <Section title="This run">
          <dl className="flex flex-col gap-1 text-xs">
            {ran.length > 0 && <Row label={ran.length > 1 ? 'Engines' : 'Engine'}>{ran.join(', ')}</Row>}
            {resolution && <Row label="Grid">{resolution} m</Row>}
            {gridShape && (
              <Row label="Cells">
                {count(gridShape[0])} × {count(gridShape[1])}{' '}
                <span className="text-mist-muted">({count(gridShape[0] * gridShape[1])})</span>
              </Row>
            )}
            {bounds && (
              <>
                <Row label="West / east">
                  {degrees(bounds.west, 'E', 'W')} – {degrees(bounds.east, 'E', 'W')}
                </Row>
                <Row label="South / north">
                  {degrees(bounds.south, 'N', 'S')} – {degrees(bounds.north, 'N', 'S')}
                </Row>
              </>
            )}
          </dl>
        </Section>
      )}

      {temporal && temporalFrame && fast?.frame && (
        <Comparison temporal={temporal} fast={fast} temporalFrame={temporalFrame} followingLatest={followingLatest} />
      )}
    </div>
  )
}
