export type RunMode = 'seeded_pool' | 'gauge_driven' | 'fast'

/** Served grid resolutions, in meters: the live grid and the validation grid. */
export type Resolution = 30 | 90

export interface SimulationParams {
  mode?: RunMode
  resolution?: Resolution
  steps?: number
  // Temporal modes only - a fast run has no time steps, and the backend rejects these for it.
  frame_interval?: number
  outflow_fraction?: number
  stop_at_peak?: boolean
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
