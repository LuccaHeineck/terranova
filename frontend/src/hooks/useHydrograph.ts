import { useEffect, useState } from 'react'
import { fetchHydrograph, HttpError } from '../api/client'
import type { HydrographRecord } from '../types/simulation'

/** Retry delay while the API is unreachable (e.g. still starting under Docker Compose). */
const RETRY_MS = 3000

/**
 * The May 2024 gauge record (GET /hydrograph), loaded once. Null until it loads, and for good if the API answers
 * with an error (its raw gauge file isn't downloaded): the chart is then just not shown.
 */
export function useHydrograph(): HydrographRecord | null {
  const [record, setRecord] = useState<HydrographRecord | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const load = () => {
      fetchHydrograph().then(
        (loaded) => {
          if (!cancelled) setRecord(loaded)
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

  return record
}
