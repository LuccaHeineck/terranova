import type { ObservedExtent, Resolution } from '../types/simulation'
import type { DepthGrid } from './depthGrid'
import { isWet } from './depthToImage'

/**
 * The observed May 2024 extent as the client keeps it: one byte per cell, row-major like a frame's depth grid.
 * The arrays sit in private fields for the same reason as DepthGrid's (React's dev-mode prop diffing would
 * enumerate a shallowly reachable typed array element by element).
 */
export class ObservedMasks {
  readonly resolution: Resolution
  readonly rows: number
  readonly cols: number
  /** River stage of the reference layer (the May 2024 peak), m. */
  readonly stageM: number
  readonly observedCount: number
  readonly excludedCount: number
  readonly #observed: Uint8Array
  readonly #excluded: Uint8Array

  constructor(extent: ObservedExtent) {
    const [rows, cols] = extent.grid_shape
    this.resolution = extent.resolution
    this.rows = rows
    this.cols = cols
    this.stageM = extent.stage_m
    this.#observed = new Uint8Array(rows * cols)
    this.#excluded = new Uint8Array(rows * cols)
    for (const cell of extent.observed_cells) this.#observed[cell] = 1
    for (const cell of extent.excluded_cells) this.#excluded[cell] = 1
    this.observedCount = extent.observed_cells.length
    this.excludedCount = extent.excluded_cells.length
  }

  get observed(): Uint8Array {
    return this.#observed
  }

  /** Cells the Estrela coverage-gap correction leaves out of scoring (docs/tcc-deviations.md section 16.2). */
  get excluded(): Uint8Array {
    return this.#excluded
  }
}

export interface Scores {
  /** Flooded in both. */
  tp: number
  /** Flooded in the simulation only. */
  fp: number
  /** Flooded in the observation only. */
  fn: number
  /** TP / (TP + FP + FN); null where undefined (nothing flooded in either). */
  csi: number | null
  /** TP / (TP + FN); null with no observed flooding. */
  hitRate: number | null
  /** FP / (TP + FP); null with no simulated flooding. */
  falseAlarmRate: number | null
}

export interface ObservedAgreement {
  /** Scored without the excluded cells: the gap-corrected numbers the documented CSI 0.8997 is. */
  corrected: Scores
  /** Scored over the whole grid. */
  naive: Scores
}

function ratio(numerator: number, denominator: number): number | null {
  return denominator === 0 ? null : numerator / denominator
}

function scores(tp: number, fp: number, fn: number): Scores {
  return {
    tp,
    fp,
    fn,
    csi: ratio(tp, tp + fp + fn),
    hitRate: ratio(tp, tp + fn),
    falseAlarmRate: ratio(fp, tp + fp),
  }
}

/**
 * A simulated extent scored against the observed one, with the same confusion counts as the backend's
 * `validation/metrics.py`. Null when the frame is on a different grid than the observation.
 */
export function scoreAgainstObserved({ values: depth, rows, cols }: DepthGrid, masks: ObservedMasks): ObservedAgreement | null {
  if (rows !== masks.rows || cols !== masks.cols) return null
  const { observed, excluded } = masks
  // [tp, fp, fn] over every cell, and over the scored (non-excluded) cells only.
  const all = [0, 0, 0]
  const scored = [0, 0, 0]
  for (let cell = 0; cell < depth.length; cell++) {
    const sim = isWet(depth[cell])
    const obs = observed[cell] === 1
    const kind = sim && obs ? 0 : sim ? 1 : obs ? 2 : -1
    if (kind < 0) continue
    all[kind]++
    if (!excluded[cell]) scored[kind]++
  }
  return { corrected: scores(scored[0], scored[1], scored[2]), naive: scores(all[0], all[1], all[2]) }
}

/** The colors of the thesis' confusion-map figures (backend/examples/plot_confusion_map.py), reused on the map. */
export const AGREEMENT_COLORS = {
  hit: '#2a78d6',
  missed: '#eb6834',
  falseAlarm: '#1baf7a',
  notScored: '#8c8c8c',
} as const

/** The observed extent drawn on its own, before any run. */
export const OBSERVED_COLOR = '#6d28d9'

type Rgba = [number, number, number, number]

function rgba(hex: string, alpha = 255): Rgba {
  return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16), alpha]
}

const HIT = rgba(AGREEMENT_COLORS.hit)
const MISSED = rgba(AGREEMENT_COLORS.missed)
const FALSE_ALARM = rgba(AGREEMENT_COLORS.falseAlarm)
// Lighter than the scored classes: the model floods it, but the reference never modeled it.
const NOT_SCORED = rgba(AGREEMENT_COLORS.notScored, 170)
const OBSERVED = rgba(OBSERVED_COLOR)

function paint(rows: number, cols: number, colorOf: (cell: number) => Rgba | null): string {
  const canvas = document.createElement('canvas')
  canvas.width = cols
  canvas.height = rows
  const ctx = canvas.getContext('2d')!
  const image = ctx.createImageData(cols, rows)
  for (let cell = 0; cell < rows * cols; cell++) {
    const color = colorOf(cell)
    if (color) image.data.set(color, cell * 4)
  }
  ctx.putImageData(image, 0, 0)
  return canvas.toDataURL()
}

/**
 * A simulated extent against the observed one, cell by cell: hit, missed, false alarm, and - where the
 * simulation floods an excluded cell - not scored. Dry cells the reference also leaves dry stay transparent,
 * as do excluded dry ones, so the gap correction shows only where it changes a score.
 */
export function agreementToImageDataUrl(grid: DepthGrid, masks: ObservedMasks): string | null {
  if (grid.rows !== masks.rows || grid.cols !== masks.cols) return null
  const depth = grid.values
  const { observed, excluded } = masks
  return paint(grid.rows, grid.cols, (cell) => {
    const sim = isWet(depth[cell])
    const obs = observed[cell] === 1
    if (sim && excluded[cell] && !obs) return NOT_SCORED
    if (sim && obs) return HIT
    if (sim) return FALSE_ALARM
    if (obs) return MISSED
    return null
  })
}

/** The observed extent alone. */
export function observedToImageDataUrl(masks: ObservedMasks): string {
  const { observed } = masks
  return paint(masks.rows, masks.cols, (cell) => (observed[cell] === 1 ? OBSERVED : null))
}
