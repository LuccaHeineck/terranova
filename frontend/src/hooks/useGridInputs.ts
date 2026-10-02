import { useEffect, useState } from 'react'
import { fetchGridInputs, HttpError } from '../api/client'
import { ModelInputs } from '../rendering/modelInputs'
import type { Resolution } from '../types/simulation'

/** Retry delay while the API is unreachable (e.g. still starting under Docker Compose). */
const RETRY_MS = 3000

/**
 * A grid's model inputs (GET /grids/{resolution}/inputs), loaded the first time they are needed - an input layer
 * turned on, or a cell inspected - and kept for every grid loaded since. Pass null while nothing needs them.
 * Null until loaded, and for good if the API answers with an error.
 */
export function useGridInputs(resolution: Resolution | null): ModelInputs | null {
  const [loaded, setLoaded] = useState<Partial<Record<Resolution, ModelInputs>>>({})
  const cached = resolution !== null && resolution in loaded

  useEffect(() => {
    if (resolution === null || cached) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const load = () => {
      fetchGridInputs(resolution).then(
        (inputs) => {
          if (!cancelled) setLoaded((prev) => ({ ...prev, [resolution]: new ModelInputs(inputs) }))
        },
        (e: unknown) => {
          // Only an unreachable API is worth retrying; an HTTP error answer won't change until a restart.
          if (!cancelled && !(e instanceof HttpError)) timer = setTimeout(load, RETRY_MS)
        },
      )
    }
    load()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [resolution, cached])

  return resolution === null ? null : (loaded[resolution] ?? null)
}
