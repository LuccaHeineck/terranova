import { useSimulationRun } from './hooks/useSimulationRun'
import { ConfigPanel } from './components/ConfigPanel'
import { FloodMap } from './components/FloodMap'
import { LogPanel } from './components/LogPanel'

export default function App() {
  const run = useSimulationRun()

  return (
    <div className="grid h-screen grid-cols-[280px_1fr_320px]">
      <ConfigPanel status={run.status} onStart={run.start} />
      <FloodMap bounds={run.bounds} frame={run.latestFrame} />
      <LogPanel status={run.status} gridShape={run.gridShape} bounds={run.bounds} log={run.log} error={run.error} />
    </div>
  )
}
