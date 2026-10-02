import type { ModelInputs } from './modelInputs'
import { hexToRgba, paint } from './paint'
import type { Rgba } from './paint'

/**
 * The model-input layers drawn under the flood overlay: the terrain Z and the Manning roughness the engine runs
 * on, one pixel per cell like the flood overlay, so the CA's own cells stay visible.
 *
 * Both ramps are sequential, light to dark in OKLCH, checked with the dataviz skill's palette validator. Neither
 * is blue (the depth ramp), burnt orange (the fast extent) or the agreement colors' violet, so a flood frame
 * drawn over an input layer still reads as water.
 * - Terrain: one earth hue (h 65), light at the lowest cell to dark at the highest. A continuous ramp, so its
 *   lightest stop may recede toward the map.
 * - Roughness: yellow-green to deep green (h 110 -> 165, like ColorBrewer's YlGn), light where water moves
 *   easily to dark where it is slowed. It is ordinal, one step per distinct n on the grid (see
 *   roughnessLevels), and the hue drift is deliberate. A one-hue green ramp only managed ~8-9 OKLab dE between
 *   adjacent steps, and its darkest pair less still; drifting the hue lifts the worst adjacent pair to ~10 dE.
 *   That is about the ceiling for six ordered steps (the validator's 15 floor is for unordered categories).
 *   The legend names every step, so no class is identified by color alone.
 */
const TERRAIN_STOPS = ['#ffead7', '#e5c8ac', '#cba683', '#b1855a', '#976530', '#7e4500'].map((c) => hexToRgba(c))
const ROUGHNESS_STOPS = ['#eff159', '#b6d551', '#80b74c', '#4a9847', '#007940', '#005a37'].map((c) => hexToRgba(c))

/**
 * Opacity of each input layer; the legend swatches use the same value so they match the map. Roughness is drawn
 * opaque: its classes are told apart by small color steps, which the basemap showing through would blur.
 */
export const INPUT_OVERLAY_OPACITY = { terrain: 0.85, roughness: 1 } as const

/** Sun position for the hillshade: the cartographic convention, from the north-west and 45 degrees up. */
const SUN_AZIMUTH_DEG = 315
const SUN_ALTITUDE_DEG = 45

function lerpStops(stops: readonly Rgba[], t: number): Rgba {
  const x = Math.min(Math.max(t, 0), 1) * (stops.length - 1)
  const i = Math.min(Math.floor(x), stops.length - 2)
  const f = x - i
  const [a, b] = [stops[i], stops[i + 1]]
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, 255]
}

function toHex([r, g, b]: Rgba): string {
  return `#${[r, g, b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')}`
}

/**
 * The distinct Manning's n values on a grid, ascending: the roughness layer's steps. Colored by rank, not by
 * value: the region's n values cluster (0.025-0.040 for open ground, crops and water; 0.150-0.160 for urban
 * area and forest), and a value scale gave the four low ones nearly the same color. Every served grid has the
 * same six values, so a color still means the same n on each.
 */
export function roughnessLevels(inputs: ModelInputs): number[] {
  return [...new Set(inputs.classes.map((c) => c.manning_n))].sort((a, b) => a - b)
}

/** The roughness layer's color for each level: evenly spaced ramp steps, exact stops when there are six. */
function levelColors(levels: readonly number[]): Map<number, Rgba> {
  const last = Math.max(levels.length - 1, 1)
  return new Map(levels.map((n, rank) => [n, lerpStops(ROUGHNESS_STOPS, rank / last)]))
}

/** The roughness layer's color for each n on the grid, for its legend. */
export function roughnessColors(inputs: ModelInputs): Map<number, string> {
  const colors = levelColors(roughnessLevels(inputs))
  return new Map([...colors].map(([n, rgba]) => [n, toHex(rgba)]))
}

/** The terrain ramp's colors from the lowest to the highest cell, for its legend's gradient. */
export const TERRAIN_GRADIENT = TERRAIN_STOPS.map(toHex)

