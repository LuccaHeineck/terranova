import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import L from 'leaflet'
import type { Bounds, LatLon } from '../types/simulation'
import { OVERLAY_OPACITY } from '../rendering/depthToImage'

interface MapPaneProps {
  bounds: Bounds | null
  /** The flood overlay image; null shows the basemap only. */
  imageUrl: string | null
  /** Engine name drawn over the pane, for the two-pane Compare view. */
  label?: string
  /** Key for this pane's overlay, drawn in its bottom-left corner. */
  legend?: ReactNode
  /** Fit the view to `bounds` on mount. Off for a pane whose view is copied from another map instead. */
  fitOnMount?: boolean
  /** Called with the Leaflet map once created, and with null just before it is removed. */
  onMapReady?: (map: L.Map | null) => void
  /** A grid's true outline ([lat, lon] corners), drawn dashed while a seed can be placed; null hides it. */
  footprint?: readonly [number, number][] | null
  /** The seed marker; null draws none. */
  seedMarker?: LatLon | null
  /** Map clicks while a seed can be placed; null leaves clicks to plain panning. */
  onMapClick?: ((point: LatLon) => void) | null
}

// Above the flood overlay (overlayPane, z 400) and below Leaflet's markers/popups, so the seed marker and the
// grid outline are never hidden under a frame that arrives after them.
const SEED_PANE = 'seed'
const SEED_PANE_Z_INDEX = '450'

// Lajeado/Estrela, RS - a reasonable default view before a run's real bounds arrive.
const DEFAULT_CENTER: [number, number] = [-29.48, -51.96]
const DEFAULT_ZOOM = 13

function toLatLngBounds(bounds: Bounds): L.LatLngBounds {
  return L.latLngBounds([bounds.south, bounds.west], [bounds.north, bounds.east])
}

/** One Leaflet map: OSM basemap plus a single flood overlay image stretched over the grid's bounds. */
export function MapPane({
  bounds,
  imageUrl,
  label,
  legend,
  fitOnMount = true,
  onMapReady,
  footprint = null,
  seedMarker = null,
  onMapClick = null,
}: MapPaneProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const overlayRef = useRef<L.ImageOverlay | null>(null)
  const outlineRef = useRef<L.Polygon | null>(null)
  const markerRef = useRef<L.CircleMarker | null>(null)
  const onMapClickRef = useRef(onMapClick)
  useEffect(() => {
    onMapClickRef.current = onMapClick
  }, [onMapClick])
  // Bounds the view was last fitted to; seeding it with the mount-time bounds skips that first fit.
  const fittedBoundsRef = useRef<Bounds | null>(fitOnMount ? null : bounds)
  const onMapReadyRef = useRef(onMapReady)
  useEffect(() => {
    onMapReadyRef.current = onMapReady
  }, [onMapReady])

  useEffect(() => {
    const container = containerRef.current
    if (!container || mapRef.current) return

    const map = L.map(container).setView(DEFAULT_CENTER, DEFAULT_ZOOM)
    // Standard OSM: streets and place names stay readable under the overlay. The depth ramp
    // (rendering/depthToImage.ts) is designed against its light tiles, including its blue water.
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map)
    map.createPane(SEED_PANE).style.zIndex = SEED_PANE_Z_INDEX
    map.on('click', (event: L.LeafletMouseEvent) => {
      onMapClickRef.current?.({ lat: event.latlng.lat, lon: event.latlng.lng })
    })
    mapRef.current = map
    // The pane is resized by layout changes Leaflet can't see (the Compare view splitting the map area),
    // which would otherwise leave unrendered gray strips.
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(container)
    onMapReadyRef.current?.(map)

    return () => {
      observer.disconnect()
      onMapReadyRef.current?.(null)
      map.remove()
      mapRef.current = null
      overlayRef.current = null
      outlineRef.current = null
      markerRef.current = null
    }
  }, [])

  // A crosshair says the map takes a click; Leaflet's own grab cursor otherwise.
  useEffect(() => {
    const container = containerRef.current
    if (container) container.style.cursor = onMapClick ? 'crosshair' : ''
  }, [onMapClick])

  useEffect(() => {
    const map = mapRef.current
    outlineRef.current?.remove()
    outlineRef.current = null
    if (!map || !footprint) return
    outlineRef.current = L.polygon(footprint.map(([lat, lon]): L.LatLngTuple => [lat, lon]), {
      pane: SEED_PANE,
      color: '#111827',
      weight: 1.5,
      dashArray: '6 4',
      fill: false,
      interactive: false,
    }).addTo(map)
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
  }, [bounds])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (!imageUrl || !bounds) {
      overlayRef.current?.remove()
      overlayRef.current = null
      return
    }
    if (!overlayRef.current) {
      // Pixelated: each image pixel is one grid cell, and the browser's default smoothing would
      // blend neighboring depth bands into colors that belong to neither.
      overlayRef.current = L.imageOverlay(imageUrl, toLatLngBounds(bounds), {
        opacity: OVERLAY_OPACITY,
        className: '[image-rendering:pixelated]',
      }).addTo(map)
    } else {
      overlayRef.current.setBounds(toLatLngBounds(bounds))
      overlayRef.current.setUrl(imageUrl)
    }
  }, [imageUrl, bounds])

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      {label && (
        <div className="pointer-events-none absolute top-3 left-14 z-1000 rounded bg-basalt/95 px-2.5 py-1 font-display text-[13px] font-semibold text-mist shadow-lg tabular-nums">
          {label}
        </div>
      )}
      {legend && <div className="absolute bottom-6 left-3 z-1000">{legend}</div>}
    </div>
  )
}
