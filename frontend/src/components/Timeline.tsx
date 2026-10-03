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
  if (following && live) [state, stateClass] = ['Live', 'bg-danger/12 text-danger']
  else if (following) [state, stateClass] = ['Latest', 'bg-sunken text-ink']
  else if (playing) [state, stateClass] = ['Replaying', 'bg-accent/12 text-accent']
  else [state, stateClass] = ['Paused', 'bg-warn/12 text-warn']
  const fill = count > 1 ? (index / (count - 1)) * 100 : 100
  const bufferNote = `${count} frame${count === 1 ? '' : 's'} buffered (${fmt(megabytes)} MB)${
    buffer.stride > 1 ? `, every ${ordinal(buffer.stride)} received frame kept` : ''
  }`

  return (
    <div className="flex flex-col gap-2 border-t border-line bg-surface px-3 pt-2.5 pb-2.5 text-xs text-ink-muted sm:px-4">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={timeline.togglePlay}
          disabled={count < 2}
          aria-label={playing ? 'Pause replay' : 'Play buffered frames'}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-canvas shadow-sm transition-colors hover:bg-accent-strong disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-muted disabled:shadow-none"
        >
          {playing ? <IconPause className="h-4 w-4" /> : <IconPlay className="h-4 w-4" />}
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(0, count - 1)}
          value={index}
          onChange={(e) => timeline.select(Number(e.target.value))}
          aria-label={compare ? 'Temporal frame (temporal CA pane)' : 'Temporal frame'}
          className="range-ruler min-w-0 flex-1"
          style={{ '--fill': `${fill}%` } as CSSProperties}
        />
        {gauge && (
          <span className="shrink-0 text-ink tabular-nums" data-testid="timeline-time">
            <span className="font-serif text-2xl leading-none">{fmt(frame.elapsed_time! / 3600)}</span>
            <span className="ml-0.5 text-ink-muted">h</span>
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 tabular-nums" data-testid="timeline-readout">
        <span
          className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${stateClass}`}
          data-testid="timeline-state"
          title={bufferNote}
        >
          {following && live && (
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-danger motion-safe:animate-pulse" />
          )}
          {state}
        </span>
        <span>
          Frame <span className="text-ink">{index + 1}</span>/{count} · step{' '}
          <span className="text-ink">{frame.step.toLocaleString('en-US')}</span>
        </span>
        <span data-testid="timeline-flooded">
          <span className="text-ink">{flooded.toLocaleString('en-US')}</span> cells flooded
        </span>
        <span title="Volumes are summed cell depths (m), as the API reports them.">
          volume <span className="text-ink">{fmt(frame.volume)}</span>
        </span>
        {gauge && (
          <>
            <span>
              in <span className="text-ink">{fmt(inflow)}</span> / out <span className="text-ink">{fmt(outflow)}</span>
            </span>
            <span title="volume − (inflow − outflow): the engine's mass-conservation invariant">
              balance <span className="text-ink">{(frame.volume - (inflow - outflow)).toExponential(1)}</span>
            </span>
          </>
        )}
        <span className="sr-only" data-testid="timeline-buffer">
          {bufferNote}
        </span>
        <button
          type="button"
          onClick={timeline.jumpToLatest}
          disabled={following}
          className="ml-auto shrink-0 rounded-lg px-2 py-0.5 font-medium text-accent transition-colors hover:bg-accent/10 disabled:invisible"
        >
          {live ? 'Jump to live →' : 'Jump to latest →'}
        </button>
      </div>
    </div>
  )
}
