import { useEffect, useRef } from 'react'
import L from 'leaflet'
import type { Bounds, SimulationFrame } from '../types/simulation'
import { computeMaxDepth, depthToImageDataUrl } from '../rendering/depthToImage'

interface FloodMapProps {
  bounds: Bounds | null
  frame: SimulationFrame | null
}

// Lajeado/Estrela, RS - a reasonable default view before a run's real bounds arrive.
const DEFAULT_CENTER: [number, number] = [-29.48, -51.96]
const DEFAULT_ZOOM = 13

export function FloodMap({ bounds, frame }: FloodMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const overlayRef = useRef<L.ImageOverlay | null>(null)
  const maxDepthRef = useRef(0)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = L.map(containerRef.current).setView(DEFAULT_CENTER, DEFAULT_ZOOM)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)
    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // A new run's bounds arrived: clear any stale overlay and pan/zoom to the real grid extent.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !bounds) return

    overlayRef.current?.remove()
    overlayRef.current = null
    maxDepthRef.current = 0
    map.fitBounds(L.latLngBounds([bounds.south, bounds.west], [bounds.north, bounds.east]))
  }, [bounds])

  // A new frame arrived: rasterize it and push it into the overlay.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !bounds || !frame) return

    const llBounds = L.latLngBounds([bounds.south, bounds.west], [bounds.north, bounds.east])
    maxDepthRef.current = Math.max(maxDepthRef.current, computeMaxDepth(frame.depth))
    const url = depthToImageDataUrl(frame.depth, maxDepthRef.current)

    if (!overlayRef.current) {
      overlayRef.current = L.imageOverlay(url, llBounds, { opacity: 0.75 }).addTo(map)
    } else {
      overlayRef.current.setUrl(url)
    }
  }, [frame, bounds])

  return <div ref={containerRef} className="h-full w-full" />
}
