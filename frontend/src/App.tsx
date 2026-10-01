import { useState } from 'react'
import type { SimulationParams } from './types/simulation'
import { useSimulationRun } from './hooks/useSimulationRun'
import { useTimeline } from './hooks/useTimeline'
import { useGrids } from './hooks/useGrids'
import { useRunSetup } from './hooks/useRunSetup'
import { ConfigPanel } from './components/ConfigPanel'
import { FloodMap } from './components/FloodMap'
import { LogPanel } from './components/LogPanel'
import { ResultsPanel } from './components/ResultsPanel'
import { Sidebar } from './components/Sidebar'
import type { SidebarTab } from './components/Sidebar'
import { TopBar } from './components/TopBar'

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
  const shownLayer = run.layers[run.activeEngine] ?? run.layers.temporal ?? run.layers.fast

  const [tab, setTab] = useState<SidebarTab>('setup')
  const [panelOpen, setPanelOpen] = useState(true)
  // A run's results are what to look at next: show them, and on a narrow screen get the drawer off the map.
  const showResults = () => {
    setTab('results')
    setPanelOpen(false)
  }
  const start = (params: SimulationParams) => {
    showResults()
    run.start(params)
  }
  const startReplay = () => {
    showResults()
    run.startReplay()
  }

  return (
    <div className="grid h-screen grid-rows-[52px_minmax(0,1fr)] overflow-hidden bg-basalt text-mist">
      <TopBar
        status={run.status}
        gridShape={run.gridShape}
        resolution={shownLayer?.resolution ?? null}
        onStop={run.stop}
      />
      <div className="relative flex min-h-0">
        <Sidebar
          tab={tab}
          onTab={setTab}
          open={panelOpen}
          onOpenChange={setPanelOpen}
          badges={{ results: run.error ? 'error' : busy ? 'live' : null }}
          panels={{
            setup: (
              <ConfigPanel
                status={run.status}
                setup={setup}
                seedPlacementError={gridsError}
                onStart={start}
                onReplay={startReplay}
              />
            ),
            results: (
              <ResultsPanel
                status={run.status}
                gridShape={run.gridShape}
                bounds={run.bounds}
                layers={run.layers}
                temporalFrame={timeline.frame}
                followingLatest={timeline.following}
                error={run.error}
                onGoToSetup={() => setTab('setup')}
              />
            ),
            log: <LogPanel log={run.log} />,
          }}
        />
        <main className="min-w-0 flex-1">
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
        </main>
      </div>
    </div>
  )
}
