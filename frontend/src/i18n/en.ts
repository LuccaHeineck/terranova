import { int, num, upTo } from './format'

/**
 * Every UI string in English. pt-BR.ts must provide the same shape (it is typed as `Messages`). Strings that
 * carry numbers are functions, so each language orders its own words; numbers go through format.ts.
 */
export const en = {
  common: {
    temporalCa: 'Temporal CA',
    fast: 'Fast',
    fastMode: 'Fast mode',
    dry: 'dry',
    na: 'n/a',
    default: 'default',
    /** "t = 12.3 h" */
    tHours: (hours: number) => `t = ${num(hours, 1)} h`,
    hours: (hours: number) => `${num(hours, 1)} h`,
    step: (step: number) => `step ${int(step)}`,
    cells: (n: number) => `${int(n)} cells`,
    gridM: (resolution: number) => `${resolution} m grid`,
    neighborhood: (label: string) => `${label} neighborhood`,
    compass: { N: 'N', S: 'S', E: 'E', W: 'W' },
  },

  topBar: {
    tagline: 'Flood simulation · Vale do Taquari',
    showPanel: 'Show panel',
    hidePanel: 'Hide panel',
    gridInfo: (rows: number, cols: number, resolution: number) => `${int(rows)} × ${int(cols)} cells · ${resolution} m`,
    status: {
      starting: 'Starting…',
      streaming: 'Running',
      done: 'Done',
      stopped: 'Stopped',
      error: 'Error',
    },
    about: 'About',
    language: 'Language',
    stop: 'Stop',
    start: 'Start',
    startSuffix: ' simulation',
  },

  sidebar: {
    panels: 'Panels',
    tabs: { setup: 'Setup', results: 'Results', log: 'Log' },
    closePanel: 'Close panel',
    badgeError: ' (error)',
    badgeLive: ' (run in progress)',
  },

  fields: {
    decrease: (label: string) => `Decrease ${label.toLowerCase()}`,
    increase: (label: string) => `Increase ${label.toLowerCase()}`,
  },

  config: {
    locked: 'Settings are locked while a run is going. Stop it to change them.',
    replayKicker: 'Validated scenario',
    replayTitle: 'May 2024 flood',
    replayText: 'The 90 m grid, fast engine and temporal CA to the observed peak, side by side.',
    replayButton: 'Replay the May 2024 flood',
    orConfigure: 'or configure a run',
    engine: 'Engine',
    temporalDescription: 'Time-stepped flow, streams frames',
    fastDescription: 'Steady extent at the observed peak',
    grid: 'Grid',
    gridCaption: { 30: 'Live', 60: 'Unvalidated', 90: 'Validation' } as Record<number, string>,
    fastNote:
      'Real May 2024 event: one steady classification at the observed peak discharge. No time steps, so there is no frame interval or outflow fraction.',
    scenario: 'Scenario',
    seededPool: 'Seeded pool',
    seededPoolCaption: 'Synthetic',
    gauges: 'May 2024 gauges',
    gaugesCaption: 'Real event',
    steps: 'Steps',
    seedVolume: 'Seed volume',
    seedVolumeHint: "Summed cell depth (m), as the log's volume.",
    seedVolumeEquivalent: (depth: number, cubicMetres: number, resolution: number) =>
      `${upTo(depth, 1)} m deep over the 5×5 seed patch, ≈ ${upTo(cubicMetres, 1)} m³ on the ${resolution} m grid.`,
    seedLocation: 'Seed location',
    clear: 'Clear',
    lowestPoint: 'Lowest point of the terrain (default)',
    seedOutlineError: (error: string) => `Can't place a seed on the map yet: the grid outline didn't load (${error}). Retrying…`,
    seedMoveHint: 'Click the map again to move it; Clear goes back to the lowest point.',
    seedPickHint: (resolution: number) => `Click the map inside the dashed ${resolution} m grid outline to choose a spot instead.`,
    stopAtPeak: 'Stop at the observed peak',
    tuning: 'Engine tuning',
    changed: 'Changed',
    neighborhood: 'Neighborhood',
    mooreCaption: '8 neighbors, validated',
    vonNeumannCaption: '4 neighbors, not validated',
    validatedNeighborhoodNote:
      'The validated May 2024 results (CSI 0.90, the fast-mode agreement) apply to the Moore neighborhood only.',
    frameInterval: 'Frame interval',
    stepsUnit: 'steps',
    outflowFraction: 'Outflow fraction',
    vonNeumannOutflowHint: (max: number) =>
      `At most ${num(max, 3)} with von Neumann: above that its result depends on the engine's substep size.`,
    summaryFast: (resolution: number) => `Runs the fast engine at the observed May 2024 peak on the ${resolution} m grid.`,
    summarySeeded: (steps: number, resolution: number, neighborhood: string) =>
      `Runs a ${int(steps)}-step seeded pool on the ${resolution} m grid, ${neighborhood}.`,
    summaryGauges: (toPeak: boolean, resolution: number, neighborhood: string) =>
      `Runs the May 2024 gauge record ${toPeak ? 'up to the observed peak' : 'in full (about 14 days)'} on the ${resolution} m grid, ${neighborhood}.`,
    seedOutside: (resolution: number) => `Outside the ${resolution} m grid: click inside the dashed outline.`,
  },

  results: {
    empty: 'No results yet. Set up a run, or replay the May 2024 flood.',
    goToSetup: 'Go to setup',
    thisRun: 'This run',
    engine: 'Engine',
    engines: 'Engines',
    grid: 'Grid',
    cells: 'Cells',
    westEast: 'West / east',
    southNorth: 'South / north',
    ranTemporal: (neighborhood: string) => `Temporal CA (${neighborhood})`,
    hydrograph: 'May 2024 gauge record',
    observed: 'Against the observed flood',
    observedIntro: (stageM: number, excluded: number) =>
      `SGB/CPRM extent at the ${num(stageM, 2)} m peak stage. Gap-corrected scores leave out the ${int(excluded)} Estrela-side cells the reference never modeled. Documented: the temporal CA scores CSI ${num(0.9, 2)} at the peak.`,
    wrongGrid: (observedResolution: number, runResolution: number | undefined) =>
      `The observed extent is scored on the ${observedResolution} m validation grid only; this run used the ${runResolution} m grid.`,
    atPeak: 'at the peak',
    csiCorrected: 'CSI, gap-corrected',
    hitRate: 'Hit rate',
    falseAlarmRate: 'False alarm rate',
    hitMissedFalse: 'Hit / missed / false alarm',
    naiveCsi: 'Naive CSI (whole grid)',
    comparison: 'Comparison',
    comparisonIntro: (resolution: number, followingLatest: boolean, threshold: number) =>
      `${resolution} m grid${followingLatest ? '' : ', temporal frame selected on the timeline'}. Flooded means depth > ${threshold} m.`,
    agreement: 'Flooded-cell agreement',
    both: 'Both',
    temporalOnly: 'Temporal only',
    fastOnly: 'Fast only',
    flooded: 'Flooded',
    floodedAt: (cells: number, hours: number) => `${int(cells)} cells at t = ${num(hours, 1)} h`,
    floodedAtPeak: (cells: number, hours: number) => `${int(cells)} cells at the peak (t = ${num(hours, 1)} h)`,
    engineTime: 'Engine',
    wallClock: 'Wall-clock',
    soFar: ' so far',
    differentNeighborhoods: (temporal: string, fast: string) =>
      `Different neighborhoods: the temporal run used ${temporal}; the fast engine is ${fast}-based. The validated agreement numbers are for Moore only.`,
    notAtPeak: (hours: number, peakHours: number) =>
      `The temporal run is at t = ${num(hours, 1)} h of the ${num(peakHours, 1)} h to the peak that the fast mode models, so the two extents are from different moments of the event.`,
  },

  hydrograph: {
    atCursor: 'At cursor',
    atTimeline: 'At the timeline',
    peak: 'Peak',
    peakTick: 'peak',
    discharge: (m3s: number) => `${int(m3s)} m³/s`,
    aria: (duration: string, peak: string, at: string) =>
      `Discharge at the Estrela gauge over ${duration}, peaking at ${peak} at t = ${at}`,
    caption: (station: string, peak: string, at: string) =>
      `Station ${station}, Porto Fluvial de Estrela: ANA's discharge, from the stage record through the station's own rating pairs. Peak ${peak} at t = ${at}.`,
    markerNote: ' The vertical marker follows the timeline.',
  },

  map: {
    views: { temporal: 'Temporal', fast: 'Fast', compare: 'Compare' },
    mapView: 'Map view',
    compareTitle: 'Both engines side by side; pan or zoom either map and both follow',
    products: { depth: 'Depth', arrival: 'Arrival', maxDepth: 'Max depth' },
    productTitles: {
      depth: 'Water depth at the timeline frame',
      arrival: 'When each cell first flooded, up to the timeline frame',
      maxDepth: 'Deepest water each cell reached over the run',
    },
    temporalLayer: 'Temporal layer',
    turnObservedOff: 'Turn Observed off to show arrival time or maximum depth',
    vonNeumannWarning: 'von Neumann neighborhood: not validated',
    layers: 'Layers',
    mapLayers: 'Map layers',
    basemap: 'Basemap',
    basemaps: { relief: 'Relief', topo: 'Topographic', streets: 'Streets', satellite: 'Satellite' },
    overlays: 'Overlays',
    opacity: 'Opacity',
    observedLayer: {
      label: 'Observed flood',
      hint: 'May 2024 extent, scored against the run',
      title: 'Draw the run against the observed May 2024 flood extent',
    },
    terrainLayer: {
      label: 'Terrain',
      hint: 'Model DEM, the terrain Z',
      title: "Model input: the model's own DEM, the terrain Z the automaton runs on",
    },
    roughnessLayer: {
      label: 'Roughness',
      hint: "Manning's n from land cover",
      title: "Model input: Manning's n from MapBiomas land cover, what slows the water",
    },
    export: 'Export',
    saving: 'Saving…',
    exportHeading: 'Export what is on the map',
    png: 'PNG image',
    pngSaving: 'Saving PNG…',
    pngHint: 'The map as shown, with its legend',
    geojson: 'GeoJSON',
    geojsonHint: 'Flooded extent as polygons (WGS84)',
    pngSaved: 'Map saved as PNG.',
    pngMissingTiles: (n: number) => `Map saved, without ${n} basemap tiles whose server blocks cross-origin reads.`,
    pngFailed: (message: string) => `PNG export failed: ${message}`,
    geojsonSaved: 'Flooded extent saved as GeoJSON (WGS84).',
    exportCaption: (resolution: number | undefined, date: string) =>
      `Terranova CA flood simulator, Vale do Taquari${resolution ? `, ${resolution} m grid` : ''}. Exported ${date}.`,
    temporalName: (neighborhood: string | null) => (neighborhood ? `Temporal CA (${neighborhood})` : 'Temporal CA'),
    paneStarting: (name: string) => `${name}: starting…`,
    paneFastComputing: 'Fast: computing…',
    paneFastSteady: 'Fast: steady peak extent',
    paneMaxDepth: (name: string) => `${name}: maximum depth`,
    paneAt: (name: string, when: string) => `${name}: ${when}`,
    exportFastTitle: 'Fast mode: steady peak extent',
    exportAgainstObserved: 'Against the observed May 2024 extent',
    compareFastNote: 'Fast mode: one steady frame at the peak. It does not follow the timeline.',
    maxDepth: 'Maximum depth',
    maxDepthNoteLive: 'Over the run so far.',
    maxDepthNote: 'Over the run.',
  },

  legends: {
    depth: 'Water depth',
    metres: 'metres',
    dryBelow: (threshold: number) => `Dry below ${num(threshold, 2)} m`,
    fastFlooded: (threshold: number) => `Flooded (depth > ${num(threshold, 2)} m)`,
    fastExtentOnly: 'Extent only: its depths are not validated.',
    fastExtentOnlyTitle: "The fast mode's depths are a steady estimate with no observations to validate them against.",
    agreement: 'Against the observed flood',
    observed: 'Observed flood, May 2024',
    hit: 'Hit: flooded in both',
    missed: 'Missed: observed only',
    falseAlarm: 'False alarm: simulated only',
    notScored: 'Not scored: reference gap',
    floodedInReference: 'Flooded in the reference',
    observedNote: (stageM: number) => `SGB/CPRM extent at the ${num(stageM, 2)} m peak stage.`,
    gapNote: ' Estrela-side cells the reference never modeled are not scored.',
    arrivalHours: 'First flooded (h into the event)',
    arrivalSteps: 'First flooded (engine step)',
    arrivalNote: "Cells wet by the timeline's t. Darker: reached sooner.",
    terrain: 'Terrain Z (m)',
    terrainNote: (resolution: number) =>
      `The model's own sink-filled DEM at ${resolution} m, shaded from the north-west: one pixel per cell.`,
    roughness: "Manning's n (roughness)",
    roughnessNote: 'MapBiomas 2024 land cover. Darker slows the water more; one shade per value, in order, not to scale.',
    // The exported PNG's legends (rendering/legendSpecs.ts).
    exportDepth: 'Water depth (m)',
    exportMaxDepth: 'Maximum depth (m)',
    exportDry: (threshold: number) => `Under ${num(threshold, 2)} m: dry`,
    exportArrivalNote: 'Darker: reached sooner.',
    exportExtentOnly: 'Extent only.',
  },

  inspector: {
    title: 'Cell inspector',
    rowCol: (row: number, col: number) => `row ${row}, col ${col}`,
    gridSuffix: (resolution: number) => ` · ${resolution} m grid`,
    sameCell: 'The same cell in both panes, outlined in each.',
    close: 'Close the cell inspector',
    loading: "Loading the grid's terrain and land cover…",
    modelInputs: 'Model inputs',
    bothEngines: 'both engines',
    elevation: 'Elevation Z',
    landCover: 'Land cover',
    manning: "Manning's n",
    depth: 'Depth',
    waterSurface: 'Water surface',
    firstWet: 'First wet',
    atFrameNote: "At the timeline's frame. First wet is exact to one frame interval.",
    steadyPeak: 'steady peak',
    never: 'never',
    drySoFar: 'dry so far',
    later: ' (later)',
    tMinutes: (minutes: number) => `t = ${num(minutes, 0)} min`,
    outflowTitle: (neighborhood: string) => `Outflow split · ${neighborhood}`,
    bareTerrain: 'bare terrain',
    wall: 'wall',
    uphill: 'uphill',
    thisCell: 'this cell',
    noWater: 'no water',
    depthH: (depth: number) => `h ${num(depth, 2)} m`,
    metres: (value: number) => `${num(value, 2)} m`,
    noLowerNeighbor: 'No lower neighbor: water here stays put (a pit or a flat water surface).',
    splitWet:
      'Each lower neighbor gets √(drop / distance) / n of the receiving cell, normalized, at the temporal frame shown. The engine re-weighs it on every sub-step.',
    splitDryHere:
      'Dry here at the temporal frame shown: where water arriving would go, by √(drop / distance) / n of the receiving cell.',
    splitWouldGo: 'Where water arriving here would go under the temporal CA, by √(drop / distance) / n of the receiving cell.',
    fastNoSplit: ' The fast engine has no such split: it fills a steady stage per river reach instead.',
    edgeWalls: (outlet: boolean) =>
      ` Off-grid neighbors are walls${outlet ? ' (the gauge-driven south outlet is not shown)' : ''}.`,
    /** MapBiomas class names as the API sends them; English is the source, so no lookup. */
    landCoverNames: {} as Record<string, string>,
  },

  timeline: {
    live: 'Live',
    latest: 'Latest',
    replaying: 'Replaying',
    paused: 'Paused',
    buffer: (count: number, megabytes: number, stride: number) =>
      `${count} frame${count === 1 ? '' : 's'} buffered (${num(megabytes, 1)} MB)${
        stride > 1 ? `, every ${ordinal(stride)} received frame kept` : ''
      }`,
    play: 'Play buffered frames',
    pause: 'Pause replay',
    frameAria: 'Temporal frame',
    frameAriaCompare: 'Temporal frame (temporal CA pane)',
    frame: 'Frame',
    step: 'step',
    cellsFlooded: 'cells flooded',
    volume: 'volume',
    volumeTitle: 'Volumes are summed cell depths (m), as the API reports them.',
    in: 'in',
    out: 'out',
    balance: 'balance',
    balanceTitle: "volume − (inflow − outflow): the engine's mass-conservation invariant",
    jumpLive: 'Jump to live →',
    jumpLatest: 'Jump to latest →',
  },

  log: {
    empty: "Nothing logged yet. A run's progress appears here.",
    fastLine: (q: number, flooded: number, ms: number, out: number, retained: number) =>
      `fast: Q=${num(q, 1)} m3/s, flooded=${int(flooded)} cells, engine=${int(ms)} ms, out=${num(out, 1)} retained=${num(retained, 1)} m3/s`,
    stepLine: (step: number, volume: number, elapsedMinutes: number | undefined) =>
      `step ${step}: volume=${num(volume, 4)}${elapsedMinutes !== undefined ? `, elapsed=${num(elapsedMinutes, 1)}min` : ''}`,
    temporalLine: (neighborhood: string, validated: boolean) =>
      `temporal CA: ${neighborhood} neighborhood${validated ? '' : ' (not validated)'}`,
    seededLine: (volume: number, row: number, col: number, chosen: boolean) =>
      `seeded ${upTo(volume, 1)} at row ${row}, col ${col} (${chosen ? 'the chosen location' : 'the lowest point'})`,
  },

  stream: {
    socketError: 'WebSocket error',
    runNotFound: 'Run not found (unknown or already-streamed run_id).',
    closedUnexpectedly: (code: number) => `Stream closed unexpectedly (code ${code}).`,
  },
}

function ordinal(n: number): string {
  const tens = n % 100
  if (tens >= 11 && tens <= 13) return `${n}th`
  return `${n}${['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'}`
}

export type Messages = typeof en
