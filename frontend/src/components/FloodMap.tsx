import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import L from 'leaflet'
import { NEIGHBORHOOD_LABEL } from '../types/simulation'
import type { Bounds, GridInfo, LatLon, Neighborhood, Resolution } from '../types/simulation'
import type { CompactFrame, DepthGrid } from '../rendering/depthGrid'
import type { Engine, ResultLayers } from '../hooks/useSimulationRun'
import type { Timeline as TimelineState } from '../hooks/useTimeline'
import {
  depthToImageDataUrl,
  extentToImageDataUrl,
  FLOODED_DEPTH_THRESHOLD_M,
  isWet,
  OVERLAY_OPACITY,
} from '../rendering/depthToImage'
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
import { arrivalBands, arrivalToImageDataUrl } from '../rendering/arrivalTime'
import { frameTime } from '../rendering/firstWet'
import { download, snapshotMap } from '../rendering/mapSnapshot'
import type { SnapshotLegend } from '../rendering/mapSnapshot'
import { agreementLegendSpec, arrivalLegendSpec, depthLegendSpec, extentLegendSpec } from '../rendering/legendSpecs'
import { extentsToGeoJson } from '../geo/extentGeoJson'
import type { ExtentFeatureInput } from '../geo/extentGeoJson'
import { BASEMAPS, DEFAULT_BASEMAP } from '../geo/basemaps'
import type { BasemapId } from '../geo/basemaps'
import { cellAt, cellRect } from '../geo/cell'
import type { Cell, CellRect } from '../geo/cell'
import { containsPoint } from '../geo/footprint'
import { useGridInputs } from '../hooks/useGridInputs'
import { AgreementLegend } from './AgreementLegend'
import { ArrivalLegend } from './ArrivalLegend'
import { CellInspector } from './CellInspector'
import { RoughnessLegend, TerrainLegend } from './InputLegend'
import { DepthLegend } from './DepthLegend'
import { ExtentLegend } from './ExtentLegend'
import { MapPane } from './MapPane'
import { Timeline } from './Timeline'
import { Popover, PopoverHeading } from './ui/Popover'
import { IconDownload, IconLayers } from './ui/icons'
import { messages, useI18n } from '../i18n'

type MapView = Engine | 'compare'

/**
 * What the temporal pane draws: the selected frame's depth, when each cell first flooded (up to the selected
 * frame), or the deepest water each cell reached over the run. All three come from frames the client already has
 * (useSimulationRun records first-wet times and the depth envelope as frames arrive).
 */
type TemporalProduct = 'depth' | 'arrival' | 'maxDepth'

const PRODUCTS: TemporalProduct[] = ['depth', 'arrival', 'maxDepth']

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

const VIEWS: MapView[] = ['temporal', 'fast', 'compare']

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
const OPACITY_STORAGE_KEY = 'terranova.overlayOpacity'

/** The overlay opacity set last time in this browser, if storage is readable and the value is sane. */
function storedOpacity(): number {
  try {
    const stored = Number(localStorage.getItem(OPACITY_STORAGE_KEY))
    if (stored >= 0.2 && stored <= 1) return stored
  } catch {
    // Storage blocked: fall back to the default.
  }
  return OVERLAY_OPACITY
}

/** An on/off map layer in the Layers menu: a swatch of the colors it draws in, a one-line hint, and a switch. */
function LayerToggle({
  label,
  title,
  hint,
  swatch,
  on,
  onToggle,
}: {
  label: string
  title: string
  hint: string
  swatch: string
  on: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      role="switch"
      onClick={onToggle}
      aria-checked={on}
      title={title}
      className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-sunken"
    >
      <span aria-hidden="true" className="h-4 w-6 shrink-0 rounded-[4px] ring-1 ring-line" style={{ background: swatch }} />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-[13px] font-medium">{label}</span>
        <span className="truncate text-[11px] text-ink-muted">{hint}</span>
      </span>
      <span
        aria-hidden="true"
        className={`relative h-4 w-7 shrink-0 rounded-full transition-colors after:absolute after:top-0.5 after:left-0.5 after:h-3 after:w-3 after:rounded-full after:bg-surface after:shadow-sm after:transition-transform ${
          on ? 'bg-accent after:translate-x-3' : 'bg-line'
        }`}
      />
    </button>
  )
}

