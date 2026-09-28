import { useCallback, useEffect, useRef, useState } from 'react'
import { createSimulation } from '../api/client'
import { openSimulationStream } from '../api/stream'
import type { Bounds, Resolution, RunMode, SimulationFrame, SimulationParams } from '../types/simulation'

export type SimulationStatus = 'idle' | 'starting' | 'streaming' | 'done' | 'stopped' | 'error'

export type Engine = 'temporal' | 'fast'

/** The latest result of one engine, kept on screen for comparison with the other engine's. */
export interface ResultLayer {
  mode: RunMode
  resolution: Resolution
  frame: SimulationFrame | null
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

export function useSimulationRun() {
  const [status, setStatus] = useState<SimulationStatus>('idle')
  const [gridShape, setGridShape] = useState<[number, number] | null>(null)
  const [bounds, setBounds] = useState<Bounds | null>(null)
  const [layers, setLayers] = useState<ResultLayers>({ temporal: null, fast: null })
  const [activeEngine, setActiveEngine] = useState<Engine>('temporal')
  // Incremented per run; lets the map reset its view to the engine just run.
  const [runCount, setRunCount] = useState(0)
  const [log, setLog] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const closeStreamRef = useRef<(() => void) | null>(null)
  // Callbacks from a superseded or stopped run check this and do nothing, so a
  // late message can never write into the current run's state.
  const runTokenRef = useRef(0)
  const startedAtRef = useRef(0)

  const finishLayer = useCallback((engine: Engine) => {
    const wallClockSeconds = (performance.now() - startedAtRef.current) / 1000
    setLayers((prev) => {
      const layer = prev[engine]
      return layer ? { ...prev, [engine]: { ...layer, finished: true, wallClockSeconds } } : prev
    })
  }, [])

  const start = useCallback(
    async (params: SimulationParams) => {
      closeStreamRef.current?.()
      closeStreamRef.current = null
      const token = ++runTokenRef.current
      const mode = params.mode ?? 'seeded_pool'
      const resolution = params.resolution ?? 30
      const engine = engineOf(mode)
      const other: Engine = engine === 'fast' ? 'temporal' : 'fast'

      setStatus('starting')
      setError(null)
      setLog([])
      setActiveEngine(engine)
      setRunCount((n) => n + 1)
      // This engine's previous result goes now, not when the new one's first frame arrives;
      // the other engine's result stays only if it's still a like-for-like comparison.
      setLayers((prev) => ({
        [engine]: null,
        [other]: prev[other] && isComparable(prev[other], mode, resolution) ? prev[other] : null,
      }) as ResultLayers)
      startedAtRef.current = performance.now()

      try {
        const created = await createSimulation(params)
        if (token !== runTokenRef.current) return
        setGridShape(created.grid_shape)
        setBounds(created.bounds)
        setStatus('streaming')
        setLayers((prev) => ({
          ...prev,
          [engine]: { mode, resolution, frame: null, wallClockSeconds: 0, finished: false },
        }))

        closeStreamRef.current = openSimulationStream(created.run_id, {
          onFrame: (frame) => {
            if (token !== runTokenRef.current) return
            const wallClockSeconds = (performance.now() - startedAtRef.current) / 1000
            setLayers((prev) => {
              const layer = prev[engine]
              if (!layer) return prev
              return {
                ...prev,
                [engine]: { ...layer, frame, wallClockSeconds },
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
          },
          onError: (message) => {
            if (token !== runTokenRef.current) return
            setError(message)
            setStatus('error')
          },
        })
      } catch (e) {
        if (token !== runTokenRef.current) return
        setError(e instanceof Error ? e.message : String(e))
        setStatus('error')
      }
    },
    [finishLayer],
  )

  /** Abandons the current run; its latest frame stays on screen (and available for comparison). */
  const stop = useCallback(() => {
    runTokenRef.current++
    closeStreamRef.current?.()
    closeStreamRef.current = null
    finishLayer(activeEngine)
    setStatus('stopped')
  }, [activeEngine, finishLayer])

  useEffect(() => () => closeStreamRef.current?.(), [])

  return { status, gridShape, bounds, layers, activeEngine, runCount, log, error, start, stop }
}
