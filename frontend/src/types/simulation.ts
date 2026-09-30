export type RunMode = 'seeded_pool' | 'gauge_driven' | 'fast'

/**
 * The temporal engine's neighborhood: Moore (8 neighbors) is the TCC's model and the only validated one;
 * von Neumann (4 orthogonal neighbors) is an unvalidated option (docs/tcc-deviations.md section 22).
 */
export type Neighborhood = 'moore' | 'von_neumann'

export const NEIGHBORHOOD_LABEL: Record<Neighborhood, string> = {
  moore: 'Moore',
  von_neumann: 'von Neumann',
}

/** Served grid resolutions, in meters: the live grid, an unvalidated 60 m grid and the validation grid. */
export type Resolution = 30 | 60 | 90

/** A WGS84 point, in degrees. */
export interface LatLon {
  lat: number
  lon: number
}

export interface SimulationParams {
  mode?: RunMode
  resolution?: Resolution
  steps?: number
  // Temporal modes only - a fast run has no time steps, and the backend rejects these for it.
  frame_interval?: number
  outflow_fraction?: number
  stop_at_peak?: boolean
  neighborhood?: Neighborhood
  // Seeded-pool only - the backend rejects these for the other modes.
  /** Summed cell depth (m), the frames' own `volume` unit. Default 400. */
  seed_volume?: number
  /** Where to center the pool; omitted seeds at the terrain's lowest point. */
  seed_location?: LatLon
}

export interface Bounds {
  west: number
  south: number
  east: number
  north: number
}

export interface SimulationCreated {
  run_id: string
  grid_shape: [number, number]
  bounds: Bounds
  /** Seeded-pool runs: the [row, col] the pool is centered on (the chosen cell, or the lowest point's). */
  seed_cell?: [number, number] | null
}

/** One served grid, from GET /grids - known before any run. */
export interface GridInfo {
  resolution: Resolution
  grid_shape: [number, number]
  /** Axis-aligned WGS84 envelope: what the overlay image is stretched over. */
  bounds: Bounds
  /**
   * The grid's true outline, four [lat, lon] corners clockwise from the top-left. The grid is north-up in
   * UTM, so it is slightly rotated in lat/lon and `bounds` also covers thin slivers outside it.
   */
  footprint: [number, number][]
}

export interface SimulationFrame {
  /** 0 for a fast-mode frame (no time integration). */
  step: number
  depth: number[][]
  volume: number
  // gauge_driven frames
  elapsed_time?: number
  cumulative_inflow?: number
  cumulative_outflow?: number
  // fast frames (the single frame of a fast run)
  peak_discharge_m3s?: number
  peak_elapsed_time?: number
  outflow_m3s?: number
  retained_m3s?: number
  flooded_cells?: number
  compute_seconds?: number
}

export interface GridShape {
  rows: number
  cols: number
}

export interface SimulationDone {
  done: true
}

export type StreamMessage = SimulationFrame | SimulationDone

export function isDone(message: StreamMessage): message is SimulationDone {
  return (message as SimulationDone).done === true
}
