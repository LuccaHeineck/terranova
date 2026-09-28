import { useSimulationRun } from './hooks/useSimulationRun'
import { ConfigPanel } from './components/ConfigPanel'
import { FloodMap } from './components/FloodMap'
import { LogPanel } from './components/LogPanel'

export default function App() {
  const run = useSimulationRun()

  return (
    <div className="grid h-screen grid-cols-[280px_1fr_320px] grid-rows-1 overflow-hidden">
      <ConfigPanel status={run.status} onStart={run.start} onStop={run.stop} />
      <FloodMap bounds={run.bounds} layers={run.layers} activeEngine={run.activeEngine} runCount={run.runCount} />
      <LogPanel
        status={run.status}
        gridShape={run.gridShape}
        bounds={run.bounds}
        layers={run.layers}
        log={run.log}
        error={run.error}
      />
    </div>
  )
}
