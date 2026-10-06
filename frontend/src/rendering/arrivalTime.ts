import { int, upTo } from '../i18n'
import type { FirstWetGrid, FirstWetUnit } from './firstWet'
import { hexToRgba, paint } from './paint'

/**
 * The arrival-time ramp, earliest band first: one magenta hue, darkest where the water arrived first (the cells
 * that had the least warning), lightening in even OKLCH lightness steps (0.30 -> 0.66, C 0.13, h 350). Its own
 * hue, so it never reads as a depth (the blue ramp) or the fast extent (burnt orange) beside it in Compare.
 * Checked with the dataviz skill's validator as an ordinal ramp: monotone lightness, adjacent steps >= 0.06 apart,
 * and the lightest band clears 2:1 against OSM land (#f2efe9) and OSM water (#aad3df).
 */
export const ARRIVAL_COLORS = ['#580037', '#6e184a', '#852e5e', '#9d4472', '#b45987', '#cc6f9d'] as const

export interface ArrivalBand {
  /** Inclusive lower edge, in the grid's unit (seconds or engine steps). */
  min: number
  /** Exclusive upper edge; null for the open-ended last band. */
  max: number | null
  color: string
}

// Band widths a gauge-driven run's bands snap to, in hours: whole days once the run spans several.
const HOUR_STEPS = [1, 2, 3, 6, 12, 24, 48]

/** The smallest "nice" number (1, 2 or 5 times a power of ten) at or above `value`. */
function niceCeil(value: number): number {
  if (value <= 1) return 1
  const power = 10 ** Math.floor(Math.log10(value))
  return ([1, 2, 5, 10].find((m) => m * power >= value) ?? 10) * power
}

/**
 * Equal-width bands covering [0, span], one per ramp color, with a round width: whole hours (whole days for a
 * multi-day run) for real time, 1/2/5 x 10^k for engine steps. `span` is the run's latest time, so the bands only
 * change while a live run grows, not while scrubbing its timeline.
 */
export function arrivalBands(span: number, unit: FirstWetUnit): ArrivalBand[] {
  const count = ARRIVAL_COLORS.length
  const raw = Math.max(span, 1) / count
  const width =
    unit === 'seconds'
      ? (HOUR_STEPS.find((h) => h * 3600 >= raw) ?? Math.ceil(raw / 86400) * 24) * 3600
      : niceCeil(raw)
  return ARRIVAL_COLORS.map((color, i) => ({
    min: i * width,
    max: i === count - 1 ? null : (i + 1) * width,
    color,
  }))
}

/** "0–24 h" / "≥ 120 h", or engine steps for a seeded pool. */
export function arrivalBandLabel({ min, max }: ArrivalBand, unit: FirstWetUnit): string {
  const fmt = (v: number) => (unit === 'seconds' ? upTo(v / 3600, 2) : int(v))
  const suffix = unit === 'seconds' ? ' h' : ''
  return max === null ? `≥ ${fmt(min)}${suffix}` : `${fmt(min)}–${fmt(max)}${suffix}`
}

/**
 * Arrival-time overlay: each cell that was wet by `upTo` takes the band of the time it first got wet; cells still
 * dry then are transparent. Drawn up to the timeline's selected time, so scrubbing replays the spread.
 */
export function arrivalToImageDataUrl(grid: FirstWetGrid, upTo: number, bands: readonly ArrivalBand[]): string {
  const colors = bands.map(({ color }) => hexToRgba(color))
  const times = grid.values
  return paint(grid.rows, grid.cols, (cell) => {
    const t = times[cell]
    if (Number.isNaN(t) || t > upTo) return null
    let i = 0
    while (i < bands.length - 1 && t >= bands[i].max!) i++
    return colors[i]
  })
}
