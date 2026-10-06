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
import { messages, num, useI18n } from '../i18n'
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
  const { common, inspector } = messages()
  if (unit === 'step') return common.step(value)
  return value < 3600 ? inspector.tMinutes(value / 60) : common.tHours(value / 3600)
}

/** What a temporal layer's times are in: seeded-pool runs have no real time, only engine steps. */
function unitOf(layer: ResultLayer): FirstWetUnit {
  return layer.mode === 'gauge_driven' ? 'seconds' : 'step'
}

function formatDepth(depth: number): string {
  return isWet(depth) ? messages().inspector.metres(depth) : messages().common.dry
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
  const { inspector } = messages()
  const grid = layer.firstWet
  if (!grid) return '—'
  const time = grid.values[cell]
  if (Number.isNaN(time)) return layer.finished ? inspector.never : inspector.drySoFar
  const shownAt = frame ? frameTime(frame, grid.unit) : Infinity
  return time > shownAt ? `${formatTime(time, grid.unit)}${inspector.later}` : formatTime(time, grid.unit)
}

function NeighborBox({ neighbor }: { neighbor: NeighborShare }) {
  const { t } = useI18n()
  if (neighbor.wall) {
    return (
      <div className="flex items-center justify-center rounded-sm border border-dashed border-line text-ink-muted">
        {t.inspector.wall}
      </div>
    )
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
        {lower ? `${ARROW[`${neighbor.dr},${neighbor.dc}`]} ${Math.round(neighbor.share * 100)}%` : t.inspector.uphill}
      </span>
      <span className="text-[10px] tabular-nums">
        {relative >= 0 ? '+' : '−'}
        {num(Math.abs(relative), 2)} m
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
  const { t } = useI18n()
  const frame = temporal?.frame ?? null
  const neighborhood = frame ? temporal!.layer.neighborhood : 'moore'
  const split = outflowSplit(inputs, frame ? frame.depth.values : null, cell.row, cell.col, neighborhood)
  const byOffset = new Map(split.neighbors.map((n) => [`${n.dr},${n.dc}`, n]))
  const onEdge = cell.row === 0 || cell.col === 0 || cell.row === inputs.rows - 1 || cell.col === inputs.cols - 1
  const outletEdge = temporal?.layer.mode === 'gauge_driven' && cell.row === inputs.rows - 1
  const wet = frame !== null && isWet(split.depth)

  return (
    <Section
      title={t.inspector.outflowTitle(NEIGHBORHOOD_LABEL[neighborhood])}
      swatch={frame ? TEMPORAL_SWATCH : undefined}
      aside={frame ? formatTime(frameTime(frame, unitOf(temporal!.layer)), unitOf(temporal!.layer)) : t.inspector.bareTerrain}
    >
      <div className="grid grid-cols-3 grid-rows-3 gap-0.5 text-[11px]" style={{ gridAutoRows: '2.6rem' }}>
        {[-1, 0, 1].flatMap((dr) =>
          [-1, 0, 1].map((dc) => {
            const key = `${dr},${dc}`
            if (dr === 0 && dc === 0) {
              return (
                <div key={key} className="flex flex-col items-center justify-center rounded-sm border border-accent leading-tight">
                  <span className="font-semibold">{t.inspector.thisCell}</span>
                  <span className="text-[10px] text-ink-muted tabular-nums">
                    {!frame ? t.inspector.noWater : wet ? t.inspector.depthH(split.depth) : t.common.dry}
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
          ? t.inspector.noLowerNeighbor
          : wet
            ? t.inspector.splitWet
            : frame
              ? t.inspector.splitDryHere
              : t.inspector.splitWouldGo}
        {!frame && fastShown && t.inspector.fastNoSplit}
        {onEdge && t.inspector.edgeWalls(outletEdge)}
      </p>
    </Section>
  )
}

/** A clicked cell's model inputs and, for each engine on screen, its state there and where its water goes. */
export function CellInspector({ cell, inputs, temporal, fast, compare, onClose }: CellInspectorProps) {
  const { t } = useI18n()
  const index = inputs ? cell.row * inputs.cols + cell.col : -1
  const landcover = inputs?.classOf(index) ?? null
  const z = inputs ? inputs.elevation[index] : 0

  return (
    <div className="float-card max-h-full w-64 overflow-y-auto rounded-xl px-3 py-2.5 text-xs text-ink">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-[13px] font-semibold">{t.inspector.title}</h2>
          <div className="text-ink-muted tabular-nums">
            {t.inspector.rowCol(cell.row, cell.col)}
            {inputs && t.inspector.gridSuffix(inputs.resolution)}
          </div>
          {compare && <div className="text-ink-muted">{t.inspector.sameCell}</div>}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={t.inspector.close}
          className="rounded p-0.5 text-ink-muted hover:bg-surface hover:text-ink"
        >
          <IconClose className="h-4 w-4" />
        </button>
      </div>
      {!inputs ? (
        <p className="mt-2 text-ink-muted">{t.inspector.loading}</p>
      ) : (
        <>
          <Section title={t.inspector.modelInputs} aside={t.inspector.bothEngines}>
            <dl className="flex flex-col gap-0.5">
              <Row label={t.inspector.elevation}>{t.inspector.metres(z)}</Row>
              <Row label={t.inspector.landCover}>
                {landcover ? (t.inspector.landCoverNames[landcover.name] ?? landcover.name) : '—'}
              </Row>
              <Row label={t.inspector.manning}>{landcover ? num(landcover.manning_n, 3) : '—'}</Row>
            </dl>
          </Section>
          {temporal?.frame && (
            <Section
              title={t.common.temporalCa}
              swatch={TEMPORAL_SWATCH}
              aside={formatTime(frameTime(temporal.frame, unitOf(temporal.layer)), unitOf(temporal.layer))}
            >
              <dl className="flex flex-col gap-0.5">
                <Row label={t.inspector.depth}>{formatDepth(temporal.frame.depth.values[index])}</Row>
                {isWet(temporal.frame.depth.values[index]) && (
                  <Row label={t.inspector.waterSurface}>{t.inspector.metres(z + temporal.frame.depth.values[index])}</Row>
                )}
                <Row label={t.inspector.firstWet}>{firstWetText(temporal.layer, temporal.frame, index)}</Row>
              </dl>
              <p className="mt-1 text-ink-muted">{t.inspector.atFrameNote}</p>
            </Section>
          )}
          {fast && (
            <Section title={t.common.fastMode} swatch={FAST_EXTENT_COLOR} aside={t.inspector.steadyPeak}>
              <dl className="flex flex-col gap-0.5">
                <Row label={t.inspector.depth}>{formatDepth(fast.depth.values[index])}</Row>
              </dl>
            </Section>
          )}
          <OutflowPanel inputs={inputs} cell={cell} temporal={temporal} fastShown={Boolean(fast)} />
        </>
      )}
    </div>
  )
}
