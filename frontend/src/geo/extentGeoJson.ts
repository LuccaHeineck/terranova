import type { Bounds } from '../types/simulation'

/** A ring of grid-corner coordinates: x = column edge (0..cols), y = row edge (0..rows, downward). */
type Ring = [number, number][]

/**
 * Traces the outline of the `true` cells of a row-major mask into polygons with holes, in grid-corner
 * coordinates. Every wet cell side facing a dry cell (or the grid edge) becomes a directed edge, clockwise around
 * the wet cell on screen (y down), so the edges link into closed rings: outer boundaries clockwise, holes
 * counter-clockwise. Where two wet cells touch only at a corner, the trace turns right, keeping them separate
 * polygons (4-connectivity); a hole pinched at a corner is split in two (splitAtRepeats), so no ring touches
 * itself.
 */
export function traceExtent(mask: ArrayLike<boolean | number>, rows: number, cols: number): Ring[][] {
  const wet = (r: number, c: number) => r >= 0 && r < rows && c >= 0 && c < cols && Boolean(mask[r * cols + c])
  // Edges as [x0, y0, dx, dy], indexed by start vertex.
  const edges: [number, number, number, number][] = []
  const byStart = new Map<number, number[]>()
  const key = (x: number, y: number) => y * (cols + 1) + x
  const add = (x: number, y: number, dx: number, dy: number) => {
    const k = key(x, y)
    const list = byStart.get(k)
    if (list) list.push(edges.length)
    else byStart.set(k, [edges.length])
    edges.push([x, y, dx, dy])
  }
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (!wet(r, c)) continue
      if (!wet(r - 1, c)) add(c, r, 1, 0)
      if (!wet(r, c + 1)) add(c + 1, r, 0, 1)
      if (!wet(r + 1, c)) add(c + 1, r + 1, -1, 0)
      if (!wet(r, c - 1)) add(c, r + 1, 0, -1)
    }
  }

  const used = new Uint8Array(edges.length)
  const outers: { ring: Ring; area: number }[] = []
  const holes: { ring: Ring; probe: [number, number] }[] = []
  for (let first = 0; first < edges.length; first++) {
    if (used[first]) continue
    const ring: Ring = []
    let e = first
    for (;;) {
      used[e] = 1
      const [x, y, dx, dy] = edges[e]
      ring.push([x, y])
      const nx = x + dx
      const ny = y + dy
      const next = (byStart.get(key(nx, ny)) ?? []).filter((i) => !used[i] || i === first)
      if (next.length === 0) break
      // Prefer a right turn (-dy, dx), then straight on, then a left turn.
      const rank = (i: number) => {
        const [, , ex, ey] = edges[i]
        if (ex === -dy && ey === dx) return 0
        if (ex === dx && ey === dy) return 1
        return 2
      }
      e = next.reduce((best, i) => (rank(i) < rank(best) ? i : best))
      if (e === first) break
    }
    for (const loop of splitAtRepeats(ring)) {
      const simplified = dropCollinear(loop)
      const area = signedArea(simplified)
      if (area > 0) {
        outers.push({ ring: simplified, area })
      } else {
        // The wet cell on the right of the hole's first edge belongs to the polygon around the hole.
        const [x0, y0] = loop[0]
        const [x1, y1] = loop[1]
        const dx = x1 - x0
        const dy = y1 - y0
        holes.push({ ring: simplified, probe: [x0 + dx / 2 - dy / 2, y0 + dy / 2 + dx / 2] })
      }
    }
  }

  const polygons: Ring[][] = outers.map(({ ring }) => [ring])
  for (const hole of holes) {
    let owner = -1
    for (let i = 0; i < outers.length; i++) {
      if (!insideRing(outers[i].ring, hole.probe)) continue
      if (owner < 0 || outers[i].area < outers[owner].area) owner = i
    }
    if (owner >= 0) polygons[owner].push(hole.ring)
  }
  return polygons
}

