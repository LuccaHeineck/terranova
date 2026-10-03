import { useState } from 'react'
import type { FormEvent } from 'react'
import { NEIGHBORHOOD_LABEL } from '../types/simulation'
import type { Neighborhood, Resolution, SimulationParams } from '../types/simulation'
import type { SimulationStatus } from '../hooks/useSimulationRun'
import type { RunSetup, TemporalScenario } from '../hooks/useRunSetup'
import {
  DEFAULT_OUTFLOW_FRACTION,
  DEFAULT_SEED_VOLUME,
  GAUGE_DRIVEN_FRAME_INTERVAL,
  MAX_SEED_VOLUME,
  MAY_2024_REPLAY,
  VALIDATED_NEIGHBORHOOD_NOTE,
  VON_NEUMANN_MAX_OUTFLOW_FRACTION,
} from '../presets'
import { Callout } from './ui/Callout'
import { NeighborhoodGlyph } from './ui/icons'
import { NumberField } from './ui/NumberField'
import { OptionCard } from './ui/OptionCard'
import { Section } from './ui/Section'
import { Segmented } from './ui/Segmented'
import type { SegmentOption } from './ui/Segmented'
import { SliderField } from './ui/SliderField'
import { Toggle } from './ui/Toggle'

/** The setup form's id: the top bar's Start button submits it from outside the sidebar. */
export const RUN_SETUP_FORM_ID = 'run-setup'

interface ConfigPanelProps {
  status: SimulationStatus
  /** Engine, scenario, grid and seed marker - shared with the map, which places the marker. */
  setup: RunSetup
  /** Why the map can't take a seed location right now (the grid outlines didn't load), if so. */
  seedPlacementError: string | null
  onStart: (params: SimulationParams) => void
  /** Runs the May 2024 replay preset (fast, then temporal to the peak, in Compare). */
  onReplay: () => void
}

// A seeded-pool run is a few hundred steps, so a frame every 5 is fine. A
// gauge-driven run covers the whole real May 2024 event in 100k+ engine steps -
// at an interval of 5 that would be tens of thousands of WebSocket frames, so it
// defaults far coarser. Switching modes resets the field to that mode's default;
// the user can still type any value afterwards.
const DEFAULT_FRAME_INTERVAL: Record<TemporalScenario, number> = {
  seeded_pool: 5,
  gauge_driven: GAUGE_DRIVEN_FRAME_INTERVAL,
}

/** The seed pool is a 5x5 patch (simulation/engine.py), before clipping at a grid edge. */
const SEED_PATCH_CELLS = 25

const GRID_OPTIONS: readonly SegmentOption<Resolution>[] = [
  { value: 30, label: '30 m', caption: 'Live' },
  { value: 60, label: '60 m', caption: 'Unvalidated', captionTone: 'warn' },
  { value: 90, label: '90 m', caption: 'Validation' },
]

const SCENARIO_OPTIONS: readonly SegmentOption<TemporalScenario>[] = [
  { value: 'seeded_pool', label: 'Seeded pool', caption: 'Synthetic' },
  { value: 'gauge_driven', label: 'May 2024 gauges', caption: 'Real event' },
]

const NEIGHBORHOOD_OPTIONS: readonly SegmentOption<Neighborhood>[] = [
  { value: 'moore', label: <><NeighborhoodGlyph kind="moore" />Moore</>, caption: '8 neighbors, validated' },
  {
    value: 'von_neumann',
    label: <><NeighborhoodGlyph kind="von_neumann" />von Neumann</>,
    caption: '4 neighbors, not validated',
    captionTone: 'warn',
  },
]

/** Two faint river lines in the replay card's corner: decoration only. */
function WaveMotif() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 120 60"
      className="pointer-events-none absolute -top-1 -right-2 h-16 w-32 text-accent opacity-25"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
    >
      <path d="M2 20c12-8 22-8 34 0s22 8 34 0 22-8 34 0 14 6 14 6" />
      <path d="M2 34c12-8 22-8 34 0s22 8 34 0 22-8 34 0 14 6 14 6" opacity="0.6" />
      <path d="M2 48c12-8 22-8 34 0s22 8 34 0 22-8 34 0 14 6 14 6" opacity="0.3" />
    </svg>
  )
}

function formatNumber(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: 1 })
}

interface SeedLocationFieldProps {
  seed: RunSetup['seed']
  resolution: Resolution
  error: string | null
  busy: boolean
  onClear: () => void
}

