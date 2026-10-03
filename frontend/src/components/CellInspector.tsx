import type { ReactNode } from 'react'
import type { Cell } from '../geo/cell'
import type { ResultLayer } from '../hooks/useSimulationRun'
import type { CompactFrame } from '../rendering/depthGrid'
import { DEPTH_BANDS, FAST_EXTENT_COLOR, isWet } from '../rendering/depthToImage'
import { frameTime } from '../rendering/firstWet'
import type { FirstWetUnit } from '../rendering/firstWet'
import type { ModelInputs } from '../rendering/modelInputs'
import { isNeighbor, outflowSplit } from '../rendering/outflowShares'
import type { NeighborShare } from '../rendering/outflowShares'
import { NEIGHBORHOOD_LABEL } from '../types/simulation'
import { IconClose } from './ui/icons'

interface CellInspectorProps {
  cell: Cell
  /** The grid's static inputs; null while they load. */
  inputs: ModelInputs | null
  /** The temporal layer and the timeline's frame, while the temporal pane is on screen. */
  temporal: { layer: ResultLayer; frame: CompactFrame | null } | null
  /** The fast layer's frame, while the fast pane is on screen. */
  fast: CompactFrame | null
  /** Both panes are on screen: the cell is the same one in each, outlined in both. */
  compare: boolean
  onClose: () => void
}

// The swatches mark which pane a section's numbers come from, in that pane's own overlay color.
const TEMPORAL_SWATCH = DEPTH_BANDS[2].color

const ARROW: Record<string, string> = {
  '-1,-1': '↖',
  '-1,0': '↑',
  '-1,1': '↗',
  '0,-1': '←',
  '0,1': '→',
  '1,-1': '↙',
  '1,0': '↓',
  '1,1': '↘',
}

function formatTime(value: number, unit: FirstWetUnit): string {
  if (unit === 'step') return `step ${value}`
  return value < 3600 ? `t = ${(value / 60).toFixed(0)} min` : `t = ${(value / 3600).toFixed(1)} h`
}

/** What a temporal layer's times are in: seeded-pool runs have no real time, only engine steps. */
function unitOf(layer: ResultLayer): FirstWetUnit {
  return layer.mode === 'gauge_driven' ? 'seconds' : 'step'
}

function formatDepth(depth: number): string {
  return isWet(depth) ? `${depth.toFixed(2)} m` : 'dry'
}

/** A label/value row of a definition list. */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-right text-ink tabular-nums">{children}</dd>
    </div>
  )
}

/** One source of numbers about the cell, under a heading that says which (with its pane's color, if any). */
function Section({ title, swatch, aside, children }: { title: string; swatch?: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-2 border-t border-line pt-1.5">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-[13px] font-semibold">
          {swatch && <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: swatch }} />}
          {title}
        </h3>
        {aside && <span className="text-ink-muted tabular-nums">{aside}</span>}
      </div>
      {children}
    </section>
  )
}

function firstWetText(layer: ResultLayer, frame: CompactFrame | null, cell: number): string {
  const grid = layer.firstWet
  if (!grid) return '—'
  const time = grid.values[cell]
  if (Number.isNaN(time)) return layer.finished ? 'never' : 'dry so far'
  const shownAt = frame ? frameTime(frame, grid.unit) : Infinity
  return time > shownAt ? `${formatTime(time, grid.unit)} (later)` : formatTime(time, grid.unit)
}

function NeighborBox({ neighbor }: { neighbor: NeighborShare }) {
  if (neighbor.wall) {
    return <div className="flex items-center justify-center rounded-sm border border-dashed border-line text-ink-muted">wall</div>
  }
  const lower = neighbor.share > 0
  // The neighbor's water surface relative to this cell's: negative is lower, where water can go.
  const relative = -neighbor.drop
  return (
    <div
      className={`flex flex-col items-center justify-center rounded-sm leading-tight ${
        lower ? (neighbor.share > 0.45 ? 'text-canvas' : 'text-ink') : 'bg-sunken text-ink-muted'
      }`}
      style={lower ? { background: `color-mix(in srgb, var(--color-accent) ${Math.round(18 + 75 * neighbor.share)}%, transparent)` } : undefined}
    >
      <span className="font-semibold">
        {lower ? `${ARROW[`${neighbor.dr},${neighbor.dc}`]} ${Math.round(neighbor.share * 100)}%` : 'uphill'}
      </span>
      <span className="text-[10px] tabular-nums">
        {relative >= 0 ? '+' : '−'}
        {Math.abs(relative).toFixed(2)} m
      </span>
    </div>
  )
}

/**
 * The inspected cell's outflow split among its neighbors - the temporal CA's transition rule, drawn as the
 * neighborhood itself: each lower neighbor's share, and every neighbor's water surface relative to this cell's.
 * Only the temporal CA moves water cell to cell, so with no temporal frame on screen it is the rule applied to
 * bare terrain (the fast engine fills a steady rating-curve stage instead).
 */
