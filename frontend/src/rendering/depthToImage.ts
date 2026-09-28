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
 * The depth color scale, shared by the temporal and fast overlays and the map legend.
 *
 * Fixed bands for this ROI rather than a scale derived from the data, because:
 * - A running max over the run's frames gets captured by the gauge-driven first-step spike. Step 1 pushes
 *   the whole river's discharge into the 9 inflow-mask cells (~250 m deep at 30m). A frame that early
 *   (a small frame interval) then pins the scale, so the real ~12-14 m flood renders at t < 0.06, i.e.
 *   uniformly faint, for the rest of the run.
 * - A per-frame percentile would rescale every frame. An early, shallow frame would look as deep as the
 *   peak, and the legend's numbers would change under the viewer.
 * - The temporal and fast overlays have to share one scale for their colors to be comparable.
 * The top band opens at 20 m: the May 2024 event's stage rise (~14 m -> 33.66 m at the gauge), and between the
 * 90th and 95th percentile of wet-cell depth (17.7 m / 22.7 m) at the peak of a real temporal run on the 90m
 * grid. Before the flood wave arrives the same run sits at p99 ~13.5 m (median ~4 m), so the lower bands
 * carry the early frames and the scale still shows depth structure all the way to the peak. Deeper cells take
 * the top color: the inflow spike, and most of the fast mode's extent, whose steady Manning depth is known to
 * be too high (median ~33 m - docs/tcc-deviations.md section 19).
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

const BAND_RGB = DEPTH_BANDS.map(({ color }) => [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16)))

function bandIndex(d: number): number {
  let i = 0
  while (i < DEPTH_BANDS.length - 1 && d >= DEPTH_BANDS[i].max!) i++
  return i
}

/** Rasterizes a depth grid to a data URL: dry cells are transparent, wet ones take their band's color. */
export function depthToImageDataUrl(depth: number[][]): string {
  const rows = depth.length
  const cols = depth[0]?.length ?? 0
  const canvas = document.createElement('canvas')
  canvas.width = cols
  canvas.height = rows
  const ctx = canvas.getContext('2d')!
  const image = ctx.createImageData(cols, rows)

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const d = depth[r][c]
      const i = (r * cols + c) * 4
      if (!isWet(d)) {
        image.data[i + 3] = 0
        continue
      }
      const [red, green, blue] = BAND_RGB[bandIndex(d)]
      image.data[i] = red
      image.data[i + 1] = green
      image.data[i + 2] = blue
      image.data[i + 3] = 255
    }
  }

  ctx.putImageData(image, 0, 0)
  return canvas.toDataURL()
}

export interface ExtentAgreement {
  both: number
  temporalOnly: number
  fastOnly: number
}

function isWet(d: number): boolean {
  return d > FLOODED_DEPTH_THRESHOLD_M
}

export function countFlooded(depth: number[][]): number {
  let count = 0
  for (const row of depth) {
    for (const value of row) {
      if (isWet(value)) count++
    }
  }
  return count
}

function sameShape(a: number[][], b: number[][]): boolean {
  return a.length === b.length && (a[0]?.length ?? 0) === (b[0]?.length ?? 0)
}

/** Cell counts of where two extents agree and disagree, or null if the grids differ. */
export function compareExtents(temporal: number[][], fast: number[][]): ExtentAgreement | null {
  if (!sameShape(temporal, fast)) return null
  const counts: ExtentAgreement = { both: 0, temporalOnly: 0, fastOnly: 0 }
  for (let r = 0; r < temporal.length; r++) {
    for (let c = 0; c < temporal[r].length; c++) {
      const t = isWet(temporal[r][c])
      const f = isWet(fast[r][c])
      if (t && f) counts.both++
      else if (t) counts.temporalOnly++
      else if (f) counts.fastOnly++
    }
  }
  return counts
}
