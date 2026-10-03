import { useRef } from 'react'
import type { ReactNode } from 'react'
import { NeighborhoodGlyph } from './ui/icons'

/**
 * Documented results quoted on the page (docs/project-plan.md, docs/tcc-deviations.md sections 16, 21 and 23).
 * They describe the validated May 2024 run on the 90 m grid with the Moore neighborhood, not whatever is on the
 * map; update them by hand if those results are ever re-run.
 */
const DOCUMENTED = {
  peakStageM: 33.66,
  temporalCsi: 0.9,
  fastCsi: 0.896,
  fastSeconds: '≈ 70 ms',
  temporalMinutes: '≈ 8–24 min',
} as const

const SECTIONS = [
  { id: 'about-problem', label: 'The problem' },
  { id: 'about-model', label: 'The model' },
  { id: 'about-engines', label: 'Two engines' },
  { id: 'about-data', label: 'Data' },
  { id: 'about-usage', label: 'How to use it' },
  { id: 'about-limits', label: 'Limits' },
] as const

type SectionId = (typeof SECTIONS)[number]['id']

/** A UI control's name as the app labels it, so the instructions read like the screen. */
function Ui({ children }: { children: ReactNode }) {
  return (
    <span className="rounded bg-surface px-1.5 py-px font-medium whitespace-nowrap text-ink">{children}</span>
  )
}

function Formula({ children }: { children: ReactNode }) {
  return <code className="rounded bg-sunken px-1.5 py-px font-mono whitespace-nowrap text-[12.5px] text-accent">{children}</code>
}

function AboutSection({ id, title, children }: { id: SectionId; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-6 border-t border-line pt-8">
      <h2 id={`${id}-title`} className="mb-4 font-serif text-[34px] leading-tight text-ink">
        {title}
      </h2>
      <div className="flex flex-col gap-4 text-[15px] leading-relaxed text-ink/85">{children}</div>
    </section>
  )
}

function RuleStep({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <li className="flex flex-col gap-1.5 rounded-xl border border-line bg-surface p-4">
      <span className="font-display text-xs font-semibold tracking-wide text-accent uppercase">Step {n}</span>
      <span className="font-display text-base font-semibold text-ink">{title}</span>
      <div className="text-sm leading-relaxed text-ink/80">{children}</div>
    </li>
  )
}

interface EngineCardProps {
  name: string
  tagline: string
  stats: { label: string; value: string }[]
  children: ReactNode
}

