import { useMemo } from 'react'
import type { Timeline as TimelineState } from '../hooks/useTimeline'
import { bufferBytes } from '../rendering/frameBuffer'
import { countFlooded } from '../rendering/depthToImage'

interface TimelineProps {
  timeline: TimelineState
  /** In Compare, the timeline drives the temporal pane only; say so. */
  compare: boolean
}

function fmt(value: number, digits = 1): string {
  // Float noise just below zero (e.g. cumulative outflow early in a run) would otherwise print as "-0.0".
  const shown = Math.abs(value) < 0.5 * 10 ** -digits ? 0 : value
  return shown.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function ordinal(n: number): string {
  const tens = n % 100
  if (tens >= 11 && tens <= 13) return `${n}th`
  return `${n}${['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'}`
}

/** Slider, playback and readout for the buffered frames of the temporal run. */
export function Timeline({ timeline, compare }: TimelineProps) {
  const { buffer, frame, index, count, following, playing, live } = timeline
  const flooded = useMemo(() => (frame ? countFlooded(frame.depth) : 0), [frame])
  if (!buffer || !frame) return null

  const gauge = frame.elapsed_time !== undefined
  const inflow = frame.cumulative_inflow ?? 0
  const outflow = frame.cumulative_outflow ?? 0
  const megabytes = bufferBytes(buffer) / 2 ** 20

  let state: string
  let stateClass: string
  if (following && live) [state, stateClass] = ['● Live', 'text-red-700']
  else if (following) [state, stateClass] = ['Latest frame', 'text-gray-700']
  else if (playing) [state, stateClass] = ['Replaying', 'text-blue-700']
  else [state, stateClass] = ['Paused', 'text-amber-700']

  return (
    <div className="flex flex-col gap-1.5 border-t border-gray-300 bg-white px-3 py-2 text-xs text-gray-700">
      <div className="flex items-center gap-2">
        <span className="font-semibold text-gray-900">{compare ? 'Timeline: temporal CA pane' : 'Timeline'}</span>
        <span className={`font-medium ${stateClass}`} data-testid="timeline-state">
          {state}
        </span>
        <span className="ml-auto text-gray-500" data-testid="timeline-buffer">
          {count} frame{count === 1 ? '' : 's'} buffered ({fmt(megabytes)} MB)
          {buffer.stride > 1 ? `, every ${ordinal(buffer.stride)} received frame kept` : ''}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={timeline.togglePlay}
          disabled={count < 2}
          aria-label={playing ? 'Pause replay' : 'Play buffered frames'}
          className="w-16 rounded bg-gray-100 px-2 py-1 text-gray-800 hover:bg-gray-200 disabled:opacity-40"
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(0, count - 1)}
          value={index}
          onChange={(e) => timeline.select(Number(e.target.value))}
          aria-label="Temporal frame"
          className="min-w-0 flex-1 accent-blue-700"
        />
        <button
          type="button"
          onClick={timeline.jumpToLatest}
          disabled={following}
          className="w-24 rounded bg-gray-100 px-2 py-1 text-gray-800 hover:bg-gray-200 disabled:invisible"
        >
          {live ? 'Jump to live' : 'Jump to latest'}
        </button>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-0.5 tabular-nums" data-testid="timeline-readout">
        <span>
          Frame {index + 1}/{count}, step {frame.step.toLocaleString('en-US')}
        </span>
        {gauge && <span data-testid="timeline-time">t = {fmt(frame.elapsed_time! / 3600)} h</span>}
        <span data-testid="timeline-flooded">{flooded.toLocaleString('en-US')} cells flooded</span>
        <span>volume {fmt(frame.volume)}</span>
        {gauge && (
          <>
            <span>in {fmt(inflow)}</span>
            <span>out {fmt(outflow)}</span>
            <span title="volume − (inflow − outflow): the engine's mass-conservation invariant">
              balance {(frame.volume - (inflow - outflow)).toExponential(1)}
            </span>
          </>
        )}
      </div>
      <div className="text-gray-500">Volumes are summed cell depths (m), as the API reports them.</div>
    </div>
  )
}
