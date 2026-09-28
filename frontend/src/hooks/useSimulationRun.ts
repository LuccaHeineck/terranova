import { useCallback, useEffect, useRef, useState } from 'react'
import { createSimulation } from '../api/client'
import { openSimulationStream } from '../api/stream'
import { MAY_2024_REPLAY } from '../presets'
import { toCompactFrame } from '../rendering/depthGrid'
import type { CompactFrame } from '../rendering/depthGrid'
import { appendFrame, createFrameBuffer } from '../rendering/frameBuffer'
import type { FrameBuffer } from '../rendering/frameBuffer'
import type { Bounds, Resolution, RunMode, SimulationFrame, SimulationParams } from '../types/simulation'

export type SimulationStatus = 'idle' | 'starting' | 'streaming' | 'done' | 'stopped' | 'error'

export type Engine = 'temporal' | 'fast'

/** The latest result of one engine, kept on screen for comparison with the other engine's. */
export interface ResultLayer {
  mode: RunMode
  resolution: Resolution
  /** The newest frame (for a temporal run, the tail of `history`). */
  frame: CompactFrame | null
  /**
   * Temporal runs only: every received frame, bounded by decimation, for the timeline. It lives and dies with
   * the layer, so the stale-state rules below apply to it unchanged, and a stopped run stays scrubbable.
   */
  history: FrameBuffer | null
  /** From submitting the run to its latest frame, or to done/stop. */
  wallClockSeconds: number
  finished: boolean
}

export type ResultLayers = Record<Engine, ResultLayer | null>

/** Most recent log lines kept in memory (and rendered); older ones are dropped. */
const MAX_LOG_LINES = 200

export function engineOf(mode: RunMode): Engine {
  return mode === 'fast' ? 'fast' : 'temporal'
}

/**
 * Whether a layer from the other engine still describes the same scenario as a new run.
 * Only the real May 2024 event exists in both engines (gauge-driven vs. fast), and only on the same grid.
 * Anything else is stale, not a comparison.
 */
function isComparable(layer: ResultLayer, mode: RunMode, resolution: Resolution): boolean {
  const scenarios = new Set([layer.mode, mode])
  return layer.resolution === resolution && scenarios.has('gauge_driven') && scenarios.has('fast')
}

function logLine(mode: RunMode, frame: SimulationFrame): string {
  if (mode === 'fast') {
    return (
      `fast: Q=${frame.peak_discharge_m3s?.toFixed(1)} m3/s, flooded=${frame.flooded_cells} cells, ` +
      `engine=${((frame.compute_seconds ?? 0) * 1000).toFixed(0)} ms, ` +
      `out=${frame.outflow_m3s?.toFixed(1)} retained=${frame.retained_m3s?.toFixed(1)} m3/s`
    )
  }
  const elapsedNote =
    frame.elapsed_time !== undefined ? `, elapsed=${(frame.elapsed_time / 60).toFixed(1)}min` : ''
  return `step ${frame.step}: volume=${frame.volume.toFixed(4)}${elapsedNote}`
}

/** A layer for a run that has started (or, in a replay, is queued) but has no frame yet. */
function pendingLayer(mode: RunMode, resolution: Resolution): ResultLayer {
  return { mode, resolution, frame: null, history: null, wallClockSeconds: 0, finished: false }
}

interface RunOptions {
  /** Called once the stream completes - never after a Stop, a newer run or an error. */
  onDone?: () => void
  /** Keep the previous run's log lines (the replay's fast line stays above the temporal run's). */
  keepLog?: boolean
}

