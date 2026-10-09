import { useMemo } from 'react'
import type { CSSProperties } from 'react'
import { PLAYBACK_SPEEDS } from '../hooks/useTimeline'
import type { Timeline as TimelineState } from '../hooks/useTimeline'
import { bufferBytes } from '../rendering/frameBuffer'
import { countFlooded } from '../rendering/depthToImage'
import { exp, int, num, useI18n } from '../i18n'
import { IconPause, IconPlay } from './ui/icons'

interface TimelineProps {
  timeline: TimelineState
  /** In Compare, the timeline drives the temporal pane only; say so. */
  compare: boolean
}

/** Slider, playback and readout for the buffered frames of the temporal run. */
export function Timeline({ timeline, compare }: TimelineProps) {
  const { t } = useI18n()
  const { buffer, frame, index, count, following, playing, live, speed } = timeline
  const flooded = useMemo(() => (frame ? countFlooded(frame.depth) : 0), [frame])
  if (!buffer || !frame) return null

  const gauge = frame.elapsed_time !== undefined
  const inflow = frame.cumulative_inflow ?? 0
  const outflow = frame.cumulative_outflow ?? 0
  const megabytes = bufferBytes(buffer) / 2 ** 20

  let state: string
  let stateClass: string
  if (following && live) [state, stateClass] = [t.timeline.live, 'bg-danger/12 text-danger']
  else if (following) [state, stateClass] = [t.timeline.latest, 'bg-sunken text-ink']
  else if (playing) [state, stateClass] = [t.timeline.replaying, 'bg-accent/12 text-accent']
  else [state, stateClass] = [t.timeline.paused, 'bg-warn/12 text-warn']
  const fill = count > 1 ? (index / (count - 1)) * 100 : 100
  const bufferNote = t.timeline.buffer(count, megabytes, buffer.stride)
  const nextSpeed = PLAYBACK_SPEEDS[(PLAYBACK_SPEEDS.indexOf(speed) + 1) % PLAYBACK_SPEEDS.length]

  return (
    <div className="flex flex-col gap-2 border-t border-line bg-surface px-3 pt-2.5 pb-2.5 text-xs text-ink-muted sm:px-4">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={timeline.togglePlay}
          disabled={count < 2}
          aria-label={playing ? t.timeline.pause : t.timeline.play}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-canvas shadow-sm transition-colors hover:bg-accent-strong disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-muted disabled:shadow-none"
        >
          {playing ? <IconPause className="h-4 w-4" /> : <IconPlay className="h-4 w-4" />}
        </button>
        <button
          type="button"
          onClick={timeline.cycleSpeed}
          disabled={count < 2}
          aria-label={t.timeline.speed(speed, nextSpeed)}
          title={t.timeline.speed(speed, nextSpeed)}
          data-testid="timeline-speed"
          className="h-7 w-10 shrink-0 rounded-lg bg-sunken font-medium text-ink tabular-nums transition-colors hover:bg-line disabled:cursor-not-allowed disabled:text-ink-muted"
        >
          {speed}×
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(0, count - 1)}
          value={index}
          onChange={(e) => timeline.select(Number(e.target.value))}
          aria-label={compare ? t.timeline.frameAriaCompare : t.timeline.frameAria}
          className="range-ruler min-w-0 flex-1"
          style={{ '--fill': `${fill}%` } as CSSProperties}
        />
        {gauge && (
          <span className="shrink-0 text-ink tabular-nums" data-testid="timeline-time">
            <span className="font-serif text-2xl leading-none">{num(frame.elapsed_time! / 3600, 1)}</span>
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
          {t.timeline.frame} <span className="text-ink">{index + 1}</span>/{count} · {t.timeline.step}{' '}
          <span className="text-ink">{int(frame.step)}</span>
        </span>
        <span data-testid="timeline-flooded">
          <span className="text-ink">{int(flooded)}</span> {t.timeline.cellsFlooded}
        </span>
        <span title={t.timeline.volumeTitle}>
          {t.timeline.volume} <span className="text-ink">{num(frame.volume, 1)}</span>
        </span>
        {gauge && (
          <>
            <span>
              {t.timeline.in} <span className="text-ink">{num(inflow, 1)}</span> / {t.timeline.out}{' '}
              <span className="text-ink">{num(outflow, 1)}</span>
            </span>
            <span title={t.timeline.balanceTitle}>
              {t.timeline.balance} <span className="text-ink">{exp(frame.volume - (inflow - outflow))}</span>
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
          {live ? t.timeline.jumpLive : t.timeline.jumpLatest}
        </button>
      </div>
    </div>
  )
}
