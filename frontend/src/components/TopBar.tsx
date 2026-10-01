import type { Resolution } from '../types/simulation'
import type { SimulationStatus } from '../hooks/useSimulationRun'
import { RUN_SETUP_FORM_ID } from './ConfigPanel'
import { IconPlay, IconStop } from './ui/icons'

interface TopBarProps {
  status: SimulationStatus
  gridShape: [number, number] | null
  /** The grid the shown result ran on, if any. */
  resolution: Resolution | null
  onStop: () => void
}

const STATUS: Record<SimulationStatus, { label: string; dot: string }> = {
  idle: { label: 'Idle', dot: 'bg-mist-muted' },
  starting: { label: 'Starting…', dot: 'bg-gauge motion-safe:animate-pulse' },
  streaming: { label: 'Streaming', dot: 'bg-gauge motion-safe:animate-pulse' },
  done: { label: 'Done', dot: 'bg-mist' },
  stopped: { label: 'Stopped', dot: 'bg-mist-muted' },
  error: { label: 'Error', dot: 'bg-danger' },
}

/** Wordmark, run status and the one primary action: Start, or Stop while a run is going. */
export function TopBar({ status, gridShape, resolution, onStop }: TopBarProps) {
  const busy = status === 'starting' || status === 'streaming'
  const { label, dot } = STATUS[status]

  return (
    <header className="flex items-center gap-4 border-b border-basalt-line bg-basalt px-4">
      <div className="flex min-w-0 items-baseline gap-2.5">
        <span className="font-display text-xl font-semibold tracking-wide text-mist">Terranova</span>
        <span className="hidden truncate text-[13px] text-mist-muted sm:inline">Vale do Taquari flood simulation</span>
      </div>

      <div className="ml-auto flex items-center gap-4 text-[13px]">
        {gridShape && resolution && (
          <span className="hidden text-mist-muted tabular-nums md:inline">
            {gridShape[0].toLocaleString('en-US')} × {gridShape[1].toLocaleString('en-US')} cells, {resolution} m grid
          </span>
        )}
        <span role="status" className="flex items-center gap-2 rounded-full bg-basalt-raised px-2.5 py-1 text-mist">
          <span aria-hidden="true" className={`h-2 w-2 rounded-full ${dot}`} />
          {label}
        </span>

        {/* Distinct keys: if React reused one <button> and flipped its type from "button" to "submit"
            during the Stop click, the click's default action would submit the form and start a new run. */}
        {busy ? (
          <button
            key="stop"
            type="button"
            onClick={onStop}
            className="flex items-center gap-1.5 rounded border border-mist-muted px-3 py-1.5 font-medium text-mist transition-colors hover:border-mist hover:bg-basalt-raised"
          >
            <IconStop className="h-4 w-4" />
            Stop
          </button>
        ) : (
          <button
            key="start"
            type="submit"
            form={RUN_SETUP_FORM_ID}
            className="flex items-center gap-1.5 rounded bg-gauge px-3 py-1.5 font-semibold text-basalt transition-colors hover:bg-gauge-strong"
          >
            <IconPlay className="h-4 w-4" />
            Start simulation
          </button>
        )}
      </div>
    </header>
  )
}