/** A model input drawn under the flood: the terrain Z or the Manning roughness the engine runs on. */
type InputLayer = 'off' | 'terrain' | 'roughness'

/** The two input layers' toggles: one at a time, since both cover the whole grid. */
const INPUT_LAYERS: { id: Exclude<InputLayer, 'off'>; copy: 'terrainLayer' | 'roughnessLayer'; swatch: string }[] = [
  { id: 'terrain', copy: 'terrainLayer', swatch: `linear-gradient(to right, ${TERRAIN_GRADIENT.join(', ')})` },
  { id: 'roughness', copy: 'roughnessLayer', swatch: `linear-gradient(to right, ${ROUGHNESS_GRADIENT.join(', ')})` },
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
  return messages().map.temporalName(!neighborhood || neighborhood === 'moore' ? null : NEIGHBORHOOD_LABEL[neighborhood])
}

/** When a frame is: "t = 12.3 h" for a gauge-driven run, "step 1,200" for a seeded pool. */
function frameWhen(frame: CompactFrame): string {
  const { common } = messages()
  return frame.elapsed_time !== undefined ? common.tHours(frame.elapsed_time / 3600) : common.step(frame.step)
}

function paneLabel(
  engine: Engine,
  frame: CompactFrame | null,
  neighborhood?: Neighborhood,
  product: TemporalProduct = 'depth',
): string {
  const { map } = messages()
  if (!frame) return engine === 'fast' ? map.paneFastComputing : map.paneStarting(temporalName(neighborhood))
  if (engine === 'fast') return map.paneFastSteady
  if (product === 'maxDepth') return map.paneMaxDepth(temporalName(neighborhood))
  return map.paneAt(temporalName(neighborhood), frameWhen(frame))
}

