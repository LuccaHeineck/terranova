import { DEPTH_BANDS, FAST_EXTENT_COLOR, FLOODED_DEPTH_THRESHOLD_M } from './depthToImage'
import { arrivalBandLabel } from './arrivalTime'
import type { ArrivalBand } from './arrivalTime'
import type { FirstWetUnit } from './firstWet'
import { AGREEMENT_COLORS } from './observed'
import type { SnapshotLegend } from './mapSnapshot'

// The on-map legends as data, for the exported PNG (rendering/mapSnapshot.ts). Same colors and labels as the
// React legend components, which stay the source for the screen.

export function depthLegendSpec(title = 'Water depth (m)', note?: string): SnapshotLegend {
  return {
    title,
    items: [...DEPTH_BANDS].reverse().map(({ min, max, color }) => ({
      color,
      label: max === null ? `≥ ${min}` : `${min}–${max}`,
    })),
    note: `Under ${FLOODED_DEPTH_THRESHOLD_M} m: dry${note ? `. ${note}` : ''}`,
  }
}

export function arrivalLegendSpec(bands: readonly ArrivalBand[], unit: FirstWetUnit): SnapshotLegend {
  return {
    title: unit === 'seconds' ? 'First flooded (h into the event)' : 'First flooded (engine step)',
    items: bands.map((band) => ({ color: band.color, label: arrivalBandLabel(band, unit) })),
    note: 'Darker: reached sooner.',
  }
}

export function extentLegendSpec(): SnapshotLegend {
  return {
    title: 'Fast mode',
    items: [{ color: FAST_EXTENT_COLOR, label: `Flooded (depth > ${FLOODED_DEPTH_THRESHOLD_M} m)` }],
    note: 'Extent only.',
  }
}

export function agreementLegendSpec(stageM: number): SnapshotLegend {
  return {
    title: 'Against the observed flood',
    items: [
      { color: AGREEMENT_COLORS.hit, label: 'Hit: flooded in both' },
      { color: AGREEMENT_COLORS.missed, label: 'Missed: observed only' },
      { color: AGREEMENT_COLORS.falseAlarm, label: 'False alarm: simulated only' },
      { color: AGREEMENT_COLORS.notScored, label: 'Not scored: reference gap' },
    ],
    note: `SGB/CPRM extent at the ${stageM.toFixed(2)} m peak stage.`,
  }
}
