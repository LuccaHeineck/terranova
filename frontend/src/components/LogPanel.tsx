import type { Bounds } from '../types/simulation'
import type { SimulationStatus } from '../hooks/useSimulationRun'

interface LogPanelProps {
  status: SimulationStatus
  gridShape: [number, number] | null
  bounds: Bounds | null
  log: string[]
  error: string | null
}

const STATUS_LABEL: Record<SimulationStatus, string> = {
  idle: 'Idle',
  starting: 'Starting…',
  streaming: 'Streaming',
  done: 'Done',
  error: 'Error',
}

export function LogPanel({ status, gridShape, bounds, log, error }: LogPanelProps) {
  return (
    <div className="flex h-full flex-col gap-3 border-l border-gray-200 bg-gray-50 p-4">
      <div>
        <span className="text-sm font-semibold text-gray-900">Status: </span>
        <span className="text-sm text-gray-700">{STATUS_LABEL[status]}</span>
      </div>

      {gridShape && (
        <div className="text-xs text-gray-500">
          grid_shape: [{gridShape[0]}, {gridShape[1]}]
        </div>
      )}

      {bounds && (
        <div className="text-xs text-gray-500">
          bounds: w={bounds.west.toFixed(4)} s={bounds.south.toFixed(4)} e={bounds.east.toFixed(4)} n=
          {bounds.north.toFixed(4)}
        </div>
      )}

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-700">{error}</div>
      )}

      <ul className="flex-1 overflow-y-auto rounded border border-gray-200 bg-white p-2 font-mono text-xs text-gray-700">
        {log.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
    </div>
  )
}