/** Where the pool goes: the marker placed on the map, or - with none - the terrain's lowest point. */
function SeedLocationField({ seed, resolution, error, busy, onClear }: SeedLocationFieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[13px] font-medium text-ink">Seed location</span>
      {seed ? (
        <div className="flex items-center justify-between gap-2 rounded-md border border-line bg-surface py-1 pr-1 pl-2">
          <span className="flex items-center gap-2 text-xs text-ink tabular-nums">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-[#e11d48] ring-2 ring-white" />
            {seed.lat.toFixed(5)}, {seed.lon.toFixed(5)}
          </span>
          <button
            type="button"
            onClick={onClear}
            disabled={busy}
            className="rounded px-2 py-0.5 text-xs text-ink-muted hover:bg-sunken hover:text-ink disabled:opacity-50"
          >
            Clear
          </button>
        </div>
      ) : (
        <span className="rounded-md border border-dashed border-line px-2 py-1 text-xs text-ink-muted">
          Lowest point of the terrain (default)
        </span>
      )}
      <span className="text-xs leading-snug text-ink-muted">
        {error
          ? `Can't place a seed on the map yet: the grid outline didn't load (${error}). Retrying…`
          : seed
            ? 'Click the map again to move it; Clear goes back to the lowest point.'
            : `Click the map inside the dashed ${resolution} m grid outline to choose a spot instead.`}
      </span>
    </div>
  )
}