/** The roughness ramp's colors from the smoothest to the roughest n, for the layer toggle's swatch. */
export const ROUGHNESS_GRADIENT = ROUGHNESS_STOPS.map(toHex)

/**
 * Illumination of each cell, 0 (facing away from the sun) to 1 (facing it), from Horn's 3x3 gradient over the
 * cell's Moore neighbors - edge cells repeat their own value for the missing ones. In metres throughout (the
 * grid is square in UTM), so no geographic scaling. Azimuth is from grid north, under 0.5 degrees off true north
 * here.
 */
export function hillshade(
  elevation: Float32Array,
  rows: number,
  cols: number,
  dx: number,
  azimuthDeg = SUN_AZIMUTH_DEG,
  altitudeDeg = SUN_ALTITUDE_DEG,
): Float32Array {
  const az = (azimuthDeg * Math.PI) / 180
  const alt = (altitudeDeg * Math.PI) / 180
  // Unit vector toward the sun, in (east, north, up).
  const sun = [Math.sin(az) * Math.cos(alt), Math.cos(az) * Math.cos(alt), Math.sin(alt)]
  const z = (r: number, c: number) =>
    elevation[Math.min(Math.max(r, 0), rows - 1) * cols + Math.min(Math.max(c, 0), cols - 1)]
  const shade = new Float32Array(rows * cols)
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      // Row 0 is north, so "north minus south" is the row above minus the row below.
      const east = z(r - 1, c + 1) + 2 * z(r, c + 1) + z(r + 1, c + 1)
      const west = z(r - 1, c - 1) + 2 * z(r, c - 1) + z(r + 1, c - 1)
      const north = z(r - 1, c - 1) + 2 * z(r - 1, c) + z(r - 1, c + 1)
      const south = z(r + 1, c - 1) + 2 * z(r + 1, c) + z(r + 1, c + 1)
      const dzdE = (east - west) / (8 * dx)
      const dzdN = (north - south) / (8 * dx)
      // The surface normal (-dz/dE, -dz/dN, 1), normalized, dotted with the sun vector.
      const norm = Math.hypot(dzdE, dzdN, 1)
      shade[r * cols + c] = Math.max(0, (-dzdE * sun[0] - dzdN * sun[1] + sun[2]) / norm)
    }
  }
  return shade
}

/**
 * Tinted relief: each cell's elevation color, darkened or lightened by its hillshade. The shade is normalized so
 * flat ground keeps its tint exactly (the floodplain is nearly flat, and its color is what the legend reads).
 */
export function terrainToImageDataUrl(inputs: ModelInputs): string {
  const { rows, cols, dx, elevation, minElevation, maxElevation } = inputs
  const shade = hillshade(elevation, rows, cols, dx)
  const flat = Math.sin((SUN_ALTITUDE_DEG * Math.PI) / 180)
  const span = maxElevation - minElevation || 1
  return paint(rows, cols, (cell) => {
    const [r, g, b] = lerpStops(TERRAIN_STOPS, (elevation[cell] - minElevation) / span)
    const k = Math.min(Math.max(0.45 + 0.55 * (shade[cell] / flat), 0.3), 1.15)
    return [Math.min(r * k, 255), Math.min(g * k, 255), Math.min(b * k, 255), 255]
  })
}

/** Manning's n per cell, one ramp step per distinct n on the grid. */
export function roughnessToImageDataUrl(inputs: ModelInputs): string {
  const { rows, cols, roughness } = inputs
  const colors = levelColors(roughnessLevels(inputs))
  // Per-cell n is a float32 copy of the table's float64 value, so look it up by the nearest level.
  const levels = [...colors.keys()]
  const colorOf = (n: number) =>
    levels.reduce((best, level) => (Math.abs(level - n) < Math.abs(best - n) ? level : best), levels[0])
  return paint(rows, cols, (cell) => (Number.isNaN(roughness[cell]) ? null : colors.get(colorOf(roughness[cell]))!))
}
