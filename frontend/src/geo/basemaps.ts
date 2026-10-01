/**
 * The map's background choices. Each is a base tile layer, optionally a hillshade multiplied over it (so the
 * Taquari's valley walls and ridges read as terrain), and optionally a labels layer drawn above the flood
 * overlay so place names stay readable through it. The flood overlay itself never changes with the basemap.
 */

export type BasemapId = 'relief' | 'topo' | 'streets' | 'satellite'

export interface TileSpec {
  url: string
  attribution: string
  subdomains?: string
  /** The deepest zoom the server has tiles for; Leaflet upscales them beyond it. */
  maxNativeZoom?: number
}

export interface Basemap {
  id: BasemapId
  label: string
  base: TileSpec
  /** Esri's hillshade multiplied over the base, at this opacity. */
  relief?: { opacity: number }
  labels?: TileSpec
}

const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

export const HILLSHADE: TileSpec = {
  url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}',
  attribution: 'Hillshade &copy; <a href="https://www.esri.com/">Esri</a>',
  maxNativeZoom: 16,
}

export const BASEMAPS: Record<BasemapId, Basemap> = {
  // A near-white base leaves the hillshade alone to model the terrain, at full strength; the depth ramp's blues
  // stand out against its greys. (A CSS contrast boost on the hillshade was tried and washes it out: its flat
  // tone is mid-grey, so contrast pushes most of the shading to white.)
  relief: {
    id: 'relief',
    label: 'Relief',
    base: {
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
      attribution: 'Base &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors',
      maxNativeZoom: 16,
    },
    relief: { opacity: 1 },
    labels: {
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
      attribution: 'Labels &copy; Esri',
      maxNativeZoom: 16,
    },
  },
  // OpenTopoMap: contour lines and its own SRTM shading, already baked in.
  topo: {
    id: 'topo',
    label: 'Topographic',
    base: {
      url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
      attribution: `${OSM_ATTRIBUTION}, SRTM | Style &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)`,
      subdomains: 'abc',
      maxNativeZoom: 17,
    },
  },
  // Standard OSM, the tiles the depth ramp (rendering/depthToImage.ts) was designed against, with a lighter
  // hillshade so streets and place names stay readable.
  streets: {
    id: 'streets',
    label: 'Streets',
    base: { url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', attribution: OSM_ATTRIBUTION },
    relief: { opacity: 0.7 },
  },
  satellite: {
    id: 'satellite',
    label: 'Satellite',
    base: {
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics',
      maxNativeZoom: 18,
    },
    labels: {
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      attribution: 'Labels &copy; Esri',
      maxNativeZoom: 18,
    },
  },
}

export const DEFAULT_BASEMAP: BasemapId = 'relief'
