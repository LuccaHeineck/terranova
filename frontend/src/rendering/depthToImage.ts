/** Max depth across a frame. Avoids `Math.max(...depth.flat())`, which risks a stack overflow on a large grid. */
export function computeMaxDepth(depth: number[][]): number {
  let max = 0
  for (const row of depth) {
    for (const value of row) {
      if (value > max) max = value
    }
  }
  return max
}

const NO_WATER_THRESHOLD = 1e-6

/** Rasterizes a depth grid to a data URL: 0 depth is fully transparent, deeper is more opaque blue. */
export function depthToImageDataUrl(depth: number[][], maxDepth: number): string {
  const rows = depth.length
  const cols = depth[0]?.length ?? 0
  const canvas = document.createElement('canvas')
  canvas.width = cols
  canvas.height = rows
  const ctx = canvas.getContext('2d')!
  const image = ctx.createImageData(cols, rows)
  const safeMax = Math.max(maxDepth, NO_WATER_THRESHOLD)

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const d = depth[r][c]
      const i = (r * cols + c) * 4
      if (d <= NO_WATER_THRESHOLD) {
        image.data[i + 3] = 0
        continue
      }
      // High-contrast orange-red: OSM's own water tiles are already blue, so a blue
      // overlay blends into the river and becomes invisible - this ramp stays visible
      // against both the blue river and the beige terrain.
      const t = Math.min(d / safeMax, 1)
      image.data[i] = 255
      image.data[i + 1] = 120 - 80 * t
      image.data[i + 2] = 0
      image.data[i + 3] = 130 + 125 * t
    }
  }

  ctx.putImageData(image, 0, 0)
  return canvas.toDataURL()
}
