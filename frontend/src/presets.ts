import type { SimulationParams } from './types/simulation'

/** Mirrors the backend's DEFAULT_OUTFLOW_FRACTION (simulation/engine.py) - keep in sync by hand. */
export const DEFAULT_OUTFLOW_FRACTION = 0.085

/** Default frame interval of a gauge-driven run: 100k+ engine steps, so far coarser than a seeded pool's. */
export const GAUGE_DRIVEN_FRAME_INTERVAL = 500

/**
 * The one scenario both engines are validated on (docs/tcc-deviations.md sections 19 and 21): the real
 * May 2024 event on the 90m validation grid, fast mode at the observed peak vs. the temporal CA run to that
 * peak. The fast run goes first because it returns in well under a second; the temporal one then streams.
 * outflow_fraction is pinned to the default because the documented results (temporal peak at step 134,639
 * with 1,955 flooded cells; 1,648 / 307 / 1,192 agreement) were produced with it.
 */
export const MAY_2024_REPLAY = {
  fast: { mode: 'fast', resolution: 90 },
  temporal: {
    mode: 'gauge_driven',
    resolution: 90,
    stop_at_peak: true,
    frame_interval: GAUGE_DRIVEN_FRAME_INTERVAL,
    outflow_fraction: DEFAULT_OUTFLOW_FRACTION,
  },
} as const satisfies Record<'fast' | 'temporal', SimulationParams>
