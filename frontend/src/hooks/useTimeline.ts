import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { indexAtOrBefore } from '../rendering/frameBuffer'
import type { FrameBuffer } from '../rendering/frameBuffer'
import type { CompactFrame } from '../rendering/depthGrid'
import type { ResultLayer } from './useSimulationRun'

/** Replay speed of the buffered frames at 1x: a full 30m buffer (238 frames) plays in ~30 s. */
export const PLAYBACK_FPS = 8

/** The replay speeds offered, as multiples of PLAYBACK_FPS. */
export const PLAYBACK_SPEEDS = [1, 4, 16] as const
export type PlaybackSpeed = (typeof PLAYBACK_SPEEDS)[number]

/**
 * The most frames a second the replay draws. Past it a faster speed skips buffered frames instead of drawing
 * each one: every frame is a full overlay repaint, and 128 of them a second would outrun the browser.
 */
const MAX_DRAWN_FPS = 32

/**
 * Which buffered frame is shown. `step: null` follows the newest frame (live, or the latest once the run
 * ends). A selection is a step, not an index, because thinning the buffer shifts indices: a paused view
 * snaps to the nearest kept frame at or before its step. Tagged with the buffer it was made in, so a new
 * run starts following again.
 */
interface Cursor {
  bufferId: number | null
  step: number | null
  playing: boolean
}

export interface Timeline {
  buffer: FrameBuffer | null
  /** The selected frame, or null when the temporal layer has none yet. */
  frame: CompactFrame | null
  index: number
  count: number
  following: boolean
  playing: boolean
  /** The run is still streaming frames into the buffer. */
  live: boolean
  speed: PlaybackSpeed
  /** Steps to the next of PLAYBACK_SPEEDS, wrapping around; applies at once, even mid-replay. */
  cycleSpeed: () => void
  select: (index: number) => void
  jumpToLatest: () => void
  togglePlay: () => void
}

export function useTimeline(layer: ResultLayer | null, live: boolean): Timeline {
  const buffer = layer?.history ?? null
  const bufferId = buffer?.id ?? null
  const [stored, setCursor] = useState<Cursor>({ bufferId: null, step: null, playing: false })
  // The speed outlives runs: it is how this viewer likes to watch a replay, not part of one.
  const [speed, setSpeed] = useState<PlaybackSpeed>(1)
  const cycleSpeed = useCallback(
    () => setSpeed((current) => PLAYBACK_SPEEDS[(PLAYBACK_SPEEDS.indexOf(current) + 1) % PLAYBACK_SPEEDS.length]),
    [],
  )
  const cursor = useMemo<Cursor>(
    () => (stored.bufferId === bufferId ? stored : { bufferId, step: null, playing: false }),
    [stored, bufferId],
  )

  const count = buffer?.entries.length ?? 0
  const following = cursor.step === null
  const index = !buffer || count === 0 ? -1 : following ? count - 1 : indexAtOrBefore(buffer, cursor.step!)
  const frame = index >= 0 ? buffer!.entries[index].frame : null

  // The playback interval reads the newest buffer without restarting on every frame.
  const bufferRef = useRef(buffer)
  useEffect(() => {
    bufferRef.current = buffer
  }, [buffer])

  const select = useCallback(
    (i: number) => {
      if (!buffer) return
      // Dragging to the newest frame resumes following it; anywhere else pauses auto-follow there.
      const step = i >= buffer.entries.length - 1 ? null : buffer.entries[i].frame.step
      setCursor({ bufferId: buffer.id, step, playing: false })
    },
    [buffer],
  )

  const jumpToLatest = useCallback(() => setCursor({ bufferId, step: null, playing: false }), [bufferId])

  const togglePlay = useCallback(() => {
    if (!buffer || buffer.entries.length === 0) return
    if (cursor.playing) {
      setCursor({ ...cursor, playing: false })
      return
    }
    // From the newest frame there is nothing ahead, so play restarts from the first.
    const atEnd = cursor.step === null || index >= buffer.entries.length - 1
    setCursor({ bufferId: buffer.id, step: atEnd ? buffer.entries[0].frame.step : cursor.step, playing: true })
  }, [buffer, cursor, index])

  useEffect(() => {
    if (!cursor.playing) return
    const framesPerSecond = PLAYBACK_FPS * speed
    const drawnPerSecond = Math.min(framesPerSecond, MAX_DRAWN_FPS)
    const advance = Math.round(framesPerSecond / drawnPerSecond)
    const timer = setInterval(() => {
      setCursor((prev) => {
        const current = bufferRef.current
        if (!current || prev.bufferId !== current.id || prev.step === null) return { ...prev, playing: false }
        const next = indexAtOrBefore(current, prev.step) + advance
        const last = current.entries.length - 1
        if (next < last) return { ...prev, step: current.entries[next].frame.step }
        // Reached the newest frame: stop there, following it - which, if the run is still live, means live.
        return { ...prev, step: null, playing: false }
      })
    }, 1000 / drawnPerSecond)
    return () => clearInterval(timer)
  }, [cursor.playing, speed])

  return {
    buffer,
    frame,
    index,
    count,
    following,
    playing: cursor.playing,
    live,
    speed,
    cycleSpeed,
    select,
    jumpToLatest,
    togglePlay,
  }
}
