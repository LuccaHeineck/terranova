import { useState } from 'react'
import type { FormEvent } from 'react'
import type { SimulationParams } from '../types/simulation'
import type { SimulationStatus } from '../hooks/useSimulationRun'

interface ConfigPanelProps {
  status: SimulationStatus
  onStart: (params: SimulationParams) => void
}

export function ConfigPanel({ status, onStart }: ConfigPanelProps) {
  const [steps, setSteps] = useState(200)
  const [frameInterval, setFrameInterval] = useState(5)
  const [outflowFraction, setOutflowFraction] = useState(0.5)

  const busy = status === 'starting' || status === 'streaming'

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    onStart({ steps, frame_interval: frameInterval, outflow_fraction: outflowFraction })
  }

  return (
    <form onSubmit={handleSubmit} className="flex h-full flex-col gap-4 border-r border-gray-200 bg-gray-50 p-4">
      <h1 className="text-lg font-semibold text-gray-900">Terranova</h1>
      <p className="text-sm text-gray-500">Vale do Taquari flood simulation</p>

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