export function useSimulationRun() {
  const [status, setStatus] = useState<SimulationStatus>('idle')
  const [gridShape, setGridShape] = useState<[number, number] | null>(null)
  const [bounds, setBounds] = useState<Bounds | null>(null)
  const [layers, setLayers] = useState<ResultLayers>({ temporal: null, fast: null })
  const [activeEngine, setActiveEngine] = useState<Engine>('temporal')
  // Incremented per run; lets the map reset its view to the engine just run.
  const [runCount, setRunCount] = useState(0)
  // True from the May 2024 replay preset until the next manual run: the map then opens on Compare.
  const [replayActive, setReplayActive] = useState(false)
  const [log, setLog] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const closeStreamRef = useRef<(() => void) | null>(null)
  // Callbacks from a superseded or stopped run check this and do nothing, so a
  // late message can never write into the current run's state.
  const runTokenRef = useRef(0)
  const startedAtRef = useRef(0)
  const activeEngineRef = useRef<Engine>('temporal')

  const finishLayer = useCallback((engine: Engine) => {
    const wallClockSeconds = (performance.now() - startedAtRef.current) / 1000
    setLayers((prev) => {
      const layer = prev[engine]
      return layer ? { ...prev, [engine]: { ...layer, finished: true, wallClockSeconds } } : prev
    })
  }, [])

  /**
   * After a Stop or an error: a layer that has a frame keeps it, now finished; a layer that never got one (a run
   * stopped before its first frame, or the replay's queued temporal run) goes, so no pane waits on nothing.
   */
  const settleLayers = useCallback(() => {
    const wallClockSeconds = (performance.now() - startedAtRef.current) / 1000
    const active = activeEngineRef.current
    setLayers((prev) => {
      const settle = (engine: Engine): ResultLayer | null => {
        const layer = prev[engine]
        if (!layer || layer.finished) return layer
        if (!layer.frame) return null
        return { ...layer, finished: true, wallClockSeconds: engine === active ? wallClockSeconds : layer.wallClockSeconds }
      }
      return { temporal: settle('temporal'), fast: settle('fast') }
    })
  }, [])

  const run = useCallback(
    async (params: SimulationParams, options: RunOptions = {}) => {
      closeStreamRef.current?.()
      closeStreamRef.current = null
      const token = ++runTokenRef.current
      const mode = params.mode ?? 'seeded_pool'
      const resolution = params.resolution ?? 30
      const engine = engineOf(mode)
      const other: Engine = engine === 'fast' ? 'temporal' : 'fast'

      setStatus('starting')
      setError(null)
      if (!options.keepLog) setLog([])
      setActiveEngine(engine)
      activeEngineRef.current = engine
      setRunCount((n) => n + 1)
      // This engine's previous result goes now, replaced by a pending layer (so its pane exists from the start);
      // the other engine's result stays only if it's still a like-for-like comparison.
      setLayers((prev) => ({
        [engine]: pendingLayer(mode, resolution),
        [other]: prev[other] && isComparable(prev[other], mode, resolution) ? prev[other] : null,
      }) as ResultLayers)
      startedAtRef.current = performance.now()

      try {
        const created = await createSimulation(params)
        if (token !== runTokenRef.current) return
        setGridShape(created.grid_shape)
        setBounds(created.bounds)
        setStatus('streaming')

        closeStreamRef.current = openSimulationStream(created.run_id, {
          onFrame: (frame) => {
            if (token !== runTokenRef.current) return
            const wallClockSeconds = (performance.now() - startedAtRef.current) / 1000
            const compact = toCompactFrame(frame)
            setLayers((prev) => {
              const layer = prev[engine]
              if (!layer) return prev
              const history =
                engine === 'temporal'
                  ? appendFrame(layer.history ?? createFrameBuffer(compact.depth), compact)
                  : null
              return {
                ...prev,
                [engine]: { ...layer, frame: compact, history, wallClockSeconds },
              }
            })
            // Capped at MAX_LOG_LINES: a gauge-driven run emits tens of thousands of
            // frames, and an uncapped array is both copied in full on every frame and
            // rendered one <li> per entry by LogPanel.
            setLog((prev) => [...prev.slice(-(MAX_LOG_LINES - 1)), logLine(mode, frame)])
          },
          onDone: () => {
            if (token !== runTokenRef.current) return
            finishLayer(engine)
            setStatus('done')
            options.onDone?.()
          },
          onError: (message) => {
            if (token !== runTokenRef.current) return
            settleLayers()
            setError(message)
            setStatus('error')
          },
        })
      } catch (e) {
        if (token !== runTokenRef.current) return
        settleLayers()
        setError(e instanceof Error ? e.message : String(e))
        setStatus('error')
      }
    },
    [finishLayer, settleLayers],
  )

  /** A run started from the config panel. */
  const start = useCallback(
    (params: SimulationParams) => {
      setReplayActive(false)
      return run(params)
    },
    [run],
  )

  /**
   * The May 2024 replay preset: the fast run, then - only if it completes - the temporal run to the peak.
   * The temporal layer is queued up front so Compare opens with both panes; it is comparable with the fast
   * run, so the fast run's start keeps it. Stop cancels the chain (the fast run's onDone never fires).
   */
  const startReplay = useCallback(() => {
    const { fast, temporal } = MAY_2024_REPLAY
    setReplayActive(true)
    setLayers({ temporal: pendingLayer(temporal.mode, temporal.resolution), fast: null })
    void run(fast, { onDone: () => void run(temporal, { keepLog: true }) })
  }, [run])

  /** Abandons the current run; its latest frame stays on screen (and available for comparison). */
  const stop = useCallback(() => {
    runTokenRef.current++
    closeStreamRef.current?.()
    closeStreamRef.current = null
    settleLayers()
    setStatus('stopped')
  }, [settleLayers])

  useEffect(() => () => closeStreamRef.current?.(), [])

  return {
    status,
    gridShape,
    bounds,
    layers,
    activeEngine,
    runCount,
    replayActive,
    log,
    error,
    start,
    startReplay,
    stop,
  }
}
