import { useSimulationRun } from './hooks/useSimulationRun'
import { useTimeline } from './hooks/useTimeline'
import { ConfigPanel } from './components/ConfigPanel'
import { FloodMap } from './components/FloodMap'
import { LogPanel } from './components/LogPanel'

export default function App() {
  const run = useSimulationRun()
  const timeline = useTimeline(run.layers.temporal, run.status === 'starting' || run.status === 'streaming')

  return (
    <div className="grid h-screen grid-cols-[280px_1fr_320px] grid-rows-1 overflow-hidden">
      <ConfigPanel status={run.status} onStart={run.start} onReplay={run.startReplay} onStop={run.stop} />
      <FloodMap
        bounds={run.bounds}
        layers={run.layers}
        activeEngine={run.activeEngine}
        runCount={run.runCount}
        replayActive={run.replayActive}
        timeline={timeline}
      />
      <LogPanel
        status={run.status}
        gridShape={run.gridShape}
        bounds={run.bounds}
        layers={run.layers}
        temporalFrame={timeline.frame}
        followingLatest={timeline.following}
        log={run.log}
        error={run.error}
      />
    </div>
  )
}
