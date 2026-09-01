import { API_BASE_URL } from './config'
import type { SimulationCreated, SimulationParams } from '../types/simulation'

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