/**
 * Splits a ring that passes through a vertex twice into simple loops. Right turns keep wet regions apart, so this
 * only happens to holes: two dry cells touching at a corner trace as one ring pinched there, which becomes two
 * holes touching at that point (valid, unlike a self-touching ring).
 */
function splitAtRepeats(ring: Ring): Ring[] {
  const loops: Ring[] = []
  const stack: Ring = []
  const seen = new Map<string, number>()
  for (const p of ring) {
    const k = `${p[0]},${p[1]}`
    const at = seen.get(k)
    if (at !== undefined) {
      const loop = stack.splice(at)
      for (const q of loop) seen.delete(`${q[0]},${q[1]}`)
      loops.push(loop)
    }
    seen.set(k, stack.length)
    stack.push(p)
  }
  loops.push(stack)
  return loops
}

function dropCollinear(ring: Ring): Ring {
  const n = ring.length
  return ring.filter((p, i) => {
    const a = ring[(i - 1 + n) % n]
    const b = ring[(i + 1) % n]
    return (p[0] - a[0]) * (b[1] - p[1]) !== (p[1] - a[1]) * (b[0] - p[0])
  })
}

/** Shoelace area; positive for a clockwise ring on screen (y down). */
function signedArea(ring: Ring): number {
  let sum = 0
  for (let i = 0; i < ring.length; i++) {
    const [x0, y0] = ring[i]
    const [x1, y1] = ring[(i + 1) % ring.length]
    sum += x0 * y1 - x1 * y0
  }
  return sum / 2
}

function insideRing(ring: Ring, [x, y]: [number, number]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

/**
 * Maps a grid corner to [lon, lat]: bilinear between the grid's four true corners ([lat, lon], clockwise from the
 * top-left, as GET /grids gives them). The grid is north-up in UTM, so over a few km this is exact to well under
 * a cell. Without a footprint, the axis-aligned bounds the overlays are stretched over.
 */
function cornerMapper(rows: number, cols: number, footprint: readonly [number, number][] | null, bounds: Bounds) {
  const [tl, tr, br, bl] = footprint ?? [
    [bounds.north, bounds.west],
    [bounds.north, bounds.east],
    [bounds.south, bounds.east],
    [bounds.south, bounds.west],
  ]
  return ([x, y]: [number, number]): [number, number] => {
    const u = x / cols
    const v = y / rows
    const lerp = (k: 0 | 1) => (1 - u) * (1 - v) * tl[k] + u * (1 - v) * tr[k] + u * v * br[k] + (1 - u) * v * bl[k]
    const round = (d: number) => Math.round(d * 1e7) / 1e7
    return [round(lerp(1)), round(lerp(0))]
  }
}

export interface ExtentFeatureInput {
  mask: ArrayLike<boolean | number>
  rows: number
  cols: number
  properties: Record<string, string | number | null>
}

/**
 * A GeoJSON FeatureCollection (RFC 7946: WGS84 [lon, lat], exterior rings counter-clockwise) with one MultiPolygon
 * feature per extent. Row 0 is the grid's north edge, so the traced rings wind on the map as they do on screen:
 * outer rings clockwise, holes counter-clockwise. Each is reversed to the right-hand rule.
 */
export function extentsToGeoJson(
  extents: readonly ExtentFeatureInput[],
  footprint: readonly [number, number][] | null,
  bounds: Bounds,
): object {
  return {
    type: 'FeatureCollection',
    features: extents.map(({ mask, rows, cols, properties }) => {
      const toLonLat = cornerMapper(rows, cols, footprint, bounds)
      const polygons = traceExtent(mask, rows, cols).map((rings) =>
        rings.map((ring) => {
          const coords = ring.map(toLonLat).reverse()
          return [...coords, coords[0]]
        }),
      )
      return { type: 'Feature', properties, geometry: { type: 'MultiPolygon', coordinates: polygons } }
    }),
  }
}
