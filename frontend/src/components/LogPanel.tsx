import { useEffect, useMemo, useRef } from 'react'
import type { Bounds } from '../types/simulation'
import type { CompactFrame } from '../rendering/depthGrid'
import type { ResultLayer, ResultLayers, SimulationStatus } from '../hooks/useSimulationRun'
import { compareExtents, countFlooded, FLOODED_DEPTH_THRESHOLD_M } from '../rendering/depthToImage'

interface LogPanelProps {
  status: SimulationStatus
  gridShape: [number, number] | null
  bounds: Bounds | null
  layers: ResultLayers
  /** The temporal frame the timeline has selected; the comparison describes that one, as the map does. */
  temporalFrame: CompactFrame | null
  /** Whether that is the newest frame (following live / latest) rather than one scrubbed back to. */
  followingLatest: boolean
  log: string[]
  error: string | null
}

const STATUS_LABEL: Record<SimulationStatus, string> = {
  idle: 'Idle',
  starting: 'Starting…',
  streaming: 'Streaming',
  done: 'Done',
  stopped: 'Stopped',
  error: 'Error',
}

function formatDuration(seconds: number): string {
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`
  if (seconds < 120) return `${seconds.toFixed(1)} s`
  return `${(seconds / 60).toFixed(1)} min`
}

function wallClock(layer: ResultLayer): string {
  return `${formatDuration(layer.wallClockSeconds)}${layer.finished ? '' : ' so far'}`
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
    <div className="flex flex-col gap-1 rounded border border-gray-200 bg-white p-2 text-xs text-gray-700">
      <div className="font-semibold text-gray-900">
        Comparison ({temporal.resolution} m grid{followingLatest ? '' : ', temporal frame selected on the timeline'})
      </div>
      <div>
        <span className="font-medium">Temporal:</span> {temporalFlooded} cells flooded at t={elapsedHours.toFixed(1)} h,
        wall-clock {wallClock(temporal)}
      </div>
      <div>
        <span className="font-medium">Fast:</span> {fastFrame.flooded_cells} cells flooded at the peak (t=
        {peakHours.toFixed(1)} h), engine {formatDuration(fastFrame.compute_seconds ?? 0)}, wall-clock {wallClock(fast)}
      </div>
      {agreement && (
        <div>
          <span className="font-medium">Agreement:</span> {agreement.both} both, {agreement.temporalOnly} temporal only,{' '}
          {agreement.fastOnly} fast only
        </div>
      )}
      <div className="text-gray-500">Flooded means depth &gt; {FLOODED_DEPTH_THRESHOLD_M} m.</div>
      {!reachedPeak && (
        <div className="rounded border border-amber-300 bg-amber-50 p-1.5 text-amber-800">
          The temporal run is at t={elapsedHours.toFixed(1)} h of the {peakHours.toFixed(1)} h to the peak that the fast
          mode models, so the two extents are from different moments of the event.
        </div>
      )}
    </div>
  )
}

/** Pixels from the bottom within which the log still counts as scrolled to the end. */
const STICK_TO_BOTTOM_PX = 24

export function LogPanel({ status, gridShape, bounds, layers, temporalFrame, followingLatest, log, error }: LogPanelProps) {
  const { temporal, fast } = layers
  const logRef = useRef<HTMLUListElement | null>(null)
  const atBottomRef = useRef(true)

  // Follow new lines, unless the user has scrolled up to read older ones.
  useEffect(() => {
    const el = logRef.current
    if (el && atBottomRef.current) el.scrollTop = el.scrollHeight
  }, [log])

  return (
    <div className="flex h-full flex-col gap-3 border-l border-gray-200 bg-gray-50 p-4">
      <div>
        <span className="text-sm font-semibold text-gray-900">Status: </span>
        <span className="text-sm text-gray-700">{STATUS_LABEL[status]}</span>
      </div>

      {gridShape && (
        <div className="text-xs text-gray-500">
          grid_shape: [{gridShape[0]}, {gridShape[1]}]
        </div>
      )}

      {bounds && (
        <div className="text-xs text-gray-500">
          bounds: w={bounds.west.toFixed(4)} s={bounds.south.toFixed(4)} e={bounds.east.toFixed(4)} n=
          {bounds.north.toFixed(4)}
        </div>
      )}

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-700">{error}</div>
      )}

      {temporal && temporalFrame && fast?.frame && (
        <Comparison temporal={temporal} fast={fast} temporalFrame={temporalFrame} followingLatest={followingLatest} />
      )}

      <ul
        ref={logRef}
        onScroll={(e) => {
          const el = e.currentTarget
          atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_TO_BOTTOM_PX
        }}
        className="min-h-0 flex-1 overflow-y-auto rounded border border-gray-200 bg-white p-2 font-mono text-xs text-gray-700">
        {log.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
    </div>
  )
}
