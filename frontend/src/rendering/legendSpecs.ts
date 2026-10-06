import { DEPTH_BANDS, FAST_EXTENT_COLOR, FLOODED_DEPTH_THRESHOLD_M } from './depthToImage'
import { arrivalBandLabel } from './arrivalTime'
import type { ArrivalBand } from './arrivalTime'
import type { FirstWetUnit } from './firstWet'
import { AGREEMENT_COLORS } from './observed'
import type { SnapshotLegend } from './mapSnapshot'
import { messages, upTo } from '../i18n'

// The on-map legends as data, for the exported PNG (rendering/mapSnapshot.ts). Same colors and labels as the
// React legend components, which stay the source for the screen.

// Band edges as short numbers in the UI language: 0.15 / 0,15, and 2 rather than 2.00.
const edge = (value: number) => upTo(value, 2)

export function depthLegendSpec(title?: string, note?: string): SnapshotLegend {
  const { legends } = messages()
  return {
    title: title ?? legends.exportDepth,
    items: [...DEPTH_BANDS].reverse().map(({ min, max, color }) => ({
      color,
      label: max === null ? `≥ ${edge(min)}` : `${edge(min)}–${edge(max)}`,
    })),
    note: `${legends.exportDry(FLOODED_DEPTH_THRESHOLD_M)}${note ? `. ${note}` : ''}`,
  }
}

export function arrivalLegendSpec(bands: readonly ArrivalBand[], unit: FirstWetUnit): SnapshotLegend {
  return {
    title: unit === 'seconds' ? messages().legends.arrivalHours : messages().legends.arrivalSteps,
    items: bands.map((band) => ({ color: band.color, label: arrivalBandLabel(band, unit) })),
    note: messages().legends.exportArrivalNote,
  }
}

export function extentLegendSpec(): SnapshotLegend {
  return {
    title: messages().common.fastMode,
    items: [{ color: FAST_EXTENT_COLOR, label: messages().legends.fastFlooded(FLOODED_DEPTH_THRESHOLD_M) }],
    note: messages().legends.exportExtentOnly,
  }
}

export function agreementLegendSpec(stageM: number): SnapshotLegend {
  const { legends } = messages()
  return {
    title: legends.agreement,
    items: [
      { color: AGREEMENT_COLORS.hit, label: legends.hit },
      { color: AGREEMENT_COLORS.missed, label: legends.missed },
      { color: AGREEMENT_COLORS.falseAlarm, label: legends.falseAlarm },
      { color: AGREEMENT_COLORS.notScored, label: legends.notScored },
    ],
    note: legends.observedNote(stageM),
  }
}
