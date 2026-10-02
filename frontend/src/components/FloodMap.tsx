import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import L from 'leaflet'
import { NEIGHBORHOOD_LABEL } from '../types/simulation'
import type { Bounds, GridInfo, LatLon, Neighborhood, Resolution } from '../types/simulation'
import type { CompactFrame, DepthGrid } from '../rendering/depthGrid'
import type { Engine, ResultLayers } from '../hooks/useSimulationRun'
import type { Timeline as TimelineState } from '../hooks/useTimeline'
import { depthToImageDataUrl, extentToImageDataUrl } from '../rendering/depthToImage'
import { agreementToImageDataUrl, OBSERVED_COLOR, observedToImageDataUrl } from '../rendering/observed'
import type { ObservedMasks } from '../rendering/observed'
import {
  INPUT_OVERLAY_OPACITY,
  ROUGHNESS_GRADIENT,
  roughnessToImageDataUrl,
  TERRAIN_GRADIENT,
  terrainToImageDataUrl,
} from '../rendering/inputsToImage'
import { isNeighbor } from '../rendering/outflowShares'
import { BASEMAPS, DEFAULT_BASEMAP } from '../geo/basemaps'
import type { BasemapId } from '../geo/basemaps'
import { cellAt, cellRect } from '../geo/cell'
import type { Cell, CellRect } from '../geo/cell'
import { containsPoint } from '../geo/footprint'
import { useGridInputs } from '../hooks/useGridInputs'
import { AgreementLegend } from './AgreementLegend'
import { CellInspector } from './CellInspector'
import { RoughnessLegend, TerrainLegend } from './InputLegend'
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
  /**
   * The grid the map shows (the result's, or before any run the selected one): what the input layers and the
   * cell inspector are on. Null before grids load.
   */
  mapGrid: GridInfo | null
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

/** An on/off map layer, with a swatch of the colors it draws in (dimmed while off). */
function LayerToggle({
  label,
  title,
  swatch,
  on,
  onToggle,
}: {
  label: string
  title: string
  swatch: string
  on: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={on}
      title={title}
      className={`flex items-center gap-1.5 rounded px-2.5 py-1 text-[13px] font-medium transition-colors ${
        on ? 'bg-mist text-basalt' : 'text-mist hover:bg-basalt-raised'
      }`}
    >
      <span
        aria-hidden="true"
        className={`inline-block h-2.5 w-3.5 rounded-sm ring-1 ${on ? 'ring-basalt/40' : 'opacity-60 ring-mist-muted/50'}`}
        style={{ background: swatch }}
      />
      {label}
    </button>
  )
}

/** A model input drawn under the flood: the terrain Z or the Manning roughness the engine runs on. */
type InputLayer = 'off' | 'terrain' | 'roughness'

/** The two input layers' toggles: one at a time, since both cover the whole grid. */
const INPUT_LAYERS: { id: Exclude<InputLayer, 'off'>; label: string; title: string; swatch: string }[] = [
  {
    id: 'terrain',
    label: 'Terrain',
    title: "Model input: the model's own DEM, the terrain Z the automaton runs on",
    swatch: `linear-gradient(to right, ${TERRAIN_GRADIENT.join(', ')})`,
  },
  {
    id: 'roughness',
    label: 'Roughness',
    title: "Model input: Manning's n from MapBiomas land cover, what slows the water",
    swatch: `linear-gradient(to right, ${ROUGHNESS_GRADIENT.join(', ')})`,
  },
]

const INPUT_LAYER_STORAGE_KEY = 'terranova.inputLayer'

/** The input layer picked last time in this browser, if storage is readable and the choice still exists. */
function storedInputLayer(): InputLayer {
  try {
    const stored = localStorage.getItem(INPUT_LAYER_STORAGE_KEY)
    if (stored === 'terrain' || stored === 'roughness') return stored
  } catch {
    // Storage blocked (private mode, site data off): fall back to no layer.
  }
  return 'off'
}

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

