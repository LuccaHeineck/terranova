import { NeighborhoodGlyph } from '../ui/icons'
import { DOCUMENTED } from './content'
import type { AboutCopy } from './content'
import { Formula, Strong, Ui } from './primitives'

export const aboutEn: AboutCopy = {
  kicker: 'About',
  title: 'Flood simulation for the Vale do Taquari, one cell at a time',
  lede: (
    <>
      Terranova simulates how the Taquari river spreads over the land between Lajeado and Estrela. It uses a{' '}
      <Strong>macroscopic cellular automaton</Strong>: the valley becomes a grid of cells, and each cell passes water to
      its neighbors by a simple local rule. The aim is a flood map fast enough to rerun many times, accurate enough to
      trust, built only from public data.
    </>
  ),
  credits:
    'Undergraduate thesis (TCC), Software Engineering, Univates · Lucca Coutinho Heineck · Advisor: Prof. Me. Edson Moacir Ahlert',
  openSimulator: 'Open the simulator',
  howToUse: 'How to use it',
  onThisPage: 'On this page',
  nav: {
    'about-problem': 'The problem',
    'about-model': 'The model',
    'about-engines': 'Two engines',
    'about-data': 'Data',
    'about-usage': 'How to use it',
    'about-limits': 'Limits',
  },

  problem: [
    <>
      In September 2023 and again in May 2024 the Vale do Taquari flooded beyond the 1941 record. In May 2024 the river
      at Lajeado and Estrela rose from 13.00 m to {DOCUMENTED.peakStageM.toFixed(2)} m in 72 hours.
    </>,
    <>
      Hydrodynamic models that solve the full shallow water equations (HEC-RAS 2D, for example) are accurate, but slow
      and costly to run. In an emergency you want to ask &ldquo;what if the river reaches this level?&rdquo; many times,
      quickly. This project asks whether a cellular automaton, run on public terrain, land-cover and gauge data, can
      draw a usable flood extent in a fraction of that time.
    </>,
  ],

  model: {
    intro: (
      <>
        Every cell stores two numbers: the terrain elevation <Formula>Z</Formula>, which never changes, and the water
        depth <Formula>H</Formula>, which does. At every step all cells apply the same rule at once:
      </>
    ),
    stepLabel: (n) => `Step ${n}`,
    steps: [
      {
        title: 'Find the water surface',
        body: (
          <>
            <Formula>WSE = Z + H</Formula>. Water only flows downhill on that surface, from a higher water level to a
            lower one.
          </>
        ),
      },
      {
        title: 'Split the outflow',
        body: (
          <>
            <span className="mb-1.5 flex items-center gap-2 text-ink">
              <NeighborhoodGlyph kind="moore" /> 8 neighbors (Moore)
            </span>
            Lower neighbors get a share weighted by Manning&rsquo;s equation, <Formula>√S / n</Formula>: steeper and
            smoother wins. Diagonals count their longer distance.
          </>
        ),
      },
      {
        title: 'Move the water',
        body: 'The volume leaving a cell is added to its neighbors. Nothing is created or lost: total volume changes only by what the river brings in and what leaves at the outlet.',
      },
    ],
    outro: (
      <>
        That last property, mass conservation, is the model&rsquo;s main correctness check. During a May 2024 run the
        timeline shows it live as the <em>balance</em>: volume minus net inflow, which stays at rounding-error level.
      </>
    ),
  },

  engines: {
    intro:
      'The app runs the same terrain and roughness through two engines that answer different questions. Both are scored against the observed May 2024 flood extent on the 90 m grid.',
    csiAtPeak: 'CSI at the peak',
    runTime: 'Run time, 90 m',
    temporal: {
      name: 'Temporal CA',
      tagline: 'How does the flood unfold?',
      body: 'The time-stepped cellular automaton above. Each step covers a real span of time derived from the Manning flow, so the run follows the actual May 2024 hydrograph hour by hour and streams frames to the map as it goes.',
    },
    fast: {
      name: 'Fast mode',
      tagline: 'How far does the water reach at the peak?',
      body: 'One steady extent at the observed peak discharge, with no time steps: the flow is routed once through the terrain from high to low, then spread across the floodplain with a rating curve built from height above the river. Inspired by Torres et al. (2022).',
    },
    csi: 'CSI, the Critical Success Index, counts the cells both the run and the observation call flooded, divided by every cell that either one calls flooded: 1 is a perfect match, and both missed cells and false alarms pull it down.',
  },

  data: {
    intro:
      'Everything comes from public sources and is preprocessed offline, so a run reads only local files. The study area is a box about 6 km across, over the river between Lajeado and Estrela, at 30, 60 or 90 m per cell.',
    headers: { input: 'Input', source: 'Source', usedAs: 'Used as' },
    rows: [
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
    ],
  },

  usage: {
    steps: [
      {
        title: 'Start with the real flood',
        body: (
          <>
            In <Ui>Setup</Ui>, press <Ui>Replay the May 2024 flood</Ui>. It runs the validated scenario: the fast engine
            first (it returns almost at once), then the temporal CA up to the observed peak, on the 90 m grid and side
            by side in the <Ui>Compare</Ui> view.
          </>
        ),
      },
      {
        title: 'Or set up your own run',
        body: (
          <>
            Pick an <Strong>engine</Strong> and a <Strong>grid</Strong>. For the temporal CA, choose a scenario:{' '}
            <Ui>May 2024 gauges</Ui> drives the run with the real river record, while <Ui>Seeded pool</Ui> drops a pool
            of water and lets it spread. For a seeded pool you can set the number of steps and the volume, and click the
            map inside the dashed outline to choose where the pool goes. <Ui>Engine tuning</Ui> holds the neighborhood,
            frame interval and outflow fraction; the defaults are the validated ones.
          </>
        ),
      },
      {
        title: 'Run it',
        body: (
          <>
            Press <Ui>Start simulation</Ui> in the top bar. Settings lock while a run is going; <Ui>Stop</Ui> ends it
            early and keeps what has arrived. The status pill in the top bar shows where the run is.
          </>
        ),
      },
      {
        title: 'Explore the map',
        body: (
          <ul className="mt-1 flex list-disc flex-col gap-1.5 pl-5 marker:text-ink-muted">
            <li>
              <Ui>Temporal</Ui>, <Ui>Fast</Ui> and <Ui>Compare</Ui> (top center) switch between results; in Compare both
              maps pan and zoom together. Under them, <Ui>Depth</Ui>, <Ui>Arrival</Ui> and <Ui>Max depth</Ui> choose what
              the temporal map shows.
            </li>
            <li>
              The <Strong>timeline</Strong> under the temporal map scrubs and replays the frames received so far;{' '}
              <Ui>Jump to latest</Ui> follows the run again.
            </li>
            <li>
              <Ui>Layers</Ui> (top right) changes the basemap and the overlay opacity. <Ui>Observed flood</Ui> colors
              each cell by agreement with the real May 2024 extent; <Ui>Terrain</Ui> and <Ui>Roughness</Ui> show the
              model&rsquo;s own inputs.
            </li>
            <li>
              <Ui>Export</Ui> saves the map as shown as a PNG, or the flooded extent as GeoJSON.
            </li>
            <li>
              Click any cell to inspect its elevation, land cover, Manning&rsquo;s n, depth and how the water leaving it
              is split between its neighbors.
            </li>
          </ul>
        ),
      },
      {
        title: 'Read the numbers',
        body: (
          <>
            <Ui>Results</Ui> shows the run&rsquo;s flooded area, the May 2024 gauge record, its scores against the
            observed flood (CSI, hit rate, false alarm rate) and, after a replay, how the two engines agree. <Ui>Log</Ui>{' '}
            keeps a line per frame received: the step, simulated time and volume, or the fast engine&rsquo;s discharge
            and timing.
          </>
        ),
      },
    ],
    tip: 'Tip: the panel button at the far left of the top bar hides the side panel and gives the map the full width.',
  },

  limitsTitle: 'Limits worth knowing',
  limits: [
    'The 90 m grid is the validated one, and the only one scored live in the app. The 60 m grid was scored offline against the same event (gap-corrected CSI 0.87 for the temporal engine, 0.88 for fast mode). The 30 m grid runs the same model at finer detail, but its results are not scored.',
    'The validated results use the 8-neighbor (Moore) rule. The 4-neighbor (von Neumann) option is there to compare against, not validated.',
    <>
      The observed map leaves out part of the Estrela bank, so those cells are shown as &ldquo;not scored&rdquo; and
      excluded from the gap-corrected CSI.
    </>,
    'Fast mode is checked on flood extent only: there are no depth observations to validate its depths.',
    'A seeded pool is a synthetic test of the mechanics, not a real event; its volume is the summed depth of the cells, in meters.',
  ],

  builtWith:
    'Built with Python, NumPy, rasterio and FastAPI (with WebSockets) on the backend, and React, TypeScript, Vite and Leaflet on the frontend, packaged with Docker Compose.',
}
