import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Resolution, SimulationParams } from '../types/simulation'
import type { Engine, SimulationStatus } from '../hooks/useSimulationRun'
import { DEFAULT_OUTFLOW_FRACTION, GAUGE_DRIVEN_FRAME_INTERVAL, MAY_2024_REPLAY } from '../presets'

interface ConfigPanelProps {
  status: SimulationStatus
  onStart: (params: SimulationParams) => void
  /** Runs the May 2024 replay preset (fast, then temporal to the peak, in Compare). */
  onReplay: () => void
  onStop: () => void
}

type TemporalScenario = 'seeded_pool' | 'gauge_driven'

// A seeded-pool run is a few hundred steps, so a frame every 5 is fine. A
// gauge-driven run covers the whole real May 2024 event in 100k+ engine steps -
// at an interval of 5 that would be tens of thousands of WebSocket frames, so it
// defaults far coarser. Switching modes resets the field to that mode's default;
// the user can still type any value afterwards.
const DEFAULT_FRAME_INTERVAL: Record<TemporalScenario, number> = {
  seeded_pool: 5,
  gauge_driven: GAUGE_DRIVEN_FRAME_INTERVAL,
}

const inputClass = 'rounded border border-gray-300 px-2 py-1 disabled:opacity-50'

export function ConfigPanel({ status, onStart, onReplay, onStop }: ConfigPanelProps) {
  const [engine, setEngine] = useState<Engine>('temporal')
  const [scenario, setScenario] = useState<TemporalScenario>('seeded_pool')
  const [resolution, setResolution] = useState<Resolution>(30)
  const [steps, setSteps] = useState(200)
  const [frameInterval, setFrameInterval] = useState(DEFAULT_FRAME_INTERVAL.seeded_pool)
  const [outflowFraction, setOutflowFraction] = useState(DEFAULT_OUTFLOW_FRACTION)
  // On by default: the observed peak is the moment the fast mode models and the
  // real flood extent was mapped at. Off runs the whole ~14-day record.
  const [stopAtPeak, setStopAtPeak] = useState(true)

  const busy = status === 'starting' || status === 'streaming'

  const selectScenario = (next: TemporalScenario) => {
    setScenario(next)
    setFrameInterval(DEFAULT_FRAME_INTERVAL[next])
  }

  // The form is set to the replay's temporal run, so afterwards it shows what actually ran and a plain
  // Start re-runs that same temporal run.
  const startReplay = () => {
    const preset = MAY_2024_REPLAY.temporal
    setEngine('temporal')
    setScenario(preset.mode)
    setResolution(preset.resolution)
    setStopAtPeak(preset.stop_at_peak)
    setFrameInterval(preset.frame_interval)
    setOutflowFraction(preset.outflow_fraction)
    onReplay()
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (engine === 'fast') {
      onStart({ mode: 'fast', resolution })
      return
    }
    onStart({
      mode: scenario,
      resolution,
      frame_interval: frameInterval,
      outflow_fraction: outflowFraction,
      ...(scenario === 'seeded_pool' ? { steps } : { stop_at_peak: stopAtPeak }),
    })
  }

  return (
    <form onSubmit={handleSubmit} className="flex h-full flex-col gap-4 overflow-y-auto border-r border-gray-200 bg-gray-50 p-4">
      <h1 className="text-lg font-semibold text-gray-900">Terranova</h1>
      <p className="text-sm text-gray-500">Vale do Taquari flood simulation</p>

      <div className="flex flex-col gap-1.5 rounded-md border border-blue-200 bg-white p-3">
        <button
          type="button"
          onClick={startReplay}
          disabled={busy}
          className="rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Replay May 2024 flood
        </button>
        <p className="text-xs text-gray-600">
          Validated scenario: 90 m grid, the fast engine and the temporal CA to the observed peak, side by side.
        </p>
      </div>

      <fieldset className="flex flex-col gap-1 text-sm text-gray-700">
        <legend className="mb-1 font-medium">Engine</legend>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="engine"
            checked={engine === 'temporal'}
            disabled={busy}
            onChange={() => setEngine('temporal')}
          />
          Temporal CA (time-stepped)
        </label>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="engine"
            checked={engine === 'fast'}
            disabled={busy}
            onChange={() => setEngine('fast')}
          />
          Fast (non-temporal)
        </label>
      </fieldset>

      <label className="flex flex-col gap-1 text-sm text-gray-700">
        Grid
        <select
          value={resolution}
          disabled={busy}
          onChange={(e) => setResolution(Number(e.target.value) as Resolution)}
          className={inputClass}
        >
          <option value={30}>30 m (live grid)</option>
          <option value={90}>90 m (validation grid)</option>
        </select>
      </label>

      {engine === 'fast' ? (
        <p className="text-sm text-gray-600">
          Real May 2024 event: one steady classification at the observed peak discharge. No time steps, so there is
          no frame interval or outflow fraction.
        </p>
      ) : (
        <>
          <fieldset className="flex flex-col gap-1 text-sm text-gray-700">
            <legend className="mb-1 font-medium">Scenario</legend>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="scenario"
                checked={scenario === 'seeded_pool'}
                disabled={busy}
                onChange={() => selectScenario('seeded_pool')}
              />
              Synthetic seeded pool
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="scenario"
                checked={scenario === 'gauge_driven'}
                disabled={busy}
                onChange={() => selectScenario('gauge_driven')}
              />
              Real May 2024 event (gauge-driven)
            </label>
          </fieldset>

          {scenario === 'seeded_pool' ? (
            <label className="flex flex-col gap-1 text-sm text-gray-700">
              Steps
              <input
                type="number"
                min={1}
                value={steps}
                disabled={busy}
                onChange={(e) => setSteps(Number(e.target.value))}
                className={inputClass}
              />
            </label>
          ) : (
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={stopAtPeak}
                disabled={busy}
                onChange={(e) => setStopAtPeak(e.target.checked)}
              />
              Stop at the observed peak
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
              className={inputClass}
            />
          </label>

          <label className="flex flex-col gap-1 text-sm text-gray-700">
            Outflow fraction
            <input
              type="number"
              min={0.01}
              max={1}
              step={0.005}
              value={outflowFraction}
              disabled={busy}
              onChange={(e) => setOutflowFraction(Number(e.target.value))}
              className={inputClass}
            />
          </label>
        </>
      )}

      {/* Distinct keys: if React reused one <button> and flipped its type from "button" to "submit"
          during the Stop click, the click's default action would submit the form and start a new run. */}
      {busy ? (
        <button
          key="stop"
          type="button"
          onClick={onStop}
          className="mt-2 rounded bg-gray-700 px-3 py-2 text-sm font-medium text-white hover:bg-gray-800"
        >
          Stop
        </button>
      ) : (
        <button
          key="start"
          type="submit"
          className="mt-2 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Start simulation
        </button>
      )}
    </form>
  )
}
