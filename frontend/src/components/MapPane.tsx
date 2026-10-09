import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import L from 'leaflet'
import type { Bounds, LatLon } from '../types/simulation'
import { OVERLAY_OPACITY } from '../rendering/depthToImage'
import type { CellRect } from '../geo/cell'
import { HILLSHADE } from '../geo/basemaps'
import type { Basemap, TileSpec } from '../geo/basemaps'

interface MapPaneProps {
  bounds: Bounds | null
  /** The background tiles (base, optional hillshade and labels); switching it swaps them in place. */
  basemap: Basemap
  /** The flood overlay image; null shows the basemap only. */
  imageUrl: string | null
  /** Engine name drawn over the pane (above its legend), for the two-pane Compare view. */
  label?: string
  /** Key for this pane's overlay, drawn in its bottom-left corner. */
  legend?: ReactNode
  /** Fit the view to `bounds` on mount. Off for a pane whose view is copied from another map instead. */
  fitOnMount?: boolean
  /** Called with the Leaflet map once created, and with null just before it is removed. */
  onMapReady?: (map: L.Map | null) => void
  /** A grid's true outline ([lat, lon] corners), drawn dashed to show the simulated area; null hides it. */
  footprint?: readonly [number, number][] | null
  /** The seed marker; null draws none. */
  seedMarker?: LatLon | null
  /** Map clicks (placing a seed, inspecting a cell); null leaves clicks to plain panning. */
  onMapClick?: ((point: LatLon) => void) | null
  /** Show a crosshair cursor: a click places something (the seed), not just inspects. */
  crosshair?: boolean
  /** A model-input layer (terrain or roughness) drawn under the flood overlay; null draws none. */
  inputImage?: { url: string; bounds: Bounds; opacity: number } | null
  /** The inspected cell and its neighbors, outlined; null outlines nothing. */
  highlight?: { cell: CellRect; neighbors: CellRect[] } | null
  /** Opacity of the flood overlay. */
  opacity?: number
}

// Above the flood overlay (overlayPane, z 400) and below Leaflet's markers/popups, so the seed marker and the
// grid outline are never hidden under a frame that arrives after them.
const SEED_PANE = 'seed'
const SEED_PANE_Z_INDEX = '450'

// Between the basemap (tilePane, z 200) and the flood overlay (overlayPane, z 400): the hillshade multiplies
// into the base tiles only, never into the depth ramp drawn above it. The floodplain itself is near-flat, so
// it shades almost white and barely changes there.
const RELIEF_PANE = 'relief'
const RELIEF_PANE_Z_INDEX = '250'

// Between the relief (250) and the flood overlay (400): a model-input layer covers the basemap, and the flood
// is drawn over it, so where the water sits and what it sits on read together.
const INPUTS_PANE = 'inputs'
const INPUTS_PANE_Z_INDEX = '300'

// The flood overlay's own pane, where overlayPane sits (400). The overlay opacity is the pane's, not each image's:
// during a crossfade the two frames add up inside it (plus-lighter, see .flood-frame) and the sum is then dimmed
// once, so a cell wet in both frames keeps its strength instead of dipping halfway through.
const FLOOD_PANE = 'flood'
const FLOOD_PANE_Z_INDEX = '400'

// One frame fades into the next over this long, or less when frames come faster (0.8 of the gap since the last
// one), so a fade always finishes before the next starts. Shorter than MIN_FADE_MS, it just swaps.
const FADE_MS = 220
const MIN_FADE_MS = 60

// Each image pixel is one grid cell, and the browser's default smoothing would blend neighboring depth bands into
// colors that belong to neither.
const FLOOD_FRAME_CLASS = '[image-rendering:pixelated] flood-frame'

/** The next flood image, fading in over the current one once it has loaded. */
interface IncomingFrame {
  overlay: L.ImageOverlay
  durationMs: number
  /** Loaded and fading: a newer frame finishes this fade first instead of replacing the image. */
  fading: boolean
  /** The pending animation frame of the fade. */
  raf: number | null
}

// Place names above the flood overlay, so they stay readable through it, and below the seed pane.
const LABELS_PANE = 'labels'
const LABELS_PANE_Z_INDEX = '420'

