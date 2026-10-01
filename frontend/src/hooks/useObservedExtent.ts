import { useEffect, useState } from 'react'
import { fetchObservedExtent, HttpError } from '../api/client'
import { ObservedMasks } from '../rendering/observed'

/** Retry delay while the API is unreachable (e.g. still starting under Docker Compose). */
const RETRY_MS = 3000

/**
 * The observed May 2024 extent (GET /validation/may2024), loaded once. Null until it loads, and for good if the
 * API answers with an error (its raw SGB layers aren't downloaded): the app works without it, minus scoring.
 */
export function useObservedExtent(): ObservedMasks | null {
  const [masks, setMasks] = useState<ObservedMasks | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const load = () => {
      fetchObservedExtent().then(
        (extent) => {
          if (!cancelled) setMasks(new ObservedMasks(extent))
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
  }, [])

  return masks
}
