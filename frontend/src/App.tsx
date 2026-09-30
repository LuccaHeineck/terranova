import { useSimulationRun } from './hooks/useSimulationRun'
import { useTimeline } from './hooks/useTimeline'
import { useGrids } from './hooks/useGrids'
import { useRunSetup } from './hooks/useRunSetup'
import { ConfigPanel } from './components/ConfigPanel'
import { FloodMap } from './components/FloodMap'
import { LogPanel } from './components/LogPanel'

export default function App() {
  const run = useSimulationRun()
  const busy = run.status === 'starting' || run.status === 'streaming'
  const timeline = useTimeline(run.layers.temporal, busy)
  const setup = useRunSetup()
  const { grids, error: gridsError } = useGrids()
  const grid = grids?.[setup.resolution] ?? null
  // The seed marker and the outline it must fall in only exist for a seeded-pool setup; clicks place it
  // only while no run is going, like every other form field.
  const footprint = setup.seeding && grid ? grid.footprint : null
  const { placeSeed } = setup
  const onMapClick = footprint && !busy ? (point: { lat: number; lon: number }) => placeSeed(point, footprint) : null

  return (
    <div className="grid h-screen grid-cols-[280px_1fr_320px] grid-rows-1 overflow-hidden">
      <ConfigPanel
        status={run.status}
        setup={setup}
        seedPlacementError={gridsError}
        onStart={run.start}
        onReplay={run.startReplay}
        onStop={run.stop}
      />
      <FloodMap
        // Before the first run, frame the selected grid so its outline can be clicked.
        bounds={run.bounds ?? grid?.bounds ?? null}
        layers={run.layers}
        activeEngine={run.activeEngine}
        runCount={run.runCount}
        replayActive={run.replayActive}
        timeline={timeline}
        footprint={footprint}
        seedMarker={setup.seeding ? setup.seed : null}
        onMapClick={onMapClick}
        seedNotice={setup.seeding ? setup.seedNotice : null}
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