function tileLayer(spec: TileSpec, options: L.TileLayerOptions = {}): L.TileLayer {
  return L.tileLayer(spec.url, {
    attribution: spec.attribution,
    maxZoom: 19,
    maxNativeZoom: spec.maxNativeZoom,
    ...(spec.subdomains ? { subdomains: spec.subdomains } : {}),
    ...options,
  })
}

// Lajeado/Estrela, RS - a reasonable default view before a run's real bounds arrive.
const DEFAULT_CENTER: [number, number] = [-29.48, -51.96]
const DEFAULT_ZOOM = 13

function toLatLngBounds(bounds: Bounds): L.LatLngBounds {
  return L.latLngBounds([bounds.south, bounds.west], [bounds.north, bounds.east])
}

/** One Leaflet map: a basemap (often with shaded relief), plus a single flood overlay image stretched over the grid's bounds. */
export function MapPane({
  bounds,
  basemap,
  imageUrl,
  label,
  legend,
  fitOnMount = true,
  onMapReady,
  footprint = null,
  seedMarker = null,
  onMapClick = null,
  crosshair = false,
  inputImage = null,
  highlight = null,
  opacity = OVERLAY_OPACITY,
}: MapPaneProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  // The flood frame on screen, and the one fading in over it.
  const overlayRef = useRef<L.ImageOverlay | null>(null)
  const incomingRef = useRef<IncomingFrame | null>(null)
  const lastFrameAtRef = useRef(0)
  const inputOverlayRef = useRef<L.ImageOverlay | null>(null)
  const highlightRef = useRef<L.LayerGroup | null>(null)
  const outlineRef = useRef<L.LayerGroup | null>(null)
  const markerRef = useRef<L.CircleMarker | null>(null)
  const basemapLayersRef = useRef<L.TileLayer[]>([])
  const onMapClickRef = useRef(onMapClick)
  useEffect(() => {
    onMapClickRef.current = onMapClick
  }, [onMapClick])
  // Bounds the view was last fitted to; seeding it with the mount-time bounds skips that first fit.
  const fittedBoundsRef = useRef<Bounds | null>(fitOnMount ? null : bounds)
  // The view is still the automatic fit to those bounds, untouched by the user: refit it when the pane resizes.
  const autoFitRef = useRef(false)
  const onMapReadyRef = useRef(onMapReady)
  useEffect(() => {
    onMapReadyRef.current = onMapReady
  }, [onMapReady])

  useEffect(() => {
    const container = containerRef.current
    if (!container || mapRef.current) return

    // Zoom sits bottom right, out of the way of the pane label and the view switcher along the top.
    const map = L.map(container, { zoomControl: false }).setView(DEFAULT_CENTER, DEFAULT_ZOOM)
    L.control.zoom({ position: 'bottomright' }).addTo(map)
    const reliefPane = map.createPane(RELIEF_PANE)
    reliefPane.style.zIndex = RELIEF_PANE_Z_INDEX
    reliefPane.style.mixBlendMode = 'multiply'
    reliefPane.style.pointerEvents = 'none'
    const labelsPane = map.createPane(LABELS_PANE)
    labelsPane.style.zIndex = LABELS_PANE_Z_INDEX
    labelsPane.style.pointerEvents = 'none'
    const inputsPane = map.createPane(INPUTS_PANE)
    inputsPane.style.zIndex = INPUTS_PANE_Z_INDEX
    inputsPane.style.pointerEvents = 'none'
    const floodPane = map.createPane(FLOOD_PANE)
    floodPane.style.zIndex = FLOOD_PANE_Z_INDEX
    floodPane.style.isolation = 'isolate'
    floodPane.style.pointerEvents = 'none'
    map.createPane(SEED_PANE).style.zIndex = SEED_PANE_Z_INDEX
    map.on('click', (event: L.LeafletMouseEvent) => {
      onMapClickRef.current?.({ lat: event.latlng.lat, lon: event.latlng.lng })
    })
    mapRef.current = map
    // The pane is resized by layout changes Leaflet can't see (the Compare view splitting the map area, the
    // timeline appearing under it), which would otherwise leave unrendered gray strips. A view still as it was
    // fitted is fitted again, or the grid would spill past a pane that shrank after the fit.
    const observer = new ResizeObserver(() => {
      map.invalidateSize()
      const fitted = fittedBoundsRef.current
      if (autoFitRef.current && fitted) map.fitBounds(toLatLngBounds(fitted), { animate: false })
    })
    observer.observe(container)
    // Any pan, zoom or click of the user's own ends that: the view is theirs from then on.
    const userTookOver = () => {
      autoFitRef.current = false
    }
    for (const type of ['pointerdown', 'wheel', 'keydown'] as const) container.addEventListener(type, userTookOver)
    onMapReadyRef.current?.(map)

    return () => {
      observer.disconnect()
      for (const type of ['pointerdown', 'wheel', 'keydown'] as const) container.removeEventListener(type, userTookOver)
      onMapReadyRef.current?.(null)
      map.remove()
      mapRef.current = null
      if (incomingRef.current?.raf) cancelAnimationFrame(incomingRef.current.raf)
      incomingRef.current = null
      overlayRef.current = null
      inputOverlayRef.current = null
      highlightRef.current = null
      outlineRef.current = null
      markerRef.current = null
      basemapLayersRef.current = []
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    for (const layer of basemapLayersRef.current) layer.remove()
    const layers = [tileLayer(basemap.base)]
    if (basemap.relief) layers.push(tileLayer(HILLSHADE, { pane: RELIEF_PANE, opacity: basemap.relief.opacity }))
    if (basemap.labels) layers.push(tileLayer(basemap.labels, { pane: LABELS_PANE }))
    for (const layer of layers) layer.addTo(map)
    basemapLayersRef.current = layers
  }, [basemap])

  // A crosshair says a click places the seed; Leaflet's own grab cursor otherwise (a click there only inspects).
  useEffect(() => {
    const container = containerRef.current
    if (container) container.style.cursor = crosshair ? 'crosshair' : ''
  }, [crosshair])

  useEffect(() => {
    const map = mapRef.current
    highlightRef.current?.remove()
    highlightRef.current = null
    if (!map || !highlight) return
    const style = { pane: SEED_PANE, fill: false, interactive: false }
    // The neighbors faint, the cell itself strong, each over a pale halo like the grid outline.
    highlightRef.current = L.layerGroup([
      ...highlight.neighbors.map((rect) => L.rectangle(rect, { ...style, color: '#ffffff', weight: 1, opacity: 0.9 })),
      ...highlight.neighbors.map((rect) => L.rectangle(rect, { ...style, color: '#111827', weight: 1, dashArray: '2 2' })),
      L.rectangle(highlight.cell, { ...style, color: '#ffffff', weight: 4, opacity: 0.85 }),
      L.rectangle(highlight.cell, { ...style, color: '#e9c23a', weight: 2 }),
    ]).addTo(map)
  }, [highlight])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (!inputImage) {
      inputOverlayRef.current?.remove()
      inputOverlayRef.current = null
      return
    }
    const latLngBounds = toLatLngBounds(inputImage.bounds)
    if (!inputOverlayRef.current) {
      inputOverlayRef.current = L.imageOverlay(inputImage.url, latLngBounds, {
        pane: INPUTS_PANE,
        opacity: inputImage.opacity,
        className: '[image-rendering:pixelated]',
      }).addTo(map)
    } else {
      inputOverlayRef.current.setOpacity(inputImage.opacity)
      inputOverlayRef.current.setBounds(latLngBounds)
      inputOverlayRef.current.setUrl(inputImage.url)
    }
  }, [inputImage])

  useEffect(() => {
    const map = mapRef.current
    outlineRef.current?.remove()
    outlineRef.current = null
    if (!map || !footprint) return
    const corners = footprint.map(([lat, lon]): L.LatLngTuple => [lat, lon])
    const style = { pane: SEED_PANE, fill: false, interactive: false }
    // A dark dash over a pale halo, so the outline reads on light tiles and satellite imagery alike.
    outlineRef.current = L.layerGroup([
      L.polygon(corners, { ...style, color: '#ffffff', weight: 4, opacity: 0.7 }),
      L.polygon(corners, { ...style, color: '#111827', weight: 1.5, dashArray: '6 4' }),
    ]).addTo(map)
  }, [footprint])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (!seedMarker) {
      markerRef.current?.remove()
      markerRef.current = null
      return
    }
    const latLng: L.LatLngTuple = [seedMarker.lat, seedMarker.lon]
    if (markerRef.current) {
      markerRef.current.setLatLng(latLng)
    } else {
      // Rose with a white ring: distinct from both the blue depth ramp and the fast pane's burnt orange.
      markerRef.current = L.circleMarker(latLng, {
        pane: SEED_PANE,
        radius: 7,
        color: '#ffffff',
        weight: 2,
        fillColor: '#e11d48',
        fillOpacity: 1,
        interactive: false,
      }).addTo(map)
    }
  }, [seedMarker])

  // A new run's bounds arrived: pan/zoom to the real grid extent.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !bounds || bounds === fittedBoundsRef.current) return
    fittedBoundsRef.current = bounds
    map.fitBounds(toLatLngBounds(bounds))
    autoFitRef.current = true
  }, [bounds])

  useEffect(() => {
    const pane = mapRef.current?.getPane(FLOOD_PANE)
    if (pane) pane.style.opacity = String(opacity)
  }, [opacity])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    // Ends a fade at once: the incoming frame becomes the one on screen.
    const settle = () => {
      const incoming = incomingRef.current
      if (!incoming) return
      if (incoming.raf) cancelAnimationFrame(incoming.raf)
      incomingRef.current = null
      overlayRef.current?.remove()
      overlayRef.current = incoming.overlay
      incoming.overlay.setOpacity(1)
    }

    if (!imageUrl || !bounds) {
      settle()
      overlayRef.current?.remove()
      overlayRef.current = null
      return
    }
    const latLngBounds = toLatLngBounds(bounds)
    const now = performance.now()
    const sinceLast = now - lastFrameAtRef.current
    lastFrameAtRef.current = now
    const current = overlayRef.current
    if (!current) {
      overlayRef.current = L.imageOverlay(imageUrl, latLngBounds, {
        pane: FLOOD_PANE,
        className: FLOOD_FRAME_CLASS,
      }).addTo(map)
      return
    }

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const durationMs = reducedMotion ? 0 : Math.min(FADE_MS, 0.8 * sinceLast)
    // The incoming image has not loaded yet: load this newer frame in its place.
    const pending = incomingRef.current
    if (pending && !pending.fading) {
      pending.overlay.setBounds(latLngBounds)
      pending.overlay.setUrl(imageUrl)
      pending.durationMs = durationMs
      return
    }
    settle()
    const shown = overlayRef.current!
    shown.setBounds(latLngBounds)
    if (durationMs < MIN_FADE_MS) {
      shown.setUrl(imageUrl)
      return
    }

    const overlay = L.imageOverlay(imageUrl, latLngBounds, {
      pane: FLOOD_PANE,
      opacity: 0,
      className: FLOOD_FRAME_CLASS,
    }).addTo(map)
    const incoming: IncomingFrame = { overlay, durationMs, fading: false, raf: null }
    incomingRef.current = incoming
    overlay.on('load', () => {
      if (incomingRef.current !== incoming || incoming.fading) return
      incoming.fading = true
      const outgoing = overlayRef.current
      // Both opacities from one clock, each animation frame: CSS transitions on the two images can start frames
      // apart (a freshly loaded image's often starts late), and the sum would dip.
      const start = performance.now()
      const tick = (time: number) => {
        const progress = Math.min(1, Math.max(0, (time - start) / incoming.durationMs))
        if (progress >= 1) {
          settle()
          return
        }
        overlay.setOpacity(progress)
        outgoing?.setOpacity(1 - progress)
        incoming.raf = requestAnimationFrame(tick)
      }
      incoming.raf = requestAnimationFrame(tick)
    })
    // A frame that fails to decode is skipped: the one on screen stays.
    overlay.on('error', () => {
      if (incomingRef.current !== incoming) return
      incomingRef.current = null
      overlay.remove()
    })
  }, [imageUrl, bounds])

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      {/* The pane's name sits on top of its key, bottom left: the top edge belongs to the view switcher. */}
      {(label || legend) && (
        <div className="anim-fade absolute bottom-3 left-3 z-1000 flex flex-col items-start gap-2">
          {label && (
            <div className="float-card pointer-events-none rounded-lg px-2.5 py-1 text-[13px] font-semibold text-ink tabular-nums">
              {label}
            </div>
          )}
          {legend}
        </div>
      )}
    </div>
  )
}
