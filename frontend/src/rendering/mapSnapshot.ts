/** A legend drawn under a pane in the exported image, mirroring the on-map one. */
export interface SnapshotLegend {
  title: string
  items: { color: string; label: string }[]
  note?: string
}

export interface SnapshotPane {
  /** The pane's Leaflet container (.leaflet-container). */
  container: HTMLElement
  title: string
  legend: SnapshotLegend | null
  /** Opacity the legend swatches are drawn at, matching the overlay's. */
  swatchOpacity: number
}

export interface Snapshot {
  blob: Blob
  /** Tiles left out because their server does not allow cross-origin reads (they would taint the canvas). */
  missingTiles: number
}

const SCALE = 2
const PAD = 14
const FOOTER_TEXT = '#1d2427'
const FOOTER_MUTED = '#5b6866'
const FONT = "'Instrument Sans Variable', ui-sans-serif, system-ui, sans-serif"
const DISPLAY_FONT = "'Instrument Sans Variable', ui-sans-serif, system-ui, sans-serif"

function loadImage(src: string, crossOrigin: boolean): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const image = new Image()
    if (crossOrigin) image.crossOrigin = 'anonymous'
    image.onload = () => resolve(image)
    image.onerror = () => resolve(null)
    image.src = src
  })
}

/** The element's opacity times every ancestor's, up to the map container. */
function effectiveOpacity(element: Element, container: Element): number {
  let opacity = 1
  for (let node: Element | null = element; node && node !== container; node = node.parentElement) {
    opacity *= Number(getComputedStyle(node).opacity)
  }
  return opacity
}

/** The Leaflet pane a layer element sits in, and the pane's stacking order. */
function paneOf(element: Element, container: Element): { z: number; blend: string } {
  let pane: Element | null = element.closest('.leaflet-pane')
  // Tiles sit in a tile pane inside the map pane; the outermost pane below the map pane decides the stacking.
  while (pane?.parentElement && pane.parentElement !== container && !pane.parentElement.classList.contains('leaflet-map-pane')) {
    pane = pane.parentElement.closest('.leaflet-pane')
  }
  if (!pane) return { z: 0, blend: 'normal' }
  const style = getComputedStyle(pane)
  return { z: Number(style.zIndex) || 0, blend: style.mixBlendMode || 'normal' }
}

