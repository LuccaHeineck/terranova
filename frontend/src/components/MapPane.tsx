import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import L from 'leaflet'
import type { Bounds } from '../types/simulation'
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
}

// Lajeado/Estrela, RS - a reasonable default view before a run's real bounds arrive.
const DEFAULT_CENTER: [number, number] = [-29.48, -51.96]
const DEFAULT_ZOOM = 13

function toLatLngBounds(bounds: Bounds): L.LatLngBounds {
  return L.latLngBounds([bounds.south, bounds.west], [bounds.north, bounds.east])
}

/** One Leaflet map: OSM basemap plus a single flood overlay image stretched over the grid's bounds. */
export function MapPane({ bounds, imageUrl, label, legend, fitOnMount = true, onMapReady }: MapPaneProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const overlayRef = useRef<L.ImageOverlay | null>(null)
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
    }
  }, [])

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
        <div className="pointer-events-none absolute top-3 left-14 z-1000 rounded-md bg-white/95 px-2.5 py-1 text-xs font-medium text-gray-900 shadow-md">
          {label}
        </div>
      )}
      {legend && <div className="absolute bottom-6 left-3 z-1000">{legend}</div>}
    </div>
  )
}
