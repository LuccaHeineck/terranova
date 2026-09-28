import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import type { Bounds } from '../types/simulation'
import type { Engine, ResultLayer, ResultLayers } from '../hooks/useSimulationRun'
import { depthToImageDataUrl } from '../rendering/depthToImage'
import { DepthLegend } from './DepthLegend'
import { MapPane } from './MapPane'

type MapView = Engine | 'compare'

interface FloodMapProps {
  bounds: Bounds | null
  layers: ResultLayers
  activeEngine: Engine
  runCount: number
}

const VIEW_LABEL: Record<MapView, string> = {
  temporal: 'Temporal',
  fast: 'Fast',
  compare: 'Compare',
}

/** The view actually drawn: the selected one if its data exists, else whichever layer does. */
function resolveView(view: MapView, layers: ResultLayers): MapView | null {
  const has = (engine: Engine) => Boolean(layers[engine]?.frame)
  if (view === 'compare') return has('temporal') && has('fast') ? 'compare' : resolveView('temporal', layers)
  if (has(view)) return view
  const other: Engine = view === 'fast' ? 'temporal' : 'fast'
  return has(other) ? other : null
}

function paneLabel(engine: Engine, layer: ResultLayer | null): string {
  if (engine === 'fast') return 'Fast: steady peak'
  const hours = (layer?.frame?.elapsed_time ?? 0) / 3600
  return `Temporal CA: t = ${hours.toFixed(1)} h`
}

/** Rasterized overlay for one engine's latest frame, recomputed only when that frame changes. */
function useOverlayUrl(layer: ResultLayer | null, needed: boolean): string | null {
  const frame = layer?.frame
  return useMemo(() => (needed && frame ? depthToImageDataUrl(frame.depth) : null), [needed, frame])
}

/**
 * Keeps two maps on the same center and zoom. Returns the callbacks each pane reports its map through.
 * setView fires the follower's own move event synchronously; the flag stops that echoing back.
 */
function useSyncedMaps(bounds: Bounds | null) {
  const boundsRef = useRef(bounds)
  useEffect(() => {
    boundsRef.current = bounds
  }, [bounds])
  const mapsRef = useRef<{ primary: L.Map | null; secondary: L.Map | null }>({ primary: null, secondary: null })
  const unlinkRef = useRef<(() => void) | null>(null)

  const link = useCallback(() => {
    unlinkRef.current?.()
    unlinkRef.current = null
    const { primary, secondary } = mapsRef.current
    if (!primary || !secondary) return
    // Compare just opened, so the primary pane is now half as wide: refit the whole grid into it
    // (the ResizeObserver's own invalidateSize would only come after this), then copy that view.
    primary.invalidateSize({ pan: false })
    const b = boundsRef.current
    if (b) primary.fitBounds(L.latLngBounds([b.south, b.west], [b.north, b.east]), { animate: false })
    secondary.setView(primary.getCenter(), primary.getZoom(), { animate: false })
    let syncing = false
    const follow = (from: L.Map, to: L.Map) => () => {
      if (syncing) return
      syncing = true
      to.setView(from.getCenter(), from.getZoom(), { animate: false })
      syncing = false
    }
    const primaryMoved = follow(primary, secondary)
    const secondaryMoved = follow(secondary, primary)
    primary.on('move', primaryMoved)
    secondary.on('move', secondaryMoved)
    unlinkRef.current = () => {
      primary.off('move', primaryMoved)
      secondary.off('move', secondaryMoved)
    }
  }, [])

  const onPrimaryReady = useCallback((map: L.Map | null) => {
    mapsRef.current.primary = map
    link()
  }, [link])
  const onSecondaryReady = useCallback((map: L.Map | null) => {
    mapsRef.current.secondary = map
    link()
  }, [link])

  return { onPrimaryReady, onSecondaryReady }
}

export function FloodMap({ bounds, layers, activeEngine, runCount }: FloodMapProps) {
  // A manual view choice only lasts for the run it was made in; a new run shows the engine just run.
  const [choice, setChoice] = useState<{ view: MapView; runCount: number } | null>(null)
  const view: MapView = choice && choice.runCount === runCount ? choice.view : activeEngine
  const shown = resolveView(view, layers)
  const compare = shown === 'compare'

  const temporalUrl = useOverlayUrl(layers.temporal, shown === 'temporal' || compare)
  const fastUrl = useOverlayUrl(layers.fast, shown === 'fast' || compare)
  const { onPrimaryReady, onSecondaryReady } = useSyncedMaps(bounds)

  const available: Record<MapView, boolean> = {
    temporal: Boolean(layers.temporal?.frame),
    fast: Boolean(layers.fast?.frame),
    compare: Boolean(layers.temporal?.frame && layers.fast?.frame),
  }

  return (
    <div className="relative h-full w-full">
      {/* The primary pane stays mounted across view changes; Compare adds the fast pane beside it. */}
      <div className={`grid h-full w-full ${compare ? 'grid-cols-2 gap-0.5 bg-gray-400' : 'grid-cols-1'}`}>
        <MapPane
          bounds={bounds}
          imageUrl={shown === 'fast' ? fastUrl : temporalUrl}
          label={compare ? paneLabel('temporal', layers.temporal) : undefined}
          onMapReady={onPrimaryReady}
        />
        {compare && (
          <MapPane
            bounds={bounds}
            imageUrl={fastUrl}
            label={paneLabel('fast', layers.fast)}
            fitOnMount={false}
            onMapReady={onSecondaryReady}
          />
        )}
      </div>

      {(available.temporal || available.fast) && (
        <div className="absolute top-3 right-3 z-1000 flex flex-col gap-1.5 rounded-md bg-white/95 p-2 text-xs shadow-md">
          <div className="flex gap-1" role="group" aria-label="Map view">
            {(Object.keys(VIEW_LABEL) as MapView[]).map((v) => (
              <button
                key={v}
                type="button"
                disabled={!available[v]}
                onClick={() => setChoice({ view: v, runCount })}
                aria-pressed={shown === v}
                className={`rounded px-2 py-1 disabled:opacity-40 ${
                  shown === v ? 'bg-gray-900 text-white' : 'bg-gray-100 text-gray-800 hover:bg-gray-200'
                }`}
              >
                {VIEW_LABEL[v]}
              </button>
            ))}
          </div>
          {shown && !compare && (
            <div className="text-gray-700">{shown === 'fast' ? 'Fast mode: steady peak depth' : 'Temporal CA depth'}</div>
          )}
          {compare && <div className="text-gray-700">Pan or zoom either map; both follow.</div>}
        </div>
      )}

      {shown && (
        <div className="absolute bottom-6 left-3 z-1000">
          <DepthLegend />
        </div>
      )}
    </div>
  )
}
