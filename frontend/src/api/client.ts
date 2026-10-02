import { API_BASE_URL } from './config'
import type {
  GridInfo,
  GridInputs,
  HydrographRecord,
  ObservedExtent,
  Resolution,
  SimulationCreated,
  SimulationParams,
} from '../types/simulation'

export async function createSimulation(params: SimulationParams): Promise<SimulationCreated> {
  const response = await fetch(`${API_BASE_URL}/simulations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(`POST /simulations failed (${response.status}): ${JSON.stringify(body)}`)
  }

  return response.json()
}

export async function fetchGrids(): Promise<GridInfo[]> {
  const response = await fetch(`${API_BASE_URL}/grids`)
  if (!response.ok) throw new Error(`GET /grids failed (${response.status})`)
  return response.json()
}

/** Thrown for an HTTP error answer, as opposed to the API being unreachable. */
export class HttpError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function fetchObservedExtent(): Promise<ObservedExtent> {
  const response = await fetch(`${API_BASE_URL}/validation/may2024`)
  if (!response.ok) throw new HttpError(`GET /validation/may2024 failed (${response.status})`, response.status)
  return response.json()
}

export async function fetchGridInputs(resolution: Resolution): Promise<GridInputs> {
  const response = await fetch(`${API_BASE_URL}/grids/${resolution}/inputs`)
  if (!response.ok) throw new HttpError(`GET /grids/${resolution}/inputs failed (${response.status})`, response.status)
  return response.json()
}

export async function fetchHydrograph(): Promise<HydrographRecord> {
  const response = await fetch(`${API_BASE_URL}/hydrograph`)
  if (!response.ok) throw new HttpError(`GET /hydrograph failed (${response.status})`, response.status)
  return response.json()
}