function OutflowPanel({
  inputs,
  cell,
  temporal,
  fastShown,
}: {
  inputs: ModelInputs
  cell: Cell
  temporal: CellInspectorProps['temporal']
  fastShown: boolean
}) {
  const frame = temporal?.frame ?? null
  const neighborhood = frame ? temporal!.layer.neighborhood : 'moore'
  const split = outflowSplit(inputs, frame ? frame.depth.values : null, cell.row, cell.col, neighborhood)
  const byOffset = new Map(split.neighbors.map((n) => [`${n.dr},${n.dc}`, n]))
  const onEdge = cell.row === 0 || cell.col === 0 || cell.row === inputs.rows - 1 || cell.col === inputs.cols - 1
  const outletEdge = temporal?.layer.mode === 'gauge_driven' && cell.row === inputs.rows - 1
  const wet = frame !== null && isWet(split.depth)

  return (
    <Section
      title={`Outflow split · ${NEIGHBORHOOD_LABEL[neighborhood]}`}
      swatch={frame ? TEMPORAL_SWATCH : undefined}
      aside={frame ? formatTime(frameTime(frame, unitOf(temporal!.layer)), unitOf(temporal!.layer)) : 'bare terrain'}
    >
      <div className="grid grid-cols-3 grid-rows-3 gap-0.5 text-[11px]" style={{ gridAutoRows: '2.6rem' }}>
        {[-1, 0, 1].flatMap((dr) =>
          [-1, 0, 1].map((dc) => {
            const key = `${dr},${dc}`
            if (dr === 0 && dc === 0) {
              return (
                <div key={key} className="flex flex-col items-center justify-center rounded-sm border border-accent leading-tight">
                  <span className="font-semibold">this cell</span>
                  <span className="text-[10px] text-ink-muted tabular-nums">
                    {!frame ? 'no water' : wet ? `h ${split.depth.toFixed(2)} m` : 'dry'}
                  </span>
                </div>
              )
            }
            const neighbor = byOffset.get(key)
            if (!neighbor || !isNeighbor(dr, dc, neighborhood)) return <div key={key} />
            return <NeighborBox key={key} neighbor={neighbor} />
          }),
        )}
      </div>
      <p className="mt-1.5 text-ink-muted">
        {!split.flows
          ? 'No lower neighbor: water here stays put (a pit or a flat water surface).'
          : wet
            ? 'Each lower neighbor gets √(drop / distance) / n of the receiving cell, normalized, at the temporal frame shown. The engine re-weighs it on every sub-step.'
            : frame
              ? 'Dry here at the temporal frame shown: where water arriving would go, by √(drop / distance) / n of the receiving cell.'
              : 'Where water arriving here would go under the temporal CA, by √(drop / distance) / n of the receiving cell.'}
        {!frame && fastShown && ' The fast engine has no such split: it fills a steady stage per river reach instead.'}
        {onEdge && ` Off-grid neighbors are walls${outletEdge ? ' (the gauge-driven south outlet is not shown)' : ''}.`}
      </p>
    </Section>
  )
}

/** A clicked cell's model inputs and, for each engine on screen, its state there and where its water goes. */
export function CellInspector({ cell, inputs, temporal, fast, compare, onClose }: CellInspectorProps) {
  const index = inputs ? cell.row * inputs.cols + cell.col : -1
  const landcover = inputs?.classOf(index) ?? null
  const z = inputs ? inputs.elevation[index] : 0

  return (
    <div className="float-card max-h-full w-64 overflow-y-auto rounded-xl px-3 py-2.5 text-xs text-ink">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-[13px] font-semibold">Cell inspector</h2>
          <div className="text-ink-muted tabular-nums">
            row {cell.row}, col {cell.col}
            {inputs && ` · ${inputs.resolution} m grid`}
          </div>
          {compare && <div className="text-ink-muted">The same cell in both panes, outlined in each.</div>}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close the cell inspector"
          className="rounded p-0.5 text-ink-muted hover:bg-surface hover:text-ink"
        >
          <IconClose className="h-4 w-4" />
        </button>
      </div>
      {!inputs ? (
        <p className="mt-2 text-ink-muted">Loading the grid's terrain and land cover…</p>
      ) : (
        <>
          <Section title="Model inputs" aside="both engines">
            <dl className="flex flex-col gap-0.5">
              <Row label="Elevation Z">{z.toFixed(2)} m</Row>
              <Row label="Land cover">{landcover?.name ?? '—'}</Row>
              <Row label="Manning's n">{landcover ? landcover.manning_n.toFixed(3) : '—'}</Row>
            </dl>
          </Section>
          {temporal?.frame && (
            <Section
              title="Temporal CA"
              swatch={TEMPORAL_SWATCH}
              aside={formatTime(frameTime(temporal.frame, unitOf(temporal.layer)), unitOf(temporal.layer))}
            >
              <dl className="flex flex-col gap-0.5">
                <Row label="Depth">{formatDepth(temporal.frame.depth.values[index])}</Row>
                {isWet(temporal.frame.depth.values[index]) && (
                  <Row label="Water surface">{(z + temporal.frame.depth.values[index]).toFixed(2)} m</Row>
                )}
                <Row label="First wet">{firstWetText(temporal.layer, temporal.frame, index)}</Row>
              </dl>
              <p className="mt-1 text-ink-muted">At the timeline's frame. First wet is exact to one frame interval.</p>
            </Section>
          )}
          {fast && (
            <Section title="Fast mode" swatch={FAST_EXTENT_COLOR} aside="steady peak">
              <dl className="flex flex-col gap-0.5">
                <Row label="Depth">{formatDepth(fast.depth.values[index])}</Row>
              </dl>
            </Section>
          )}
          <OutflowPanel inputs={inputs} cell={cell} temporal={temporal} fastShown={Boolean(fast)} />
        </>
      )}
    </div>
  )
}