function EngineCard({ name, tagline, stats, children }: EngineCardProps) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-5">
      <div>
        <h3 className="font-display text-lg font-semibold text-ink">{name}</h3>
        <p className="text-sm text-ink-muted">{tagline}</p>
      </div>
      <div className="text-sm leading-relaxed text-ink/80">{children}</div>
      <dl className="mt-auto grid grid-cols-2 gap-3 border-t border-line pt-3">
        {stats.map(({ label, value }) => (
          <div key={label}>
            <dt className="text-xs text-ink-muted">{label}</dt>
            <dd className="font-serif text-3xl leading-tight text-ink tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

const DATA_ROWS: { what: string; source: string; use: string }[] = [
  {
    what: 'Terrain',
    source: 'SRTM 1 arc-second DEM (via OpenTopography), reprojected to SIRGAS 2000 / UTM 22S and sink-filled',
    use: 'Elevation Z of every cell',
  },
  {
    what: 'Land cover',
    source: 'MapBiomas Collection 10, 2024 map',
    use: "Each class looked up to a Manning's n: how much it slows the water",
  },
  {
    what: 'River',
    source: 'ANA/SGB gauge 86879300, Porto Fluvial de Estrela, 27 April – 10 May 2024',
    use: 'Discharge entering the grid over the real event',
  },
  {
    what: 'Observed flood',
    source: 'SGB/CPRM flood-extent map for Lajeado at the 33.67 m stage',
    use: 'Ground truth the runs are scored against (CSI)',
  },
]

interface AboutPageProps {
  /** Back to the map. */
  onClose: () => void
}

/** The project's introduction and user guide, shown in place of the map from the rail's About item. */
export function AboutPage({ onClose }: AboutPageProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  // Scroll the page's own container rather than following a #hash link, which would change the app's URL.
  const goTo = (id: SectionId) =>
    scrollRef.current?.querySelector(`#${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto bg-canvas">
      <article className="mx-auto flex max-w-[860px] flex-col gap-10 px-4 py-10 sm:px-8 sm:py-14">
        <header className="flex flex-col gap-5">
          <span className="font-display text-xs font-semibold tracking-[0.18em] text-accent uppercase">About</span>
          <h1 className="font-serif text-5xl leading-[1.05] text-ink sm:text-6xl">
            Flood simulation for the Vale do Taquari, one cell at a time
          </h1>
          <p className="max-w-[68ch] text-lg leading-relaxed text-ink/85">
            Terranova simulates how the Taquari river spreads over the land between Lajeado and Estrela. It uses a{' '}
            <strong className="font-semibold text-ink">macroscopic cellular automaton</strong>: the valley becomes a
            grid of cells, and each cell passes water to its neighbors by a simple local rule. The aim is a flood map
            fast enough to rerun many times, accurate enough to trust, built only from public data.
          </p>
          <p className="text-sm text-ink-muted">
            Undergraduate thesis (TCC), Software Engineering, Univates · Lucca Coutinho Heineck · Advisor: Prof. Me.
            Edson Moacir Ahlert
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-canvas transition-colors hover:bg-accent-strong"
            >
              Open the simulator
            </button>
            <button
              type="button"
              onClick={() => goTo('about-usage')}
              className="rounded-lg border border-ink-muted px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-ink hover:bg-surface"
            >
              How to use it
            </button>
          </div>
          <nav aria-label="On this page" className="flex flex-wrap gap-x-4 gap-y-1.5 pt-2 text-sm">
            {SECTIONS.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => goTo(id)}
                className="text-ink-muted underline-offset-4 hover:text-ink hover:underline"
              >
                {label}
              </button>
            ))}
          </nav>
        </header>

        <AboutSection id="about-problem" title="The problem">
          <p>
            In September 2023 and again in May 2024 the Vale do Taquari flooded beyond the 1941 record. In May 2024
            the river at Lajeado and Estrela rose from 13.00 m to {DOCUMENTED.peakStageM.toFixed(2)} m in 72 hours.
          </p>
          <p>
            Hydrodynamic models that solve the full shallow water equations (HEC-RAS 2D, for example) are accurate,
            but slow and costly to run. In an emergency you want to ask &ldquo;what if the river reaches this
            level?&rdquo; many times, quickly. This project asks whether a cellular automaton, run on public
            terrain, land-cover and gauge data, can draw a usable flood extent in a fraction of that time.
          </p>
        </AboutSection>

        <AboutSection id="about-model" title="The model">
          <p>
            Every cell stores two numbers: the terrain elevation <Formula>Z</Formula>, which never changes, and the
            water depth <Formula>H</Formula>, which does. At every step all cells apply the same rule at once:
          </p>
          <ol className="grid gap-3 sm:grid-cols-3">
            <RuleStep n={1} title="Find the water surface">
              <Formula>WSE = Z + H</Formula>. Water only flows downhill on that surface, from a higher water level to
              a lower one.
            </RuleStep>
            <RuleStep n={2} title="Split the outflow">
              <span className="mb-1.5 flex items-center gap-2 text-ink">
                <NeighborhoodGlyph kind="moore" /> 8 neighbors (Moore)
              </span>
              Lower neighbors get a share weighted by Manning&rsquo;s equation, <Formula>√S / n</Formula>: steeper and
              smoother wins. Diagonals count their longer distance.
            </RuleStep>
            <RuleStep n={3} title="Move the water">
              The volume leaving a cell is added to its neighbors. Nothing is created or lost: total volume changes only
              by what the river brings in and what leaves at the outlet.
            </RuleStep>
          </ol>
          <p>
            That last property, mass conservation, is the model&rsquo;s main correctness check. During a May 2024 run
            the timeline shows it live as the <em>balance</em>: volume minus net inflow, which stays at rounding-error
            level.
          </p>
        </AboutSection>

        <AboutSection id="about-engines" title="Two engines">
          <p>
            The app runs the same terrain and roughness through two engines that answer different questions. Both
            are scored against the observed May 2024 flood extent on the 90 m grid.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <EngineCard
              name="Temporal CA"
              tagline="How does the flood unfold?"
              stats={[
                { label: 'CSI at the peak', value: DOCUMENTED.temporalCsi.toFixed(2) },
                { label: 'Run time, 90 m', value: DOCUMENTED.temporalMinutes },
              ]}
            >
              The time-stepped cellular automaton above. Each step covers a real span of time derived from the Manning
              flow, so the run follows the actual May 2024 hydrograph hour by hour and streams frames to the map as
              it goes.
            </EngineCard>
            <EngineCard
              name="Fast mode"
              tagline="How far does the water reach at the peak?"
              stats={[
                { label: 'CSI at the peak', value: DOCUMENTED.fastCsi.toFixed(3) },
                { label: 'Run time, 90 m', value: DOCUMENTED.fastSeconds },
              ]}
            >
              One steady extent at the observed peak discharge, with no time steps: the flow is routed once through
              the terrain from high to low, then spread across the floodplain with a rating curve built from height
              above the river. Inspired by Torres et al. (2022).
            </EngineCard>
          </div>
          <p>
            CSI, the Critical Success Index, counts the cells both the run and the observation call flooded, divided
            by every cell that either one calls flooded: 1 is a perfect match, and both missed cells and false alarms
            pull it down.
          </p>
        </AboutSection>

        <AboutSection id="about-data" title="Data">
          <p>
            Everything comes from public sources and is preprocessed offline, so a run reads only local files. The
            study area is a box about 6 km across, over the river between Lajeado and Estrela, at 30, 60 or 90 m per
            cell.
          </p>
          <div className="overflow-hidden rounded-md border border-line">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface text-xs text-ink-muted">
                <tr>
                  <th scope="col" className="px-4 py-2.5 font-medium">Input</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">Source</th>
                  <th scope="col" className="hidden px-4 py-2.5 font-medium sm:table-cell">Used as</th>
                </tr>
              </thead>
              <tbody>
                {DATA_ROWS.map(({ what, source, use }) => (
                  <tr key={what} className="border-t border-line align-top">
                    <th scope="row" className="px-4 py-3 font-display font-semibold whitespace-nowrap text-ink">
                      {what}
                    </th>
                    <td className="px-4 py-3 text-ink/80">
                      {source}
                      <span className="mt-1 block text-ink-muted sm:hidden">{use}</span>
                    </td>
                    <td className="hidden px-4 py-3 text-ink/80 sm:table-cell">{use}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AboutSection>

        <AboutSection id="about-usage" title="How to use it">
          <ol className="flex flex-col gap-5">
            <UsageStep n={1} title="Start with the real flood">
              In <Ui>Setup</Ui>, press <Ui>Replay May 2024 flood</Ui>. It runs the validated scenario: the fast engine
              first (it returns almost at once), then the temporal CA up to the observed peak, on the 90 m grid and
              side by side in the <Ui>Compare</Ui> view.
            </UsageStep>
            <UsageStep n={2} title="Or set up your own run">
              Pick an <strong className="text-ink">engine</strong> and a <strong className="text-ink">grid</strong>.
              For the temporal CA, choose a scenario: <Ui>May 2024 gauges</Ui> drives the run with the real river
              record, while <Ui>Seeded pool</Ui> drops a pool of water and lets it spread. For a seeded pool you can
              set the number of steps and the volume, and click the map inside the dashed outline to choose where
              the pool goes. <Ui>Engine tuning</Ui> holds the neighborhood, frame interval and outflow fraction; the
              defaults are the validated ones.
            </UsageStep>
            <UsageStep n={3} title="Run it">
              Press <Ui>Start simulation</Ui> in the top bar. Settings lock while a run is going; <Ui>Stop</Ui> ends it
              early and keeps what has arrived. The status pill in the top bar shows where the run is.
            </UsageStep>
            <UsageStep n={4} title="Explore the map">
              <ul className="mt-1 flex list-disc flex-col gap-1.5 pl-5 marker:text-ink-muted">
                <li>
                  <Ui>Temporal</Ui>, <Ui>Fast</Ui> and <Ui>Compare</Ui> (top right) switch between results. In Compare
                  both maps pan and zoom together.
                </li>
                <li>
                  The <strong className="text-ink">timeline</strong> under the temporal map scrubs and replays the
                  frames received so far; <Ui>Jump to latest</Ui> follows the run again.
                </li>
                <li>
                  <Ui>Layers</Ui>: <Ui>Observed</Ui> colors each cell by agreement with the real May 2024 extent;{' '}
                  <Ui>Terrain</Ui> and <Ui>Roughness</Ui> show the model&rsquo;s own inputs.
                </li>
                <li>
                  Click any cell to inspect its elevation, land cover, Manning&rsquo;s n, depth and how the water
                  leaving it is split between its neighbors.
                </li>
                <li>The picker at the bottom right changes the basemap: relief, topographic, streets or satellite.</li>
              </ul>
            </UsageStep>
            <UsageStep n={5} title="Read the numbers">
              <Ui>Results</Ui> shows the run&rsquo;s flooded area, its scores against the observed flood (CSI, hit
              rate, false alarm rate) and, after a replay, how the two engines agree. <Ui>Log</Ui> keeps a line
              per frame received: the step, simulated time and volume, or the fast engine&rsquo;s discharge and timing.
            </UsageStep>
          </ol>
          <p className="text-sm text-ink-muted">
            Tip: click the active menu item, or the panel button at the bottom of the menu, to collapse the side panel
            and give the map the full width.
          </p>
        </AboutSection>

        <AboutSection id="about-limits" title="Limits worth knowing">
          <ul className="flex list-disc flex-col gap-2 pl-5 marker:text-ink-muted">
            <li>
              Only the 90 m grid is validated. The 30 m and 60 m grids run the same model at finer detail, but their
              results are not scored.
            </li>
            <li>
              The validated results use the 8-neighbor (Moore) rule. The 4-neighbor (von Neumann) option is there to
              compare against, not validated.
            </li>
            <li>
              The observed map leaves out part of the Estrela bank, so those cells are shown as &ldquo;not scored&rdquo;
              and excluded from the gap-corrected CSI.
            </li>
            <li>
              Fast mode is checked on flood extent only: there are no depth observations to validate its depths.
            </li>
            <li>
              A seeded pool is a synthetic test of the mechanics, not a real event; its volume is the summed depth of
              the cells, in meters.
            </li>
          </ul>
        </AboutSection>

        <footer className="flex flex-col gap-3 border-t border-line pt-8 text-sm text-ink-muted">
          <p>
            Built with Python, NumPy, rasterio and FastAPI (with WebSockets) on the backend, and React, TypeScript,
            Vite and Leaflet on the frontend, packaged with Docker Compose.
          </p>
          <button
            type="button"
            onClick={onClose}
            className="self-start rounded-lg border border-accent px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-accent hover:text-canvas"
          >
            Open the simulator
          </button>
        </footer>
      </article>
    </div>
  )
}

function UsageStep({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <li className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3">
      <span
        aria-hidden="true"
        className="flex h-7 w-7 items-center justify-center rounded-full border border-accent font-display text-sm font-semibold text-accent"
      >
        {n}
      </span>
      <div className="flex flex-col gap-1">
        <h3 className="font-display text-lg font-semibold text-ink">{title}</h3>
        <div>{children}</div>
      </div>
    </li>
  )
}