export function ConfigPanel({ status, setup, seedPlacementError, onStart, onReplay }: ConfigPanelProps) {
  const { engine, scenario, resolution, seed, setEngine, setScenario, setResolution } = setup
  const [steps, setSteps] = useState(200)
  const [seedVolume, setSeedVolume] = useState(DEFAULT_SEED_VOLUME)
  const [frameInterval, setFrameInterval] = useState(DEFAULT_FRAME_INTERVAL.seeded_pool)
  const [outflowFraction, setOutflowFraction] = useState(DEFAULT_OUTFLOW_FRACTION)
  // On by default: the observed peak is the moment the fast mode models and the
  // real flood extent was mapped at. Off runs the whole ~14-day record.
  const [stopAtPeak, setStopAtPeak] = useState(true)
  const [neighborhood, setNeighborhood] = useState<Neighborhood>('moore')

  const busy = status === 'starting' || status === 'streaming'

  // von Neumann is only converged up to VON_NEUMANN_MAX_OUTFLOW_FRACTION (the backend rejects more), so
  // switching to it brings a larger outflow fraction down to that bound.
  const selectVonNeumann = () => {
    setNeighborhood('von_neumann')
    setOutflowFraction((f) => Math.min(f, VON_NEUMANN_MAX_OUTFLOW_FRACTION))
  }
  const maxOutflowFraction = neighborhood === 'von_neumann' ? VON_NEUMANN_MAX_OUTFLOW_FRACTION : 1

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
    setNeighborhood(preset.neighborhood)
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
      neighborhood,
      ...(scenario === 'seeded_pool'
        ? { steps, seed_volume: seedVolume, ...(seed ? { seed_location: seed } : {}) }
        : { stop_at_peak: stopAtPeak }),
    })
  }

  // Tuning is collapsed by default, so say when it holds something other than the defaults.
  const tuningChanged =
    neighborhood !== 'moore' ||
    outflowFraction !== DEFAULT_OUTFLOW_FRACTION ||
    frameInterval !== DEFAULT_FRAME_INTERVAL[scenario]

  const neighborhoodName = `${NEIGHBORHOOD_LABEL[neighborhood]} neighborhood`
  const summary =
    engine === 'fast'
      ? `Runs the fast engine at the observed May 2024 peak on the ${resolution} m grid.`
      : scenario === 'seeded_pool'
        ? `Runs a ${steps.toLocaleString('en-US')}-step seeded pool on the ${resolution} m grid, ${neighborhoodName}.`
        : `Runs the May 2024 gauge record ${stopAtPeak ? 'up to the observed peak' : 'in full (about 14 days)'} on the ${resolution} m grid, ${neighborhoodName}.`

  return (
    <form id={RUN_SETUP_FORM_ID} onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
      <div className="relative flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-4 pt-1 pb-5">
        {busy && <Callout tone="info">Settings are locked while a run is going. Stop it to change them.</Callout>}

        {/* The one-click way in: the validated real event, both engines side by side. */}
        <div className="relative shrink-0 overflow-hidden rounded-xl bg-surface p-4 ring-1 ring-line">
          <WaveMotif />
          <span className="text-[11px] font-semibold tracking-wider text-accent uppercase">Validated scenario</span>
          <h3 className="mt-0.5 font-serif text-[26px] leading-tight text-ink">May 2024 flood</h3>
          <p className="mt-1 text-xs leading-snug text-ink-muted">
            The 90 m grid, fast engine and temporal CA to the observed peak, side by side.
          </p>
          <button
            type="button"
            onClick={startReplay}
            disabled={busy}
            className="mt-3 w-full rounded-lg bg-ink px-3 py-2 text-[13px] font-semibold text-canvas transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Replay the May 2024 flood
          </button>
        </div>

        <div aria-hidden="true" className="-my-2 flex items-center gap-3 text-[11px] text-ink-muted">
          <span className="h-px flex-1 bg-line" />
          or configure a run
          <span className="h-px flex-1 bg-line" />
        </div>

        <Section title="Engine">
          <div role="radiogroup" aria-label="Engine" className="grid grid-cols-2 gap-2">
            <OptionCard
              name="engine"
              checked={engine === 'temporal'}
              disabled={busy}
              onSelect={() => setEngine('temporal')}
              title="Temporal CA"
              description="Time-stepped flow, streams frames"
            />
            <OptionCard
              name="engine"
              checked={engine === 'fast'}
              disabled={busy}
              onSelect={() => setEngine('fast')}
              title="Fast"
              description="Steady extent at the observed peak"
            />
          </div>
        </Section>

        <Section title="Grid">
          <Segmented name="resolution" label="Grid" value={resolution} options={GRID_OPTIONS} onChange={setResolution} disabled={busy} />
        </Section>

        {engine === 'fast' ? (
          <p className="text-xs leading-snug text-ink-muted">
            Real May 2024 event: one steady classification at the observed peak discharge. No time steps, so there is
            no frame interval or outflow fraction.
          </p>
        ) : (
          <>
            <Section title="Scenario">
              <Segmented
                name="scenario"
                label="Scenario"
                value={scenario}
                options={SCENARIO_OPTIONS}
                onChange={selectScenario}
                disabled={busy}
              />

              {scenario === 'seeded_pool' ? (
                <div className="mt-1 flex flex-col gap-4">
                  <NumberField label="Steps" value={steps} onChange={setSteps} min={1} stepBy={50} disabled={busy} />

                  <SliderField
                    label="Seed volume"
                    value={seedVolume}
                    onChange={setSeedVolume}
                    min={1}
                    max={MAX_SEED_VOLUME}
                    scale="log"
                    quantum={1}
                    inputStep="any"
                    marks={[{ value: DEFAULT_SEED_VOLUME, label: 'default' }]}
                    disabled={busy}
                    describedBy="seed-volume-hint"
                  >
                    <div id="seed-volume-hint" className="flex flex-col gap-0.5 text-xs leading-snug text-ink-muted">
                      <span>Summed cell depth (m), as the log's volume.</span>
                      <span className="text-ink tabular-nums">
                        {formatNumber(seedVolume / SEED_PATCH_CELLS)} m deep over the 5×5 seed patch, ≈{' '}
                        {formatNumber(seedVolume * resolution * resolution)} m³ on the {resolution} m grid.
                      </span>
                    </div>
                  </SliderField>

                  <SeedLocationField
                    seed={seed}
                    resolution={resolution}
                    error={seedPlacementError}
                    busy={busy}
                    onClear={setup.clearSeed}
                  />
                </div>
              ) : (
                <div className="mt-1">
                  <Toggle checked={stopAtPeak} onChange={setStopAtPeak} disabled={busy}>
                    Stop at the observed peak
                  </Toggle>
                </div>
              )}
            </Section>

            <Section
              title="Engine tuning"
              collapsible
              aside={
                tuningChanged && (
                  <span className="ml-auto flex items-center gap-1.5 text-xs text-accent">
                    <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-accent" />
                    Changed
                  </span>
                )
              }
            >
              <div className="flex flex-col gap-1.5">
                <span className="text-[13px] font-medium text-ink">Neighborhood</span>
                <Segmented
                  name="neighborhood"
                  label="Neighborhood"
                  value={neighborhood}
                  options={NEIGHBORHOOD_OPTIONS}
                  onChange={(next) => (next === 'von_neumann' ? selectVonNeumann() : setNeighborhood('moore'))}
                  disabled={busy}
                />
                {neighborhood === 'moore' ? (
                  <span className="text-xs leading-snug text-ink-muted">{VALIDATED_NEIGHBORHOOD_NOTE}</span>
                ) : (
                  <Callout tone="warn">{VALIDATED_NEIGHBORHOOD_NOTE}</Callout>
                )}
              </div>

              <NumberField
                label="Frame interval"
                value={frameInterval}
                onChange={setFrameInterval}
                min={1}
                stepBy={scenario === 'gauge_driven' ? 100 : 1}
                unit="steps"
                disabled={busy}
              />

              <SliderField
                label="Outflow fraction"
                value={outflowFraction}
                onChange={setOutflowFraction}
                min={0.01}
                max={maxOutflowFraction}
                scale="log"
                quantum={0.005}
                inputStep={0.005}
                marks={[{ value: DEFAULT_OUTFLOW_FRACTION, label: 'default' }]}
                disabled={busy}
                describedBy={neighborhood === 'von_neumann' ? 'outflow-fraction-hint' : undefined}
              >
                {neighborhood === 'von_neumann' && (
                  <span id="outflow-fraction-hint" className="text-xs leading-snug text-ink-muted">
                    At most {VON_NEUMANN_MAX_OUTFLOW_FRACTION} with von Neumann: above that its result depends on the
                    engine's substep size.
                  </span>
                )}
              </SliderField>
            </Section>
          </>
        )}
      </div>

      <p className="mx-3 mb-1 rounded-lg bg-sunken px-3 py-2.5 text-xs leading-snug text-ink-muted">{summary}</p>
    </form>
  )
}
