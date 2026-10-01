import { useMemo } from 'react'
import type { CSSProperties } from 'react'
import type { Timeline as TimelineState } from '../hooks/useTimeline'
import { bufferBytes } from '../rendering/frameBuffer'
import { countFlooded } from '../rendering/depthToImage'
import { IconPause, IconPlay } from './ui/icons'

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
  if (following && live) [state, stateClass] = ['Live', 'bg-danger/15 text-[#ff8a8d]']
  else if (following) [state, stateClass] = ['Latest frame', 'bg-basalt-raised text-mist']
  else if (playing) [state, stateClass] = ['Replaying', 'bg-gauge/15 text-gauge']
  else [state, stateClass] = ['Paused', 'bg-ochre/15 text-ochre']
  const fill = count > 1 ? (index / (count - 1)) * 100 : 100

  return (
    <div className="flex flex-col gap-2 border-t border-basalt-line bg-basalt px-4 pt-2.5 pb-3 text-xs text-mist-muted">
      <div className="flex items-center gap-2.5">
        <span className="font-display text-sm font-semibold text-mist">{compare ? 'Timeline: temporal CA pane' : 'Timeline'}</span>
        <span
          className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${stateClass}`}
          data-testid="timeline-state"
        >
          {following && live && (
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-danger motion-safe:animate-pulse" />
          )}
          {state}
        </span>
        <span className="ml-auto truncate" data-testid="timeline-buffer">
          {count} frame{count === 1 ? '' : 's'} buffered ({fmt(megabytes)} MB)
          {buffer.stride > 1 ? `, every ${ordinal(buffer.stride)} received frame kept` : ''}
        </span>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={timeline.togglePlay}
          disabled={count < 2}
          aria-label={playing ? 'Pause replay' : 'Play buffered frames'}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gauge text-basalt transition-colors hover:bg-gauge-strong disabled:cursor-not-allowed disabled:bg-basalt-raised disabled:text-mist-muted"
        >
          {playing ? <IconPause className="h-4 w-4" /> : <IconPlay className="h-4 w-4" />}
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(0, count - 1)}
          value={index}
          onChange={(e) => timeline.select(Number(e.target.value))}
          aria-label="Temporal frame"
          className="range-ruler min-w-0 flex-1"
          style={{ '--fill': `${fill}%` } as CSSProperties}
        />
        {gauge && (
          <span className="shrink-0 font-display text-lg font-semibold text-mist tabular-nums" data-testid="timeline-time">
            t = {fmt(frame.elapsed_time! / 3600)} h
          </span>
        )}
        <button
          type="button"
          onClick={timeline.jumpToLatest}
          disabled={following}
          className="shrink-0 rounded border border-basalt-line px-2.5 py-1 text-mist transition-colors hover:border-mist-muted disabled:invisible"
        >
          {live ? 'Jump to live' : 'Jump to latest'}
        </button>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-0.5 tabular-nums" data-testid="timeline-readout">
        <span>
          Frame <span className="text-mist">{index + 1}</span>/{count}, step{' '}
          <span className="text-mist">{frame.step.toLocaleString('en-US')}</span>
        </span>
        <span data-testid="timeline-flooded">
          <span className="text-mist">{flooded.toLocaleString('en-US')}</span> cells flooded
        </span>
        <span>
          volume <span className="text-mist">{fmt(frame.volume)}</span>
        </span>
        {gauge && (
          <>
            <span>
              in <span className="text-mist">{fmt(inflow)}</span>
            </span>
            <span>
              out <span className="text-mist">{fmt(outflow)}</span>
            </span>
            <span title="volume − (inflow − outflow): the engine's mass-conservation invariant">
              balance <span className="text-mist">{(frame.volume - (inflow - outflow)).toExponential(1)}</span>
            </span>
          </>
        )}
        <span className="ml-auto">Volumes are summed cell depths (m), as the API reports them.</span>
      </div>
    </div>
  )
}
