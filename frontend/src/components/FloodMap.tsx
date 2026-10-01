import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import L from 'leaflet'
import { NEIGHBORHOOD_LABEL } from '../types/simulation'
import type { Bounds, LatLon, Neighborhood } from '../types/simulation'
import type { CompactFrame, DepthGrid } from '../rendering/depthGrid'
import type { Engine, ResultLayers } from '../hooks/useSimulationRun'
import type { Timeline as TimelineState } from '../hooks/useTimeline'
import { depthToImageDataUrl, extentToImageDataUrl } from '../rendering/depthToImage'
import { agreementToImageDataUrl, observedToImageDataUrl } from '../rendering/observed'
import type { ObservedMasks } from '../rendering/observed'
import { BASEMAPS, DEFAULT_BASEMAP } from '../geo/basemaps'
import type { BasemapId } from '../geo/basemaps'
import { AgreementLegend } from './AgreementLegend'
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
  /** The outline of the simulated grid, always drawn so the simulation's reach is visible; null before grids load. */
  footprint: [number, number][] | null
  seedMarker: LatLon | null
  /** Places the seed marker; null while clicks can't place one (not seeded pool, or a run is busy). */
  onMapClick: ((point: LatLon) => void) | null
  /** Why the last click placed nothing (outside the grid). */
  seedNotice: string | null
  /** The observed May 2024 extent, when it is on the grid the map shows (null otherwise: no toggle). */
  observed: ObservedMasks | null
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

const BASEMAP_STORAGE_KEY = 'terranova.basemap'

/** The basemap picked last time in this browser, if storage is readable and the choice still exists. */
function storedBasemap(): BasemapId {
  try {
    const stored = localStorage.getItem(BASEMAP_STORAGE_KEY)
    if (stored && stored in BASEMAPS) return stored as BasemapId
  } catch {
    // Storage blocked (private mode, site data off): fall back to the default.
  }
  return DEFAULT_BASEMAP
}

/** "Temporal CA", naming the neighborhood when it isn't the validated Moore one. */
function temporalName(neighborhood: Neighborhood | undefined): string {
  return !neighborhood || neighborhood === 'moore' ? 'Temporal CA' : `Temporal CA (${NEIGHBORHOOD_LABEL[neighborhood]})`
}

