export type Rgba = [number, number, number, number]

export function hexToRgba(hex: string, alpha = 255): Rgba {
  return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16), alpha]
}

/**
 * Rasterizes a row-major grid to a data URL, one pixel per cell (cell i is pixel i, since both the grid and
 * ImageData are row-major). A null color leaves the cell transparent.
 */
export function paint(rows: number, cols: number, colorOf: (cell: number) => Rgba | null): string {
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