// The temporal overlay is shaded by depth; the fast one shows extent only, since only its extent is validated.
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
  mapGrid,
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
  // A manual view choice only lasts for the run it was made in; a new run shows the engine just run, or
  // Compare for the May 2024 replay.
  const [choice, setChoice] = useState<{ view: MapView; runCount: number } | null>(null)
  const defaultView: MapView = replayActive ? 'compare' : activeEngine
  const view: MapView = choice && choice.runCount === runCount ? choice.view : defaultView
  const available = availableViews(layers)
  const shown = resolveView(view, available)
  const compare = shown === 'compare'
  const showsTemporal = shown === 'temporal' || compare
  const showsFast = shown === 'fast' || compare

  const [inputLayer, setInputLayer] = useState<InputLayer>(storedInputLayer)
  const selectInputLayer = (layer: InputLayer) => {
    setInputLayer(layer)
    try {
      localStorage.setItem(INPUT_LAYER_STORAGE_KEY, layer)
    } catch {
      // Not remembered across visits, but still applied now.
    }
  }

  // The inspected cell belongs to the grid it was clicked on; it is dropped when the map moves to another grid.
  const [inspected, setInspected] = useState<(Cell & { resolution: Resolution }) | null>(null)
  const selected = inspected && mapGrid && inspected.resolution === mapGrid.resolution ? inspected : null
  const inputs = useGridInputs(mapGrid && (inputLayer !== 'off' || selected) ? mapGrid.resolution : null)
  const inputImage = useMemo(() => {
    if (!inputs || !mapGrid || inputLayer === 'off') return null
    const url = inputLayer === 'terrain' ? terrainToImageDataUrl(inputs) : roughnessToImageDataUrl(inputs)
    return { url, bounds: mapGrid.bounds, opacity: INPUT_OVERLAY_OPACITY[inputLayer] }
  }, [inputs, mapGrid, inputLayer])

  // The inspector reads only the results on screen (a hidden pane's numbers would be a puzzle), and only on the
  // map's grid (a layer on another grid has other cells).
  const temporalOnGrid =
    showsTemporal && layers.temporal && layers.temporal.resolution === mapGrid?.resolution ? layers.temporal : null
  const fastOnGrid = showsFast && layers.fast && layers.fast.resolution === mapGrid?.resolution ? layers.fast : null
  const inspectedNeighborhood = temporalOnGrid && timeline.frame ? temporalOnGrid.neighborhood : 'moore'
  const highlight = useMemo(() => {
    if (!selected || !mapGrid) return null
    const [rows, cols] = mapGrid.grid_shape
    const rect = (row: number, col: number) => cellRect(mapGrid.bounds, rows, cols, { row, col })
    const neighbors: CellRect[] = []
    for (const dr of [-1, 0, 1]) {
      for (const dc of [-1, 0, 1]) {
        const row = selected.row + dr
        const col = selected.col + dc
        const inside = row >= 0 && row < rows && col >= 0 && col < cols
        if (inside && isNeighbor(dr, dc, inspectedNeighborhood)) neighbors.push(rect(row, col))
      }
    }
    return { cell: rect(selected.row, selected.col), neighbors }
  }, [selected, mapGrid, inspectedNeighborhood])

  // Every click inspects the cell under it (outside the grid it closes the inspector); while a seed can be
  // placed, the same click also places it, so the seed spot's terrain shows right away.
  const onClick = (point: LatLon) => {
    onMapClick?.(point)
    if (!mapGrid || !containsPoint(mapGrid.footprint, point.lat, point.lon)) {
      setInspected(null)
      return
    }
    const [rows, cols] = mapGrid.grid_shape
    const cell = cellAt(mapGrid.bounds, rows, cols, point)
    setInspected(cell && { ...cell, resolution: mapGrid.resolution })
  }

  const paneProps = {
    basemap: BASEMAPS[basemapId],
    footprint,
    seedMarker,
    onMapClick: onClick,
    crosshair: Boolean(onMapClick),
    inputImage,
    highlight,
  }

  // Drawing against the observed extent is a toggle that holds across runs; it only applies while the map's
  // grid is the one the observation is on.
  const [observedOn, setObservedOn] = useState(false)
  const against = observedOn ? observed : null

  // The temporal pane draws the timeline's selected frame (the newest one while following live).
  const temporalUrl = useOverlayUrl('temporal', timeline.frame, showsTemporal, against)
  const fastUrl = useOverlayUrl('fast', layers.fast?.frame ?? null, showsFast, against)
  // With nothing simulated to draw yet, the toggle shows the observed extent on its own.
  const observedUrl = useMemo(() => (against && !shown ? observedToImageDataUrl(against) : null), [against, shown])
  // The primary pane shows the temporal result, or the fast one when that's the only view.
  const primary: Engine = shown === 'fast' ? 'fast' : 'temporal'
  const legendFor = (engine: Engine) =>
    against ? <AgreementLegend mode="agreement" stageM={against.stageM} /> : LEGEND[engine]
  const inputLegend =
    inputImage && inputs ? (
      inputLayer === 'terrain' ? <TerrainLegend inputs={inputs} /> : <RoughnessLegend inputs={inputs} />
    ) : null
  const primaryFloodLegend = shown ? (
    legendFor(primary)
  ) : against ? (
    <AgreementLegend mode="observed" stageM={against.stageM} />
  ) : null
  const { onPrimaryReady, onSecondaryReady } = useSyncedMaps(bounds)

  return (
    <div className="relative flex h-full w-full flex-col">
      {/* The primary pane stays mounted across view changes; Compare adds the fast pane beside it. */}
      <div className={`relative grid min-h-0 w-full flex-1 ${compare ? 'grid-cols-2 gap-0.5 bg-basalt-line' : 'grid-cols-1'}`}>
        <MapPane
          bounds={bounds}
          imageUrl={observedUrl ?? (primary === 'fast' ? fastUrl : temporalUrl)}
          label={compare ? paneLabel('temporal', timeline.frame, layers.temporal?.neighborhood) : undefined}
          // The input layer's key sits under the primary pane only: in Compare both panes draw the same layer.
          legend={
            primaryFloodLegend || inputLegend ? (
              <div className="flex flex-col items-start gap-2">
                {primaryFloodLegend}
                {inputLegend}
              </div>
            ) : undefined
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

        {/* On the right, under the view and layer controls and above the basemap picker: the left side holds the
            legend column, which grows upward. The wrapper lets the card scroll on a short screen without blocking
            the map around it. */}
        {selected && (
          <div className="pointer-events-none absolute top-36 right-3 bottom-18 z-1000 flex flex-col items-end">
            <div className="pointer-events-auto min-h-0">
              <CellInspector
                cell={selected}
                inputs={inputs}
                temporal={temporalOnGrid ? { layer: temporalOnGrid, frame: timeline.frame } : null}
                fast={fastOnGrid?.frame ?? null}
                compare={compare}
                onClose={() => setInspected(null)}
              />
            </div>
          </div>
        )}
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

      {(available.temporal || available.fast || observed || mapGrid) && (
        <div className="absolute top-3 right-3 z-1000 flex flex-col items-end gap-1.5 text-xs">
          {(available.temporal || available.fast) && (
            <div
              role="group"
              aria-label="Map view"
              className="flex gap-0.5 rounded-md bg-basalt/95 p-0.5 shadow-lg backdrop-blur-sm"
            >
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
          {/* Data drawn on the map, as on/off toggles with their colors - unlike the basemap picker (bottom right),
              which only chooses the background. Terrain and roughness are model inputs, drawn under the flood. */}
          {(observed || mapGrid) && (
            <div
              role="group"
              aria-label="Map layers"
              className="flex items-center gap-0.5 rounded-md bg-basalt/95 p-0.5 shadow-lg backdrop-blur-sm"
            >
              <span className="px-1.5 font-display text-[11px] font-semibold tracking-wide text-mist-muted uppercase">
                Layers
              </span>
              {observed && (
                <LayerToggle
                  label="Observed"
                  title="Draw the run against the observed May 2024 flood extent"
                  swatch={OBSERVED_COLOR}
                  on={observedOn}
                  onToggle={() => setObservedOn((on) => !on)}
                />
              )}
              {mapGrid && (
                <>
                  {observed && <span aria-hidden="true" className="mx-0.5 h-5 w-px bg-basalt-line" />}
                  {INPUT_LAYERS.map(({ id, label, title, swatch }) => (
                    <LayerToggle
                      key={id}
                      label={label}
                      title={title}
                      swatch={swatch}
                      on={inputLayer === id}
                      onToggle={() => selectInputLayer(inputLayer === id ? 'off' : id)}
                    />
                  ))}
                </>
              )}
            </div>
          )}
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
