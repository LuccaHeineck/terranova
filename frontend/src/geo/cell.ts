import type { Bounds, LatLon } from '../types/simulation'

export interface Cell {
  row: number
  col: number
}

/** A cell's [[south, west], [north, east]] corners. */
export type CellRect = [[number, number], [number, number]]

/**
 * The cell under a point, as the map draws it: every overlay (depth, observed extent, model inputs) is one image
 * stretched over the grid's axis-aligned `bounds`, so this is the pixel the user clicked and its values match the
 * colors on screen. The grid is north-up in UTM and so slightly rotated in lat/lon; its true cell under the point
 * (the backend's ingestion/dem.py `lonlat_to_cell`) can be a cell or two away near the edges - the same
 * approximation the overlays themselves make. Null outside the bounds.
 */
export function cellAt(bounds: Bounds, rows: number, cols: number, { lat, lon }: LatLon): Cell | null {
  const col = Math.floor(((lon - bounds.west) / (bounds.east - bounds.west)) * cols)
  const row = Math.floor(((bounds.north - lat) / (bounds.north - bounds.south)) * rows)
  return row >= 0 && row < rows && col >= 0 && col < cols ? { row, col } : null
}

/** Where `cellAt` puts a cell on the map: its rectangle within the stretched overlay. */
export function cellRect(bounds: Bounds, rows: number, cols: number, { row, col }: Cell): CellRect {
  const height = (bounds.north - bounds.south) / rows
  const width = (bounds.east - bounds.west) / cols
  const north = bounds.north - row * height
  const west = bounds.west + col * width
  return [
    [north - height, west],
    [north, west + width],
  ]
}
