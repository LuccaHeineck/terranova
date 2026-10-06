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
  VON_NEUMANN_MAX_OUTFLOW_FRACTION,
} from '../presets'
import { num, useI18n } from '../i18n'
import type { Messages } from '../i18n'
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

function gridOptions(t: Messages): SegmentOption<Resolution>[] {
  return [
    { value: 30, label: '30 m', caption: t.config.gridCaption[30] },
    { value: 60, label: '60 m', caption: t.config.gridCaption[60], captionTone: 'warn' },
    { value: 90, label: '90 m', caption: t.config.gridCaption[90] },
  ]
}

function scenarioOptions(t: Messages): SegmentOption<TemporalScenario>[] {
  return [
    { value: 'seeded_pool', label: t.config.seededPool, caption: t.config.seededPoolCaption },
    { value: 'gauge_driven', label: t.config.gauges, caption: t.config.gaugesCaption },
  ]
}

function neighborhoodOptions(t: Messages): SegmentOption<Neighborhood>[] {
  return [
    { value: 'moore', label: <><NeighborhoodGlyph kind="moore" />Moore</>, caption: t.config.mooreCaption },
    {
      value: 'von_neumann',
      label: <><NeighborhoodGlyph kind="von_neumann" />von Neumann</>,
      caption: t.config.vonNeumannCaption,
      captionTone: 'warn',
    },
  ]
}

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

interface SeedLocationFieldProps {
  seed: RunSetup['seed']
  resolution: Resolution
  error: string | null
  busy: boolean
  onClear: () => void
}

/** Where the pool goes: the marker placed on the map, or - with none - the terrain's lowest point. */
function SeedLocationField({ seed, resolution, error, busy, onClear }: SeedLocationFieldProps) {
  const { t, locale } = useI18n()
  // With decimal commas, a comma between the two coordinates would be ambiguous.
  const separator = locale === 'pt-BR' ? '; ' : ', '
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[13px] font-medium text-ink">{t.config.seedLocation}</span>
      {seed ? (
        <div className="flex items-center justify-between gap-2 rounded-md border border-line bg-surface py-1 pr-1 pl-2">
          <span className="flex items-center gap-2 text-xs text-ink tabular-nums">
            <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full bg-[#e11d48] ring-2 ring-white" />
            {num(seed.lat, 5)}
            {separator}
            {num(seed.lon, 5)}
          </span>
          <button
            type="button"
            onClick={onClear}
            disabled={busy}
            className="rounded px-2 py-0.5 text-xs text-ink-muted hover:bg-sunken hover:text-ink disabled:opacity-50"
          >
            {t.config.clear}
          </button>
        </div>
      ) : (
        <span className="rounded-md border border-dashed border-line px-2 py-1 text-xs text-ink-muted">
          {t.config.lowestPoint}
        </span>
      )}
      <span className="text-xs leading-snug text-ink-muted">
        {error ? t.config.seedOutlineError(error) : seed ? t.config.seedMoveHint : t.config.seedPickHint(resolution)}
      </span>
    </div>
  )
}