/** "2026-10-02", for the exported caption. */
function today(): string {
  return new Date().toISOString().slice(0, 10)
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
  const { t } = useI18n()
  const [basemapId, setBasemapId] = useState<BasemapId>(storedBasemap)
  const selectBasemap = (id: BasemapId) => {
    setBasemapId(id)
    try {
      localStorage.setItem(BASEMAP_STORAGE_KEY, id)
    } catch {
      // Not remembered across visits, but still applied now.
    }
  }
  const [opacity, setOpacity] = useState(storedOpacity)
  const changeOpacity = (value: number) => {
    setOpacity(value)
    try {
      localStorage.setItem(OPACITY_STORAGE_KEY, String(value))
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
    opacity,
  }

  // Drawing against the observed extent is a toggle that holds across runs; it only applies while the map's
  // grid is the one the observation is on.
  const [observedOn, setObservedOn] = useState(false)
  const against = observedOn ? observed : null

  // The other temporal products apply while drawing the run on its own: against the observed extent the pane
  // always shows the selected frame's agreement.
  const [product, setProduct] = useState<TemporalProduct>('depth')
  const temporalLayer = layers.temporal
  const firstWet = temporalLayer?.firstWet ?? null
  const maxDepth = temporalLayer?.maxDepth ?? null
  const shownProduct: TemporalProduct =
    against || (product === 'arrival' && !firstWet) || (product === 'maxDepth' && !maxDepth) ? 'depth' : product
  // The bands span the run so far (its newest frame), so they hold still while scrubbing back.
  const span = firstWet && temporalLayer?.frame ? frameTime(temporalLayer.frame, firstWet.unit) : 0
  const bands = useMemo(() => (firstWet ? arrivalBands(span, firstWet.unit) : null), [firstWet, span])
  const arrivalUpTo = firstWet && timeline.frame ? frameTime(timeline.frame, firstWet.unit) : 0
  // The temporal pane draws the timeline's selected frame (the newest one while following live).
  const depthUrl = useOverlayUrl('temporal', timeline.frame, showsTemporal && shownProduct === 'depth', against)
  const arrivalUrl = useMemo(
    () =>
      showsTemporal && shownProduct === 'arrival' && firstWet && bands
        ? arrivalToImageDataUrl(firstWet, arrivalUpTo, bands)
        : null,
    [showsTemporal, shownProduct, firstWet, arrivalUpTo, bands],
  )
  const maxDepthUrl = useMemo(
    () => (showsTemporal && shownProduct === 'maxDepth' && maxDepth ? RENDER.temporal(maxDepth) : null),
    [showsTemporal, shownProduct, maxDepth],
  )
  const temporalUrl = shownProduct === 'arrival' ? arrivalUrl : shownProduct === 'maxDepth' ? maxDepthUrl : depthUrl
  const fastUrl = useOverlayUrl('fast', layers.fast?.frame ?? null, showsFast, against)
  // With nothing simulated to draw yet, the toggle shows the observed extent on its own.
  const observedUrl = useMemo(() => (against && !shown ? observedToImageDataUrl(against) : null), [against, shown])
  // The primary pane shows the temporal result, or the fast one when that's the only view.
  const primary: Engine = shown === 'fast' ? 'fast' : 'temporal'
  const legendFor = (engine: Engine): ReactNode => {
    if (against) return <AgreementLegend mode="agreement" stageM={against.stageM} />
    if (engine === 'temporal' && shownProduct === 'arrival' && bands && firstWet) {
      return <ArrivalLegend bands={bands} unit={firstWet.unit} />
    }
    if (engine === 'temporal' && shownProduct === 'maxDepth') {
      return <DepthLegend title={t.map.maxDepth} note={timeline.live ? t.map.maxDepthNoteLive : t.map.maxDepthNote} />
    }
    return LEGEND[engine]
  }
  const exportLegendFor = (engine: Engine): SnapshotLegend => {
    if (against) return agreementLegendSpec(against.stageM)
    if (engine === 'fast') return extentLegendSpec()
    if (shownProduct === 'arrival' && bands && firstWet) return arrivalLegendSpec(bands, firstWet.unit)
    if (shownProduct === 'maxDepth') return depthLegendSpec(t.legends.exportMaxDepth, t.map.maxDepthNote)
    return depthLegendSpec()
  }
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
  const activeOverlays = (against ? 1 : 0) + (inputLayer !== 'off' && mapGrid ? 1 : 0)

  const rootRef = useRef<HTMLDivElement | null>(null)
  const [exportNotice, setExportNotice] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  useEffect(() => {
    if (!exportNotice) return
    const timer = setTimeout(() => setExportNotice(null), 6000)
    return () => clearTimeout(timer)
  }, [exportNotice])
  const shownEngines: Engine[] = compare ? ['temporal', 'fast'] : shown ? [primary] : []
  const resolution = (temporalLayer ?? layers.fast)?.resolution
  const fileStem = () => {
    const what = compare ? 'compare' : primary === 'fast' ? 'fast' : `temporal-${shownProduct.toLowerCase()}`
    const frame = timeline.frame
    const when =
      !showsTemporal || !frame || shownProduct === 'maxDepth'
        ? ''
        : frame.elapsed_time !== undefined
          ? `-t${(frame.elapsed_time / 3600).toFixed(1)}h`
          : `-step${frame.step}`
    return `terranova-${resolution ?? 'grid'}m-${what}${when}`
  }
  const paneTitle = (engine: Engine) =>
    engine === 'fast'
      ? t.map.exportFastTitle
      : `${paneLabel('temporal', timeline.frame, temporalLayer?.neighborhood, shownProduct)}. ${
          against ? t.map.exportAgainstObserved : t.map.productTitles[shownProduct]
        }`

  const exportPng = async () => {
    const containers = Array.from(rootRef.current?.querySelectorAll<HTMLElement>('.leaflet-container') ?? [])
    if (shownEngines.length === 0 || containers.length < shownEngines.length) return
    setExporting(true)
    try {
      const snapshot = await snapshotMap(
        shownEngines.map((engine, i) => ({
          container: containers[i],
          title: paneTitle(engine),
          legend: exportLegendFor(engine),
          swatchOpacity: opacity,
        })),
        t.map.exportCaption(resolution, today()),
      )
      download(snapshot.blob, `${fileStem()}.png`)
      setExportNotice(snapshot.missingTiles > 0 ? t.map.pngMissingTiles(snapshot.missingTiles) : t.map.pngSaved)
    } catch (e) {
      setExportNotice(t.map.pngFailed(e instanceof Error ? e.message : String(e)))
    } finally {
      setExporting(false)
    }
  }

  const exportGeoJson = () => {
    if (!bounds) return
    const features: ExtentFeatureInput[] = []
    for (const engine of shownEngines) {
      const frame = engine === 'fast' ? layers.fast?.frame : timeline.frame
      const envelope = engine === 'temporal' && shownProduct === 'maxDepth'
      const grid = envelope ? maxDepth : frame?.depth
      if (!frame || !grid) continue
      const mask = new Uint8Array(grid.values.length)
      for (let cell = 0; cell < mask.length; cell++) mask[cell] = isWet(grid.values[cell]) ? 1 : 0
      features.push({
        mask,
        rows: grid.rows,
        cols: grid.cols,
        properties: {
          engine,
          extent: engine === 'fast' ? 'steady_peak' : envelope ? 'maximum_over_run' : 'frame',
          elapsed_hours:
            engine === 'fast'
              ? (frame.peak_elapsed_time ?? 0) / 3600
              : envelope || frame.elapsed_time === undefined
                ? null
                : frame.elapsed_time / 3600,
          step: engine === 'fast' || envelope ? null : frame.step,
          resolution_m: resolution ?? null,
          neighborhood: engine === 'fast' ? 'moore' : (temporalLayer?.neighborhood ?? null),
          flooded_depth_threshold_m: FLOODED_DEPTH_THRESHOLD_M,
        },
      })
    }
    if (features.length === 0) return
    // The grid's true outline places the cells; only when it is the results' grid (else the overlay's bounds).
    const footprintOnGrid = mapGrid && mapGrid.resolution === resolution ? mapGrid.footprint : null
    const geojson = extentsToGeoJson(features, footprintOnGrid, bounds)
    download(new Blob([JSON.stringify(geojson)], { type: 'application/geo+json' }), `${fileStem()}.geojson`)
    setExportNotice(t.map.geojsonSaved)
  }

  return (
    <div ref={rootRef} className="relative flex h-full w-full flex-col">
      {/* The primary pane stays mounted across view changes; Compare adds the fast pane beside it. */}
      <div className={`relative grid min-h-0 w-full flex-1 ${compare ? 'grid-cols-2 gap-px bg-line' : 'grid-cols-1'}`}>
        <MapPane
          bounds={bounds}
          imageUrl={observedUrl ?? (primary === 'fast' ? fastUrl : temporalUrl)}
          label={compare ? paneLabel('temporal', timeline.frame, layers.temporal?.neighborhood, shownProduct) : undefined}
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
            // Against the observed extent both panes share one key, drawn once under the primary pane.
            legend={against ? undefined : legendFor('fast')}
            fitOnMount={false}
            onMapReady={onSecondaryReady}
            {...paneProps}
          />
        )}
        {/* On the right, under the Layers menu and above the zoom control: the left side holds the legend column,
            which grows upward. The wrapper lets the card scroll on a short screen without blocking the map
            around it. */}
        {selected && (
          <div className="pointer-events-none absolute top-16 right-3 bottom-24 z-1000 flex flex-col items-end">
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
        <div className={`grid w-full ${compare ? 'grid-cols-2 gap-px bg-line' : 'grid-cols-1'}`}>
          <Timeline timeline={timeline} compare={compare} />
          {compare && (
            <div className="flex items-center justify-center border-t border-line bg-surface p-3 text-center text-xs text-ink-muted">
              {t.map.compareFastNote}
            </div>
          )}
        </div>
      )}

      {exportNotice && (
        <div
          role="status"
          className="float-card pointer-events-none absolute bottom-24 left-1/2 z-1000 max-w-[90%] -translate-x-1/2 rounded-lg border-l-2 border-accent px-3 py-1.5 text-xs font-medium text-ink"
        >
          {exportNotice}
        </div>
      )}

      {/* Top center: what is drawn. The view, then (for the temporal pane) which of its products. */}
      {(available.temporal || available.fast || seedNotice) && (
        <div className="absolute top-3 left-1/2 z-1000 flex -translate-x-1/2 flex-col items-center gap-1.5">
          {(available.temporal || available.fast) && (
          <div role="group" aria-label={t.map.mapView} className="float-card flex gap-0.5 rounded-xl p-1 text-[13px]">
            {VIEWS.map((v) => (
              <button
                key={v}
                type="button"
                disabled={!available[v]}
                onClick={() => setChoice({ view: v, runCount })}
                aria-pressed={shown === v}
                title={v === 'compare' ? t.map.compareTitle : undefined}
                className={`rounded-lg px-3 py-1 font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
                  shown === v ? 'bg-accent text-canvas' : 'text-ink hover:bg-sunken disabled:hover:bg-transparent'
                }`}
              >
                {t.map.views[v]}
              </button>
            ))}
          </div>
          )}
          {showsTemporal && (firstWet || maxDepth) && (
            <div
              role="radiogroup"
              aria-label={t.map.temporalLayer}
              title={against ? t.map.turnObservedOff : undefined}
              className="float-card flex gap-0.5 rounded-lg p-0.5 text-xs"
            >
              {PRODUCTS.map((p) => (
                <button
                  key={p}
                  type="button"
                  role="radio"
                  aria-checked={shownProduct === p}
                  disabled={Boolean(against) && p !== 'depth'}
                  onClick={() => setProduct(p)}
                  title={t.map.productTitles[p]}
                  className={`rounded-md px-2.5 py-0.5 font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
                    shownProduct === p ? 'bg-ink text-canvas' : 'text-ink-muted hover:text-ink disabled:hover:text-ink-muted'
                  }`}
                >
                  {t.map.products[p]}
                </button>
              ))}
            </div>
          )}
          {showsTemporal && layers.temporal?.neighborhood === 'von_neumann' && (
            <div className="float-card rounded-lg border-l-2 border-warn px-2.5 py-1 text-xs text-ink">
              {t.map.vonNeumannWarning}
            </div>
          )}
          {seedNotice && (
            <div
              role="status"
              className="float-card pointer-events-none rounded-lg border-l-2 border-warn px-3 py-1.5 text-xs font-medium text-ink"
            >
              {seedNotice}
            </div>
          )}
        </div>
      )}

      {/* One menu for everything drawn under or over the result: the background, and the data layers as
          on/off switches with their colors. Terrain and roughness are model inputs, drawn under the flood. */}
      <div className="absolute top-3 right-3 z-1000 flex gap-2">
        {shown && (
          <Popover
            label={t.map.export}
            triggerClassName="float-card flex h-9 items-center gap-1.5 rounded-xl px-3 text-[13px] font-medium text-ink"
            trigger={() => (
              <>
                <IconDownload className="h-[18px] w-[18px]" />
                <span className="hidden lg:inline">{exporting ? t.map.saving : t.map.export}</span>
              </>
            )}
          >
            <PopoverHeading>{t.map.exportHeading}</PopoverHeading>
            <div role="group" aria-label={t.map.export} className="flex flex-col">
              <button
                type="button"
                onClick={() => void exportPng()}
                disabled={exporting}
                className="flex flex-col rounded-lg px-2 py-1.5 text-left hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span className="text-[13px] font-medium">{exporting ? t.map.pngSaving : t.map.png}</span>
                <span className="text-[11px] text-ink-muted">{t.map.pngHint}</span>
              </button>
              <button
                type="button"
                onClick={exportGeoJson}
                className="flex flex-col rounded-lg px-2 py-1.5 text-left hover:bg-sunken"
              >
                <span className="text-[13px] font-medium">{t.map.geojson}</span>
                <span className="text-[11px] text-ink-muted">{t.map.geojsonHint}</span>
              </button>
            </div>
          </Popover>
        )}
        <Popover
          label={t.map.mapLayers}
          triggerClassName="float-card flex h-9 items-center gap-1.5 rounded-xl px-3 text-[13px] font-medium text-ink"
          trigger={() => (
            <>
              <IconLayers className="h-[18px] w-[18px]" />
              <span className="hidden sm:inline">{t.map.layers}</span>
              {activeOverlays > 0 && (
                <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold text-canvas">
                  {activeOverlays}
                </span>
              )}
            </>
          )}
        >
          <PopoverHeading>{t.map.basemap}</PopoverHeading>
          <div role="radiogroup" aria-label={t.map.basemap} className="grid grid-cols-2 gap-1 px-1 pb-1">
            {Object.values(BASEMAPS).map(({ id }) => (
              <button
                key={id}
                type="button"
                role="radio"
                aria-checked={basemapId === id}
                onClick={() => selectBasemap(id)}
                className={`rounded-lg px-2 py-1.5 text-[13px] font-medium transition-colors ${
                  basemapId === id ? 'bg-ink text-canvas' : 'bg-sunken text-ink hover:bg-line'
                }`}
              >
                {t.map.basemaps[id]}
              </button>
            ))}
          </div>
          {(observed || mapGrid) && (
            <>
              <div className="mx-2 my-1 h-px bg-line" />
              <PopoverHeading>{t.map.overlays}</PopoverHeading>
              <div role="group" aria-label={t.map.mapLayers} className="flex flex-col">
                {observed && (
                  <LayerToggle
                    {...t.map.observedLayer}
                    swatch={OBSERVED_COLOR}
                    on={observedOn}
                    onToggle={() => setObservedOn((on) => !on)}
                  />
                )}
                {mapGrid &&
                  INPUT_LAYERS.map(({ id, copy, swatch }) => (
                    <LayerToggle
                      key={id}
                      {...t.map[copy]}
                      swatch={swatch}
                      on={inputLayer === id}
                      onToggle={() => selectInputLayer(inputLayer === id ? 'off' : id)}
                    />
                  ))}
              </div>
            </>
          )}
          {(shown || observedUrl) && (
            <>
              <div className="mx-2 my-1 h-px bg-line" />
              <label className="flex items-center gap-3 px-2 pt-1 pb-1.5 text-[13px]">
                <span className="font-medium">{t.map.opacity}</span>
                <input
                  type="range"
                  min={0.2}
                  max={1}
                  step={0.05}
                  value={opacity}
                  onChange={(e) => changeOpacity(Number(e.target.value))}
                  aria-valuetext={`${Math.round(opacity * 100)}%`}
                  className="range min-w-0 flex-1"
                  style={{ '--fill': `${((opacity - 0.2) / 0.8) * 100}%` } as CSSProperties}
                />
                <span className="w-9 text-right text-xs text-ink-muted tabular-nums">{Math.round(opacity * 100)}%</span>
              </label>
            </>
          )}
        </Popover>
      </div>
    </div>
  )
}
