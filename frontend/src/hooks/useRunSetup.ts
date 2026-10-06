import { useCallback, useState } from 'react'
import { messages } from '../i18n'
import { containsPoint } from '../geo/footprint'
import type { LatLon, Resolution } from '../types/simulation'
import type { Engine } from './useSimulationRun'

export type TemporalScenario = 'seeded_pool' | 'gauge_driven'

/**
 * The run choices the map needs as well as the config panel: engine, scenario, grid, and the seed marker
 * placed by clicking the map. A marker belongs to one seeded-pool setup on one grid, so the setters below
 * clear it (and any "outside the grid" notice) when the grid changes or the setup leaves seeded pool.
 */
export function useRunSetup() {
  const [engine, setEngineState] = useState<Engine>('temporal')
  const [scenario, setScenarioState] = useState<TemporalScenario>('seeded_pool')
  const [resolution, setResolutionState] = useState<Resolution>(30)
  /** null: seed at the terrain's lowest point (the backend default). */
  const [seed, setSeed] = useState<LatLon | null>(null)
  const [seedNotice, setSeedNotice] = useState<string | null>(null)

  const clearSeed = useCallback(() => {
    setSeed(null)
    setSeedNotice(null)
  }, [])

  const setEngine = useCallback(
    (next: Engine) => {
      setEngineState(next)
      if (next !== 'temporal') clearSeed()
    },
    [clearSeed],
  )

  const setScenario = useCallback(
    (next: TemporalScenario) => {
      setScenarioState(next)
      if (next !== 'seeded_pool') clearSeed()
    },
    [clearSeed],
  )

  const setResolution = useCallback(
    (next: Resolution) => {
      if (next === resolution) return
      setResolutionState(next)
      clearSeed()
    },
    [resolution, clearSeed],
  )

  /**
   * A map click: inside the grid's footprint it places (or moves) the marker; outside, it's ignored with a
   * notice. The backend re-checks against the grid's real transform and rejects with a 422 either way.
   */
  const placeSeed = useCallback(
    (point: LatLon, footprint: readonly (readonly [number, number])[]) => {
      if (!containsPoint(footprint, point.lat, point.lon)) {
        setSeedNotice(messages().config.seedOutside(resolution))
        return
      }
      setSeed(point)
      setSeedNotice(null)
    },
    [resolution],
  )

  return {
    engine,
    scenario,
    resolution,
    seed,
    seedNotice,
    /** Whether the current setup is a seeded-pool run, the only kind a seed marker applies to. */
    seeding: engine === 'temporal' && scenario === 'seeded_pool',
    setEngine,
    setScenario,
    setResolution,
    placeSeed,
    clearSeed,
  }
}

export type RunSetup = ReturnType<typeof useRunSetup>
