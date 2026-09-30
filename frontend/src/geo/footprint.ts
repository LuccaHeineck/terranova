/**
 * Whether a WGS84 point lies inside a polygon of [lat, lon] vertices (ray casting). Used against a grid's
 * footprint from GET /grids; at a few km, treating lat/lon as planar is exact to well under a cell.
 */
export function containsPoint(polygon: readonly (readonly [number, number])[], lat: number, lon: number): boolean {
  let inside = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [latI, lonI] = polygon[i]
    const [latJ, lonJ] = polygon[j]
    if (latI > lat !== latJ > lat && lon < ((lonJ - lonI) * (lat - latI)) / (latJ - latI) + lonI) {
      inside = !inside
    }
  }
  return inside
}