function paneLabel(engine: Engine, frame: CompactFrame | null, neighborhood?: Neighborhood): string {
  if (!frame) return engine === 'fast' ? 'Fast: computing…' : `${temporalName(neighborhood)}: starting…`
  if (engine === 'fast') return 'Fast: steady peak extent'
  const hours = (frame.elapsed_time ?? 0) / 3600
  return `${temporalName(neighborhood)}: t = ${hours.toFixed(1)} h`
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

/**
 * Rasterized overlay for one engine's shown frame, recomputed only when that frame changes. Against the observed
 * extent, when given, it is drawn as agreement (hit / missed / false alarm) instead of depth or extent.
 */
function useOverlayUrl(
  engine: Engine,
  frame: CompactFrame | null,
  needed: boolean,
  observed: ObservedMasks | null,
): string | null {
  return useMemo(() => {
    if (!needed || !frame) return null
    return (observed && agreementToImageDataUrl(frame.depth, observed)) ?? RENDER[engine](frame.depth)
  }, [engine, needed, frame, observed])
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
  observed,
}: FloodMapProps) {
  const [basemapId, setBasemapId] = useState<BasemapId>(storedBasemap)
  const selectBasemap = (id: BasemapId) => {
    setBasemapId(id)
    try {
      localStorage.setItem(BASEMAP_STORAGE_KEY, id)
    } catch {
      // Not remembered across visits, but still applied now.
    }
  }
  const paneProps = { basemap: BASEMAPS[basemapId], footprint, seedMarker, onMapClick }
  // A manual view choice only lasts for the run it was made in; a new run shows the engine just run, or
  // Compare for the May 2024 replay.
  const [choice, setChoice] = useState<{ view: MapView; runCount: number } | null>(null)
  const defaultView: MapView = replayActive ? 'compare' : activeEngine
  const view: MapView = choice && choice.runCount === runCount ? choice.view : defaultView
  const available = availableViews(layers)
  const shown = resolveView(view, available)
  const compare = shown === 'compare'

  // Drawing against the observed extent is a toggle that holds across runs; it only applies while the map's
  // grid is the one the observation is on.
  const [observedOn, setObservedOn] = useState(false)
  const against = observedOn ? observed : null

  const showsTemporal = shown === 'temporal' || compare
  // The temporal pane draws the timeline's selected frame (the newest one while following live).
  const temporalUrl = useOverlayUrl('temporal', timeline.frame, showsTemporal, against)
  const fastUrl = useOverlayUrl('fast', layers.fast?.frame ?? null, shown === 'fast' || compare, against)
  // With nothing simulated to draw yet, the toggle shows the observed extent on its own.
  const observedUrl = useMemo(() => (against && !shown ? observedToImageDataUrl(against) : null), [against, shown])
  // The primary pane shows the temporal result, or the fast one when that's the only view.
  const primary: Engine = shown === 'fast' ? 'fast' : 'temporal'
  const legendFor = (engine: Engine) =>
    against ? <AgreementLegend mode="agreement" stageM={against.stageM} /> : LEGEND[engine]
  const { onPrimaryReady, onSecondaryReady } = useSyncedMaps(bounds)

  return (
    <div className="relative flex h-full w-full flex-col">
      {/* The primary pane stays mounted across view changes; Compare adds the fast pane beside it. */}
      <div className={`relative grid min-h-0 w-full flex-1 ${compare ? 'grid-cols-2 gap-0.5 bg-basalt-line' : 'grid-cols-1'}`}>
        <MapPane
          bounds={bounds}
          imageUrl={observedUrl ?? (primary === 'fast' ? fastUrl : temporalUrl)}
          label={compare ? paneLabel('temporal', timeline.frame, layers.temporal?.neighborhood) : undefined}
          legend={
            shown ? legendFor(primary) : against ? <AgreementLegend mode="observed" stageM={against.stageM} /> : undefined
          }
          onMapReady={onPrimaryReady}
          {...paneProps}
        />
        {compare && (
          <MapPane
            bounds={bounds}
            imageUrl={fastUrl}
            label={paneLabel('fast', layers.fast?.frame ?? null)}
            legend={legendFor('fast')}
            fitOnMount={false}
            onMapReady={onSecondaryReady}
            {...paneProps}
          />
        )}
        <div
          role="radiogroup"
          aria-label="Basemap"
          className="absolute right-3 bottom-7 z-1000 flex gap-0.5 rounded-md bg-basalt/95 p-0.5 text-xs shadow-lg backdrop-blur-sm"
        >
          {Object.values(BASEMAPS).map(({ id, label }) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={basemapId === id}
              onClick={() => selectBasemap(id)}
              className={`rounded px-2 py-1 font-medium transition-colors ${
                basemapId === id ? 'bg-mist text-basalt' : 'text-mist hover:bg-basalt-raised'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* The timeline sits under the temporal pane only: the fast mode has a single frame to show. */}
      {showsTemporal && timeline.frame && (
        <div className={`grid w-full ${compare ? 'grid-cols-2 gap-0.5 bg-basalt-line' : 'grid-cols-1'}`}>
          <Timeline timeline={timeline} compare={compare} />
          {compare && (
            <div className="flex items-center justify-center border-t border-basalt-line bg-basalt p-3 text-center text-xs text-mist-muted">
              Fast mode: one steady frame at the peak. It does not follow the timeline.
            </div>
          )}
        </div>
      )}

      {seedNotice && (
        <div
          role="status"
          className="pointer-events-none absolute top-3 left-1/2 z-1000 -translate-x-1/2 rounded border-l-2 border-ochre bg-basalt/95 px-3 py-1.5 text-xs font-medium text-mist shadow-lg"
        >
          {seedNotice}
        </div>
      )}

      {(available.temporal || available.fast || observed) && (
        <div className="absolute top-3 right-3 z-1000 flex flex-col items-end gap-1.5 text-xs">
          <div className="flex items-center gap-0.5 rounded-md bg-basalt/95 p-0.5 shadow-lg backdrop-blur-sm">
            {(available.temporal || available.fast) && (
              <div className="flex gap-0.5" role="group" aria-label="Map view">
                {(Object.keys(VIEW_LABEL) as MapView[]).map((v) => (
              <button
                key={v}
                type="button"
                disabled={!available[v]}
                onClick={() => setChoice({ view: v, runCount })}
                aria-pressed={shown === v}
                className={`rounded px-2.5 py-1 text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
                  shown === v ? 'bg-gauge text-basalt' : 'text-mist hover:bg-basalt-raised disabled:hover:bg-transparent'
                }`}
              >
                {VIEW_LABEL[v]}
              </button>
            ))}
              </div>
            )}
            {observed && (
              <>
                {(available.temporal || available.fast) && (
                  <span aria-hidden="true" className="mx-0.5 h-5 w-px bg-basalt-line" />
                )}
                <button
                  type="button"
                  onClick={() => setObservedOn((on) => !on)}
                  aria-pressed={observedOn}
                  title="Draw the run against the observed May 2024 flood extent"
                  className={`flex items-center gap-1.5 rounded px-2.5 py-1 text-[13px] font-medium transition-colors ${
                    observedOn ? 'bg-mist text-basalt' : 'text-mist hover:bg-basalt-raised'
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`h-2.5 w-2.5 rounded-sm border ${observedOn ? 'border-basalt bg-basalt' : 'border-mist-muted'}`}
                  />
                  Observed
                </button>
              </>
            )}
          </div>
          {against ? (
            <div className="rounded bg-basalt/85 px-2 py-0.5 text-mist-muted shadow-lg">
              {shown ? 'Simulated vs. observed May 2024 extent' : 'Observed May 2024 extent'}
            </div>
          ) : (
            shown &&
            !compare && (
              <div className="rounded bg-basalt/85 px-2 py-0.5 text-mist-muted shadow-lg">
                {shown === 'fast'
                  ? 'Fast mode: steady peak extent'
                  : layers.temporal?.neighborhood === 'von_neumann'
                    ? 'Temporal CA depth, von Neumann (not validated)'
                    : 'Temporal CA depth'}
              </div>
            )
          )}
          {compare && !against && (
            <div className="rounded bg-basalt/85 px-2 py-0.5 text-mist-muted shadow-lg">Pan or zoom either map; both follow.</div>
          )}
        </div>
      )}
    </div>
  )
}
