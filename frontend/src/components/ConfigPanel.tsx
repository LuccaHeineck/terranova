import { useState } from 'react'
import type { FormEvent } from 'react'
import type { SimulationParams } from '../types/simulation'
import type { SimulationStatus } from '../hooks/useSimulationRun'

interface ConfigPanelProps {
  status: SimulationStatus
  onStart: (params: SimulationParams) => void
}

// A seeded-pool run is a few hundred steps, so a frame every 5 is fine. A
// gauge-driven run covers the whole real May 2024 event in 100k+ engine steps -
// at an interval of 5 that would be tens of thousands of WebSocket frames, so it
// defaults far coarser. Switching modes resets the field to that mode's default;
// the user can still type any value afterwards.
const DEFAULT_FRAME_INTERVAL: Record<'seeded_pool' | 'gauge_driven', number> = {
  seeded_pool: 5,
  gauge_driven: 500,
}

export function ConfigPanel({ status, onStart }: ConfigPanelProps) {
  const [mode, setMode] = useState<'seeded_pool' | 'gauge_driven'>('seeded_pool')
  const [steps, setSteps] = useState(200)
  const [frameInterval, setFrameInterval] = useState(DEFAULT_FRAME_INTERVAL.seeded_pool)
  const [outflowFraction, setOutflowFraction] = useState(0.5)

  const busy = status === 'starting' || status === 'streaming'

  const selectMode = (next: 'seeded_pool' | 'gauge_driven') => {
    setMode(next)
    setFrameInterval(DEFAULT_FRAME_INTERVAL[next])
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const params: SimulationParams = {
      mode,
      frame_interval: frameInterval,
      outflow_fraction: outflowFraction,
      ...(mode === 'seeded_pool' ? { steps } : {}),
    }
    onStart(params)
  }

  return (
    <form onSubmit={handleSubmit} className="flex h-full flex-col gap-4 border-r border-gray-200 bg-gray-50 p-4">
      <h1 className="text-lg font-semibold text-gray-900">Terranova</h1>
      <p className="text-sm text-gray-500">Vale do Taquari flood simulation</p>

      <fieldset className="flex flex-col gap-1 text-sm text-gray-700">
        <legend className="mb-1">Run mode</legend>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="mode"
            checked={mode === 'seeded_pool'}
            disabled={busy}
            onChange={() => selectMode('seeded_pool')}
          />
          Synthetic seeded pool
        </label>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="mode"
            checked={mode === 'gauge_driven'}
            disabled={busy}
            onChange={() => selectMode('gauge_driven')}
          />
          Real May 2024 event (gauge-driven)
        </label>
      </fieldset>

      {mode === 'seeded_pool' && (
        <label className="flex flex-col gap-1 text-sm text-gray-700">
          Steps
          <input
            type="number"
            min={1}
            value={steps}
            disabled={busy}
            onChange={(e) => setSteps(Number(e.target.value))}
            className="rounded border border-gray-300 px-2 py-1 disabled:opacity-50"
          />
        </label>
      )}

      <label className="flex flex-col gap-1 text-sm text-gray-700">
        Frame interval
        <input
          type="number"
          min={1}
          value={frameInterval}
          disabled={busy}
          onChange={(e) => setFrameInterval(Number(e.target.value))}
          className="rounded border border-gray-300 px-2 py-1 disabled:opacity-50"
        />
      </label>

      <label className="flex flex-col gap-1 text-sm text-gray-700">
        Outflow fraction
        <input
          type="number"
          min={0.01}
          max={1}
          step={0.01}
          value={outflowFraction}
          disabled={busy}
          onChange={(e) => setOutflowFraction(Number(e.target.value))}
          className="rounded border border-gray-300 px-2 py-1 disabled:opacity-50"
        />
      </label>

      <button
        type="submit"
        disabled={busy}
        className="mt-2 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {busy ? 'Running…' : 'Start simulation'}
      </button>
    </form>
  )
}
