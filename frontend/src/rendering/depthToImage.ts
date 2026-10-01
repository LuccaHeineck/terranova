import type { DepthGrid } from './depthGrid'

/**
 * Wet-cell cutoff for comparing extents, in meters. Mirrors the backend's
 * FLOODED_DEPTH_THRESHOLD_M (api/routers/simulations.py). Keep the two in sync by hand.
 * Also the lowest edge of the color scale, so the drawn extent is exactly the extent the log panel counts.
 */
export const FLOODED_DEPTH_THRESHOLD_M = 0.01

export interface DepthBand {
  /** Inclusive lower edge, in meters. */
  min: number
  /** Exclusive upper edge, in meters; null for the open-ended top band. */
  max: number | null
  color: string
}

/**
 * The depth color scale of the temporal overlay and its map legend. The fast overlay does not use it: only
 * the fast mode's extent is validated. Its steady rating-curve depth is plausible (median ~10 m since
 * docs/tcc-deviations.md section 23, down from section 19's ~33 m), but no depth observations exist to check it
 * against (section 20), so it draws its extent in one flat color instead (FAST_EXTENT_COLOR).
 *
 * Fixed bands for this ROI rather than a scale derived from the data, because:
 * - A running max over the run's frames gets captured by the gauge-driven first-step spike. Step 1 pushes
 *   the whole river's discharge into the 9 inflow-mask cells (~250 m deep at 30m). A frame that early
 *   (a small frame interval) then pins the scale, so the real ~12-14 m flood renders at t < 0.06, i.e.
 *   uniformly faint, for the rest of the run.
 * - A per-frame percentile would rescale every frame. An early, shallow frame would look as deep as the
 *   peak, and the legend's numbers would change under the viewer.
 * The top band opens at 20 m: the May 2024 event's stage rise (~14 m -> 33.66 m at the gauge), and between the
 * 90th and 95th percentile of wet-cell depth (17.7 m / 22.7 m) at the peak of a real temporal run on the 90m
 * grid. Before the flood wave arrives the same run sits at p99 ~13.5 m (median ~4 m), so the lower bands
 * carry the early frames and the scale still shows depth structure all the way to the peak. Deeper cells (the
 * gauge-driven inflow spike) take the top color.
 *
 * Colors: one blue hue, lightness stepping down evenly in OKLCH (0.64 -> 0.30). The lightest band still
 * clears 2:1 contrast against OSM's own light-blue water (#aad3df) - a lighter blue overlay disappears
 * into the river, which is why step 6 once moved to orange-red - and every band is far darker than OSM's
 * pastel land, parks and roads.
 */
export const DEPTH_BANDS: readonly DepthBand[] = [
  { min: FLOODED_DEPTH_THRESHOLD_M, max: 0.5, color: '#3a8cf0' },
  { min: 0.5, max: 2, color: '#2276d9' },
  { min: 2, max: 5, color: '#0262c1' },
  { min: 5, max: 10, color: '#004f9f' },
  { min: 10, max: 20, color: '#013d7d' },
  { min: 20, max: null, color: '#002c5e' },
]

/** Opacity of the flood overlay; the legend swatches use the same value so they match the map. */
export const OVERLAY_OPACITY = 0.8

/**
 * The fast overlay's single "flooded" color: extent only, since only its extent is validated (see DEPTH_BANDS).
 * Burnt orange, checked with the dataviz skill's palette validator and composited at OVERLAY_OPACITY:
 * - against OSM: 3.37:1 on land (#f2efe9) and 2.71:1 on water (#aad3df), above the ramp's own 2.12:1 floor
 *   on water; opaque, >= 3:1 on land, water, residential and forest;
 * - against the blue ramp, for the two Compare panes: OKLab dE >= 32 to every band, and >= 22 under
 *   simulated protan/deutan/tritan vision (target >= 8). Another blue or a purple would read as "a depth".
 */
export const FAST_EXTENT_COLOR = '#c2410c'

type Rgb = [number, number, number]

function hexToRgb(color: string): Rgb {
  return [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16)) as Rgb
}

const BAND_RGB = DEPTH_BANDS.map(({ color }) => hexToRgb(color))
const FAST_EXTENT_RGB = hexToRgb(FAST_EXTENT_COLOR)

function bandIndex(d: number): number {
  let i = 0
  while (i < DEPTH_BANDS.length - 1 && d >= DEPTH_BANDS[i].max!) i++
  return i
}

/** Temporal overlay: each wet cell takes its depth band's color. */
export function depthToImageDataUrl(grid: DepthGrid): string {
  return rasterize(grid, (d) => BAND_RGB[bandIndex(d)])
}

/** Fast overlay: every wet cell takes FAST_EXTENT_COLOR - extent only, no depth. */
export function extentToImageDataUrl(grid: DepthGrid): string {
  return rasterize(grid, () => FAST_EXTENT_RGB)
}

/**
 * Rasterizes a row-major depth grid to a data URL: dry cells are transparent, wet ones take `colorOf(depth)`.
 * Cell i is pixel i, since both the grid and ImageData are row-major.
 */
function rasterize({ values: depth, rows, cols }: DepthGrid, colorOf: (d: number) => Rgb): string {
  const canvas = document.createElement('canvas')
  canvas.width = cols
  canvas.height = rows
  const ctx = canvas.getContext('2d')!
  const image = ctx.createImageData(cols, rows)

  for (let cell = 0; cell < depth.length; cell++) {
    const d = depth[cell]
    const i = cell * 4
    if (!isWet(d)) {
      image.data[i + 3] = 0
      continue
    }
    const [red, green, blue] = colorOf(d)
    image.data[i] = red
    image.data[i + 1] = green
    image.data[i + 2] = blue
    image.data[i + 3] = 255
  }

  ctx.putImageData(image, 0, 0)
  return canvas.toDataURL()
}

export interface ExtentAgreement {
  both: number
  temporalOnly: number
  fastOnly: number
}

/** Whether a depth counts as flooded: above FLOODED_DEPTH_THRESHOLD_M, the same cutoff the backend scores with. */
export function isWet(d: number): boolean {
  return d > FLOODED_DEPTH_THRESHOLD_M
}

export function countFlooded({ values: depth }: DepthGrid): number {
  let count = 0
  for (let cell = 0; cell < depth.length; cell++) {
    if (isWet(depth[cell])) count++
  }
  return count
}

/** Cell counts of where two extents agree and disagree, or null if the grids differ. */
export function compareExtents(temporalGrid: DepthGrid, fastGrid: DepthGrid): ExtentAgreement | null {
  if (temporalGrid.rows !== fastGrid.rows || temporalGrid.cols !== fastGrid.cols) return null
  const temporal = temporalGrid.values
  const fast = fastGrid.values
  const counts: ExtentAgreement = { both: 0, temporalOnly: 0, fastOnly: 0 }
  for (let cell = 0; cell < temporal.length; cell++) {
    const t = isWet(temporal[cell])
    const f = isWet(fast[cell])
    if (t && f) counts.both++
    else if (t) counts.temporalOnly++
    else if (f) counts.fastOnly++
  }
  return counts
}