async function svgImage(svg: SVGSVGElement): Promise<HTMLImageElement | null> {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  // Leaflet positions the renderer with a CSS transform; its on-screen box (where it is drawn) already includes it,
  // and inside a standalone SVG image it would shift the content a second time.
  clone.removeAttribute('style')
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' }))
  try {
    return await loadImage(url, false)
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** Draws one Leaflet map, as it is on screen, into `ctx` at the current origin. Returns how many tiles it skipped. */
async function drawPane(ctx: CanvasRenderingContext2D, container: HTMLElement): Promise<number> {
  const origin = container.getBoundingClientRect()
  const layers = Array.from(container.querySelectorAll<HTMLImageElement | SVGSVGElement>('.leaflet-map-pane img, .leaflet-map-pane svg'))
    .map((element, order) => ({ element, order, ...paneOf(element, container) }))
    .filter(({ element }) => !(element instanceof HTMLImageElement) || element.complete)
    .sort((a, b) => a.z - b.z || a.order - b.order)

  let missing = 0
  ctx.save()
  ctx.beginPath()
  ctx.rect(0, 0, origin.width, origin.height)
  ctx.clip()
  ctx.fillStyle = '#dddddd'
  ctx.fillRect(0, 0, origin.width, origin.height)
  for (const { element, blend } of layers) {
    const opacity = effectiveOpacity(element, container)
    if (opacity <= 0) continue
    const box = element.getBoundingClientRect()
    if (box.width === 0 || box.height === 0) continue
    let image: HTMLImageElement | null
    if (element instanceof HTMLImageElement) {
      // Data URLs (the flood overlay) are same-origin; tiles are re-requested with CORS so the canvas stays exportable.
      const remote = !element.src.startsWith('data:')
      image = await loadImage(element.src, remote)
      if (!image && remote) missing++
    } else {
      image = await svgImage(element)
    }
    if (!image) continue
    ctx.globalAlpha = opacity
    ctx.globalCompositeOperation = blend === 'multiply' ? 'multiply' : 'source-over'
    ctx.imageSmoothingEnabled = getComputedStyle(element).imageRendering !== 'pixelated'
    ctx.drawImage(image, box.left - origin.left, box.top - origin.top, box.width, box.height)
  }
  ctx.restore()
  return missing
}

function legendHeight(legend: SnapshotLegend | null): number {
  if (!legend) return 0
  return 20 + legend.items.length * 17 + (legend.note ? 16 : 0)
}

function drawLegend(ctx: CanvasRenderingContext2D, legend: SnapshotLegend, swatchOpacity: number, width: number) {
  ctx.fillStyle = FOOTER_TEXT
  ctx.font = `600 13px ${DISPLAY_FONT}`
  ctx.textBaseline = 'top'
  ctx.fillText(legend.title, 0, 0)
  ctx.font = `12px ${FONT}`
  legend.items.forEach(({ color, label }, i) => {
    const y = 20 + i * 17
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, y, 22, 13)
    ctx.globalAlpha = swatchOpacity
    ctx.fillStyle = color
    ctx.fillRect(1, y + 1, 20, 11)
    ctx.globalAlpha = 1
    ctx.strokeStyle = '#c7cfcd'
    ctx.strokeRect(0.5, y + 0.5, 21, 12)
    ctx.fillStyle = FOOTER_TEXT
    ctx.fillText(label, 30, y)
  })
  if (legend.note) {
    ctx.fillStyle = FOOTER_MUTED
    ctx.fillText(legend.note, 0, 20 + legend.items.length * 17 + 2, width)
  }
}

/**
 * The map as on screen - basemap, shaded relief, flood overlay, grid outline - with each pane's title and legend
 * and the tile attribution drawn under it, as a PNG for a document. Panes sit side by side, as in Compare.
 */
export async function snapshotMap(panes: readonly SnapshotPane[], caption: string): Promise<Snapshot> {
  const sizes = panes.map(({ container }) => container.getBoundingClientRect())
  const gap = 4
  const width = sizes.reduce((sum, { width }) => sum + width, 0) + gap * (panes.length - 1)
  const mapHeight = Math.max(...sizes.map(({ height }) => height))
  const attribution = Array.from(
    new Set(panes.map(({ container }) => container.querySelector('.leaflet-control-attribution')?.textContent?.trim() ?? '')),
  )
    .filter(Boolean)
    .join(' | ')
  const titleHeight = 26
  const legendBlock = Math.max(...panes.map(({ legend }) => legendHeight(legend)))
  const footer = titleHeight + legendBlock + PAD + 18 + 16 + PAD
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(width * SCALE)
  canvas.height = Math.round((mapHeight + footer) * SCALE)
  const ctx = canvas.getContext('2d')!
  ctx.scale(SCALE, SCALE)
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, width, mapHeight + footer)

  let missingTiles = 0
  let x = 0
  for (const [i, pane] of panes.entries()) {
    const { width: paneWidth } = sizes[i]
    ctx.save()
    ctx.translate(x, 0)
    missingTiles += await drawPane(ctx, pane.container)
    ctx.translate(PAD, mapHeight + PAD)
    ctx.fillStyle = FOOTER_TEXT
    ctx.font = `600 15px ${DISPLAY_FONT}`
    ctx.textBaseline = 'top'
    ctx.fillText(pane.title, 0, 0, paneWidth - 2 * PAD)
    if (pane.legend) {
      ctx.translate(0, titleHeight)
      drawLegend(ctx, pane.legend, pane.swatchOpacity, paneWidth - 2 * PAD)
    }
    ctx.restore()
    x += paneWidth + gap
  }

  ctx.textBaseline = 'top'
  ctx.font = `12px ${FONT}`
  ctx.fillStyle = FOOTER_TEXT
  const footerTop = mapHeight + PAD + titleHeight + legendBlock + PAD
  ctx.fillText(caption, PAD, footerTop, width - 2 * PAD)
  ctx.fillStyle = FOOTER_MUTED
  ctx.font = `11px ${FONT}`
  ctx.fillText(attribution, PAD, footerTop + 18, width - 2 * PAD)

  const blob = await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('The map image could not be encoded'))), 'image/png'),
  )
  return { blob, missingTiles }
}

/** Saves a blob as a file through a temporary download link. */
export function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
