import { useCallback, useEffect, useRef, useState } from 'react'
import { createSimulation } from '../api/client'
import { openSimulationStream } from '../api/stream'
import type { Bounds, SimulationFrame, SimulationParams } from '../types/simulation'

export type SimulationStatus = 'idle' | 'starting' | 'streaming' | 'done' | 'error'

/** Most recent log lines kept in memory (and rendered); older ones are dropped. */
const MAX_LOG_LINES = 200

export function useSimulationRun() {
  const [status, setStatus] = useState<SimulationStatus>('idle')
  const [gridShape, setGridShape] = useState<[number, number] | null>(null)
  const [bounds, setBounds] = useState<Bounds | null>(null)
  const [latestFrame, setLatestFrame] = useState<SimulationFrame | null>(null)
  const [log, setLog] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const closeStreamRef = useRef<(() => void) | null>(null)

  const start = useCallback(async (params: SimulationParams) => {
    closeStreamRef.current?.()
    setStatus('starting')
    setError(null)
    setLog([])
    setLatestFrame(null)

    try {
      const created = await createSimulation(params)
      setGridShape(created.grid_shape)
      setBounds(created.bounds)
      setStatus('streaming')

      closeStreamRef.current = openSimulationStream(created.run_id, {
        onFrame: (frame) => {
          setLatestFrame(frame)
          const elapsedNote =
            frame.elapsed_time !== undefined ? `, elapsed=${(frame.elapsed_time / 60).toFixed(1)}min` : ''
          // Capped at MAX_LOG_LINES: a gauge-driven run emits tens of thousands of
          // frames, and an uncapped array is both copied in full on every frame and
          // rendered one <li> per entry by LogPanel.
          setLog((prev) => [
            ...prev.slice(-(MAX_LOG_LINES - 1)),
            `step ${frame.step}: volume=${frame.volume.toFixed(4)}${elapsedNote}`,
          ])
        },
        onDone: () => setStatus('done'),
        onError: (message) => {
          setError(message)
          setStatus('error')
        },
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('error')
    }
  }, [])

  useEffect(() => () => closeStreamRef.current?.(), [])

  return { status, gridShape, bounds, latestFrame, log, error, start }
}