export function ConfigPanel({ status, setup, seedPlacementError, onStart, onReplay }: ConfigPanelProps) {
  const { engine, scenario, resolution, seed, setEngine, setScenario, setResolution } = setup
  const { t } = useI18n()
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

  const neighborhoodName = t.common.neighborhood(NEIGHBORHOOD_LABEL[neighborhood])
  const summary =
    engine === 'fast'
      ? t.config.summaryFast(resolution)
      : scenario === 'seeded_pool'
        ? t.config.summarySeeded(steps, resolution, neighborhoodName)
        : t.config.summaryGauges(stopAtPeak, resolution, neighborhoodName)

  return (
    <form id={RUN_SETUP_FORM_ID} onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
      <div className="relative flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-4 pt-1 pb-5">
        {busy && <Callout tone="info">{t.config.locked}</Callout>}

        {/* The one-click way in: the validated real event, both engines side by side. */}
        <div className="relative shrink-0 overflow-hidden rounded-xl bg-surface p-4 ring-1 ring-line">
          <WaveMotif />
          <span className="text-[11px] font-semibold tracking-wider text-accent uppercase">{t.config.replayKicker}</span>
          <h3 className="mt-0.5 font-serif text-[26px] leading-tight text-ink">{t.config.replayTitle}</h3>
          <p className="mt-1 text-xs leading-snug text-ink-muted">
            {t.config.replayText}
          </p>
          <button
            type="button"
            onClick={startReplay}
            disabled={busy}
            className="mt-3 w-full rounded-lg bg-ink px-3 py-2 text-[13px] font-semibold text-canvas transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {t.config.replayButton}
          </button>
        </div>

        <div aria-hidden="true" className="-my-2 flex items-center gap-3 text-[11px] text-ink-muted">
          <span className="h-px flex-1 bg-line" />
          {t.config.orConfigure}
          <span className="h-px flex-1 bg-line" />
        </div>

        <Section title={t.config.engine}>
          <div role="radiogroup" aria-label={t.config.engine} className="grid grid-cols-2 gap-2">
            <OptionCard
              name="engine"
              checked={engine === 'temporal'}
              disabled={busy}
              onSelect={() => setEngine('temporal')}
              title={t.common.temporalCa}
              description={t.config.temporalDescription}
            />
            <OptionCard
              name="engine"
              checked={engine === 'fast'}
              disabled={busy}
              onSelect={() => setEngine('fast')}
              title={t.common.fast}
              description={t.config.fastDescription}
            />
          </div>
        </Section>

        <Section title={t.config.grid}>
          <Segmented name="resolution" label={t.config.grid} value={resolution} options={gridOptions(t)} onChange={setResolution} disabled={busy} />
        </Section>

        {engine === 'fast' ? (
          <p className="text-xs leading-snug text-ink-muted">
            {t.config.fastNote}
          </p>
        ) : (
          <>
            <Section title={t.config.scenario}>
              <Segmented
                name="scenario"
                label={t.config.scenario}
                value={scenario}
                options={scenarioOptions(t)}
                onChange={selectScenario}
                disabled={busy}
              />

              {scenario === 'seeded_pool' ? (
                <div className="mt-1 flex flex-col gap-4">
                  <NumberField label={t.config.steps} value={steps} onChange={setSteps} min={1} stepBy={50} disabled={busy} />

                  <SliderField
                    label={t.config.seedVolume}
                    value={seedVolume}
                    onChange={setSeedVolume}
                    min={1}
                    max={MAX_SEED_VOLUME}
                    scale="log"
                    quantum={1}
                    inputStep="any"
                    marks={[{ value: DEFAULT_SEED_VOLUME, label: t.common.default }]}
                    disabled={busy}
                    describedBy="seed-volume-hint"
                  >
                    <div id="seed-volume-hint" className="flex flex-col gap-0.5 text-xs leading-snug text-ink-muted">
                      <span>{t.config.seedVolumeHint}</span>
                      <span className="text-ink tabular-nums">
                        {t.config.seedVolumeEquivalent(seedVolume / SEED_PATCH_CELLS, seedVolume * resolution * resolution, resolution)}
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
                    {t.config.stopAtPeak}
                  </Toggle>
                </div>
              )}
            </Section>

            <Section
              title={t.config.tuning}
              collapsible
              aside={
                tuningChanged && (
                  <span className="ml-auto flex items-center gap-1.5 text-xs text-accent">
                    <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-accent" />
                    {t.config.changed}
                  </span>
                )
              }
            >
              <div className="flex flex-col gap-1.5">
                <span className="text-[13px] font-medium text-ink">{t.config.neighborhood}</span>
                <Segmented
                  name="neighborhood"
                  label={t.config.neighborhood}
                  value={neighborhood}
                  options={neighborhoodOptions(t)}
                  onChange={(next) => (next === 'von_neumann' ? selectVonNeumann() : setNeighborhood('moore'))}
                  disabled={busy}
                />
                {neighborhood === 'moore' ? (
                  <span className="text-xs leading-snug text-ink-muted">{t.config.validatedNeighborhoodNote}</span>
                ) : (
                  <Callout tone="warn">{t.config.validatedNeighborhoodNote}</Callout>
                )}
              </div>

              <NumberField
                label={t.config.frameInterval}
                value={frameInterval}
                onChange={setFrameInterval}
                min={1}
                stepBy={scenario === 'gauge_driven' ? 100 : 1}
                unit={t.config.stepsUnit}
                disabled={busy}
              />

              <SliderField
                label={t.config.outflowFraction}
                value={outflowFraction}
                onChange={setOutflowFraction}
                min={0.01}
                max={maxOutflowFraction}
                scale="log"
                quantum={0.005}
                inputStep={0.005}
                marks={[{ value: DEFAULT_OUTFLOW_FRACTION, label: t.common.default }]}
                disabled={busy}
                describedBy={neighborhood === 'von_neumann' ? 'outflow-fraction-hint' : undefined}
              >
                {neighborhood === 'von_neumann' && (
                  <span id="outflow-fraction-hint" className="text-xs leading-snug text-ink-muted">
                    {t.config.vonNeumannOutflowHint(VON_NEUMANN_MAX_OUTFLOW_FRACTION)}
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
