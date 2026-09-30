import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import L from 'leaflet'
import type { Bounds, LatLon } from '../types/simulation'
import type { CompactFrame, DepthGrid } from '../rendering/depthGrid'
import type { Engine, ResultLayers } from '../hooks/useSimulationRun'
import type { Timeline as TimelineState } from '../hooks/useTimeline'
import { depthToImageDataUrl, extentToImageDataUrl } from '../rendering/depthToImage'
import { DepthLegend } from './DepthLegend'
import { ExtentLegend } from './ExtentLegend'
import { MapPane } from './MapPane'
import { Timeline } from './Timeline'

type MapView = Engine | 'compare'

interface FloodMapProps {
  bounds: Bounds | null
  layers: ResultLayers
  activeEngine: Engine
  runCount: number
  replayActive: boolean
  /** Which temporal frame is shown: the timeline drives the temporal pane (never the fast one). */
  timeline: TimelineState
  /** The selected grid's outline, while the setup is a seeded pool (null otherwise). */
  footprint: [number, number][] | null
  seedMarker: LatLon | null
  /** Places the seed marker; null while clicks can't place one (not seeded pool, or a run is busy). */
  onMapClick: ((point: LatLon) => void) | null
  /** Why the last click placed nothing (outside the grid). */
  seedNotice: string | null
}

const VIEW_LABEL: Record<MapView, string> = {
  temporal: 'Temporal',
  fast: 'Fast',
  compare: 'Compare',
}

/**
 * Which views can be drawn. A single view needs its engine's frame. Compare needs both layers and at least one
 * frame: a layer without a frame yet is a run that is starting or queued (useSimulationRun drops frame-less
 * layers on Stop or error), and its pane shows the basemap until frames arrive.
 */
function availableViews(layers: ResultLayers): Record<MapView, boolean> {
  const temporal = Boolean(layers.temporal?.frame)
  const fast = Boolean(layers.fast?.frame)
  return { temporal, fast, compare: Boolean(layers.temporal && layers.fast) && (temporal || fast) }
}

/** The view actually drawn: the selected one if it can be, else whichever single view can. */
function resolveView(view: MapView, available: Record<MapView, boolean>): MapView | null {
  if (available[view]) return view
  if (view === 'compare') return resolveView('temporal', available)
  const other: Engine = view === 'fast' ? 'temporal' : 'fast'
  return available[other] ? other : null
}

function paneLabel(engine: Engine, frame: CompactFrame | null): string {
  if (!frame) return engine === 'fast' ? 'Fast: computing…' : 'Temporal CA: starting…'
  if (engine === 'fast') return 'Fast: steady peak extent'
  const hours = (frame.elapsed_time ?? 0) / 3600
  return `Temporal CA: t = ${hours.toFixed(1)} h`
}

// The temporal overlay is shaded by depth; the fast one shows extent only, since its depths are not calibrated.
const RENDER: Record<Engine, (grid: DepthGrid) => string> = {
  temporal: depthToImageDataUrl,
  fast: extentToImageDataUrl,
}

const LEGEND: Record<Engine, ReactNode> = {
  temporal: <DepthLegend />,
  fast: <ExtentLegend />,
}

/** Rasterized overlay for one engine's shown frame, recomputed only when that frame changes. */
function useOverlayUrl(engine: Engine, frame: CompactFrame | null, needed: boolean): string | null {
  return useMemo(() => (needed && frame ? RENDER[engine](frame.depth) : null), [engine, needed, frame])
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

export function FloodMap({
  bounds,
  layers,
  activeEngine,
  runCount,
  replayActive,
  timeline,
  footprint,
  seedMarker,
  onMapClick,
  seedNotice,
}: FloodMapProps) {
  const seedProps = { footprint, seedMarker, onMapClick }
  // A manual view choice only lasts for the run it was made in; a new run shows the engine just run, or
  // Compare for the May 2024 replay.
  const [choice, setChoice] = useState<{ view: MapView; runCount: number } | null>(null)
  const defaultView: MapView = replayActive ? 'compare' : activeEngine
  const view: MapView = choice && choice.runCount === runCount ? choice.view : defaultView
  const available = availableViews(layers)
  const shown = resolveView(view, available)
  const compare = shown === 'compare'

  const showsTemporal = shown === 'temporal' || compare
  // The temporal pane draws the timeline's selected frame (the newest one while following live).
  const temporalUrl = useOverlayUrl('temporal', timeline.frame, showsTemporal)
  const fastUrl = useOverlayUrl('fast', layers.fast?.frame ?? null, shown === 'fast' || compare)
  // The primary pane shows the temporal result, or the fast one when that's the only view.
  const primary: Engine = shown === 'fast' ? 'fast' : 'temporal'
  const { onPrimaryReady, onSecondaryReady } = useSyncedMaps(bounds)

  return (
    <div className="relative flex h-full w-full flex-col">
      {/* The primary pane stays mounted across view changes; Compare adds the fast pane beside it. */}
      <div className={`grid min-h-0 w-full flex-1 ${compare ? 'grid-cols-2 gap-0.5 bg-gray-400' : 'grid-cols-1'}`}>
        <MapPane
          bounds={bounds}
          imageUrl={primary === 'fast' ? fastUrl : temporalUrl}
          label={compare ? paneLabel('temporal', timeline.frame) : undefined}
          legend={shown ? LEGEND[primary] : undefined}
          onMapReady={onPrimaryReady}
          {...seedProps}
        />
        {compare && (
          <MapPane
            bounds={bounds}
            imageUrl={fastUrl}
            label={paneLabel('fast', layers.fast?.frame ?? null)}
            legend={LEGEND.fast}
            fitOnMount={false}
            onMapReady={onSecondaryReady}
            {...seedProps}
          />
        )}
      </div>

      {/* The timeline sits under the temporal pane only: the fast mode has a single frame to show. */}
      {showsTemporal && timeline.frame && (
        <div className={`grid w-full ${compare ? 'grid-cols-2 gap-0.5 bg-gray-400' : 'grid-cols-1'}`}>
          <Timeline timeline={timeline} compare={compare} />
          {compare && (
            <div className="flex items-center justify-center border-t border-gray-300 bg-gray-50 p-3 text-center text-xs text-gray-500">
              Fast mode: one steady frame at the peak. It does not follow the timeline.
            </div>
          )}
        </div>
      )}

      {seedNotice && (
        <div
          role="status"
          className="pointer-events-none absolute top-3 left-1/2 z-1000 -translate-x-1/2 rounded-md bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-900 shadow-md ring-1 ring-amber-300"
        >
          {seedNotice}
        </div>
      )}

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
            <div className="text-gray-700">{shown === 'fast' ? 'Fast mode: steady peak extent' : 'Temporal CA depth'}</div>
          )}
          {compare && <div className="text-gray-700">Pan or zoom either map; both follow.</div>}
        </div>
      )}
    </div>
  )
}
