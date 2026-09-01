export interface SimulationParams {
  steps: number
  frame_interval: number
  outflow_fraction?: number
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
  step: number
  depth: number[][]
  volume: number
}

export interface SimulationDone {
  done: true
}

export type StreamMessage = SimulationFrame | SimulationDone

export function isDone(message: StreamMessage): message is SimulationDone {
  return (message as SimulationDone).done === true
}
