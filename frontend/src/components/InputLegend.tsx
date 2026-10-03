import { INPUT_OVERLAY_OPACITY, roughnessColors, TERRAIN_GRADIENT } from '../rendering/inputsToImage'
import type { ModelInputs } from '../rendering/modelInputs'

/** Key for the terrain layer: its elevation ramp between the grid's lowest and highest cell. */
export function TerrainLegend({ inputs }: { inputs: ModelInputs }) {
  return (
    <div className="w-52 float-card rounded-xl px-3 py-2.5 text-xs text-ink">
      <div className="mb-2 text-[13px] font-semibold">Terrain Z (m)</div>
      {/* On a white backing, so the ramp shows as composited over the light map. */}
      <div className="rounded-sm bg-white p-px">
        <div
          className="h-3 rounded-[1px]"
          style={{
            background: `linear-gradient(to right, ${TERRAIN_GRADIENT.join(', ')})`,
            opacity: INPUT_OVERLAY_OPACITY.terrain,
          }}
        />
      </div>
      <div className="mt-0.5 flex justify-between tabular-nums">
        <span>{inputs.minElevation.toFixed(0)}</span>
        <span>{inputs.maxElevation.toFixed(0)}</span>
      </div>
      <div className="mt-1 text-[10.5px] leading-snug text-ink-muted">
        The model's own sink-filled DEM at {inputs.resolution} m, shaded from the north-west: one pixel per cell.
      </div>
    </div>
  )
}

/** Key for the roughness layer: one row per Manning's n on the grid, naming the land-cover classes that take it. */
export function RoughnessLegend({ inputs }: { inputs: ModelInputs }) {
  const byN = new Map<number, string[]>()
  for (const { manning_n, name } of inputs.classes) byN.set(manning_n, [...(byN.get(manning_n) ?? []), name])
  const rows = [...byN.entries()].sort(([a], [b]) => b - a)
  const colors = roughnessColors(inputs)
  return (
    <div className="w-60 float-card rounded-xl px-3 py-2.5 text-xs text-ink">
      <div className="mb-2 text-[13px] font-semibold">Manning's n (roughness)</div>
      <ul className="flex flex-col gap-1">
        {rows.map(([n, names]) => (
          <li key={n} className="flex items-start gap-2">
            <span className="mt-px inline-flex shrink-0 rounded-sm bg-white p-px">
              <span
                className="inline-block h-3 w-5 rounded-[1px]"
                style={{ background: colors.get(n), opacity: INPUT_OVERLAY_OPACITY.roughness }}
              />
            </span>
            <span className="w-9 shrink-0 tabular-nums">{n.toFixed(3)}</span>
            <span className="text-ink-muted">{names.join(', ')}</span>
          </li>
        ))}
      </ul>
      <div className="mt-1.5 text-[10.5px] leading-snug text-ink-muted">
        MapBiomas 2024 land cover. Darker slows the water more; one shade per value, in order, not to scale.
      </div>
    </div>
  )
}
