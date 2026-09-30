import { useEffect, useState } from 'react'
import { fetchGrids } from '../api/client'
import type { GridInfo, Resolution } from '../types/simulation'

/** Retry delay while the API is unreachable (e.g. still starting under Docker Compose). */
const RETRY_MS = 3000

export interface GridsState {
  /** The served grids by resolution, once loaded. */
  grids: Partial<Record<Resolution, GridInfo>> | null
  /** The last load failure, while retrying. */
  error: string | null
}

/** The served grids' shapes and outlines (GET /grids), known before any run - what the map places seeds on. */
export function useGrids(): GridsState {
  const [state, setState] = useState<GridsState>({ grids: null, error: null })

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const load = () => {
      fetchGrids().then(
        (list) => {
          if (cancelled) return
          setState({ grids: Object.fromEntries(list.map((grid) => [grid.resolution, grid])), error: null })
        },
        (e: unknown) => {
          if (cancelled) return
          setState({ grids: null, error: e instanceof Error ? e.message : String(e) })
          timer = setTimeout(load, RETRY_MS)
        },
      )
    }
    load()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [])

  return state
}
