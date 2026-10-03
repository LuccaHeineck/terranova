import { useEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent } from 'react'
import type { HydrographRecord } from '../types/simulation'
import { DEPTH_BANDS } from '../rendering/depthToImage'

interface HydrographChartProps {
  record: HydrographRecord
  /** Where the timeline is, in seconds since the record's start; null draws no marker (no gauge-driven frame). */
  markerSeconds: number | null
}

const HEIGHT = 150
const MARGIN = { top: 18, right: 10, bottom: 22, left: 40 }
// The ramp's lightest blue: the series is water, and it clears the dark chrome easily.
const SERIES_COLOR = DEPTH_BANDS[0].color
const X_TICK_HOURS = 48

/** Discharge at `seconds`, linearly interpolated like the backend's Hydrograph.discharge_at. */
function dischargeAt({ elapsed_seconds: t, discharge_m3s: q }: HydrographRecord, seconds: number): number {
  if (seconds <= t[0]) return q[0]
  if (seconds >= t[t.length - 1]) return q[q.length - 1]
  let lo = 0
  let hi = t.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (t[mid] <= seconds) lo = mid
    else hi = mid
  }
  return q[lo] + ((q[hi] - q[lo]) * (seconds - t[lo])) / (t[hi] - t[lo])
}

/** Round y-axis ticks (1/2/5 x 10^k steps) from 0 up to the first one at or above `max`, so the curve fits. */
function yTicks(max: number): number[] {
  const raw = max / 4
  const power = 10 ** Math.floor(Math.log10(raw))
  const step = ([1, 2, 5, 10].find((m) => m * power >= raw) ?? 10) * power
  const ticks = [0]
  while (ticks[ticks.length - 1] < max) ticks.push(ticks.length * step)
  return ticks
}

function kilo(value: number): string {
  return value >= 1000 ? `${value / 1000}k` : `${value}`
}

function hours(seconds: number): string {
  return `${(seconds / 3600).toFixed(1)} h`
}

function m3s(value: number): string {
  return `${Math.round(value).toLocaleString('en-US')} m³/s`
}

/**
 * The real May 2024 discharge record at the Estrela gauge, with a marker where the timeline is. One series, so no
 * legend box: the section title names it. Hovering reads off any point of the record.
 */
export function HydrographChart({ record, markerSeconds }: HydrographChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [width, setWidth] = useState(280)
  const [hoverSeconds, setHoverSeconds] = useState<number | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width)))
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  const duration = record.elapsed_seconds[record.elapsed_seconds.length - 1]
  const ticks = useMemo(() => yTicks(record.peak_discharge_m3s), [record])
  const yMax = ticks[ticks.length - 1]
  const plotW = width - MARGIN.left - MARGIN.right
  const plotH = HEIGHT - MARGIN.top - MARGIN.bottom
  const x = (seconds: number) => MARGIN.left + (seconds / duration) * plotW
  const y = (q: number) => MARGIN.top + plotH - (q / yMax) * plotH

  const path = useMemo(() => {
    const sx = (seconds: number) => MARGIN.left + (seconds / duration) * plotW
    const sy = (q: number) => MARGIN.top + plotH - (q / yMax) * plotH
    return record.elapsed_seconds
      .map((t, i) => `${i ? 'L' : 'M'}${sx(t).toFixed(1)},${sy(record.discharge_m3s[i]).toFixed(1)}`)
      .join('')
  }, [record, duration, plotW, plotH, yMax])

  const xTicks: number[] = []
  for (let h = 0; h * 3600 <= duration; h += X_TICK_HOURS) xTicks.push(h)

  const onPointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const px = event.clientX - box.left
    const seconds = ((px - MARGIN.left) / plotW) * duration
    setHoverSeconds(seconds < 0 || seconds > duration ? null : seconds)
  }

  const marker = markerSeconds !== null && markerSeconds <= duration ? markerSeconds : null
  const readout = hoverSeconds ?? marker
  const peakX = x(record.peak_elapsed_seconds)

  return (
    <div ref={containerRef} className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2 text-xs tabular-nums" aria-live="polite">
        <span className="text-ink-muted">{hoverSeconds !== null ? 'At cursor' : marker !== null ? 'At the timeline' : 'Peak'}</span>
        <span className="text-ink">
          {readout !== null
            ? `t = ${hours(readout)} · ${m3s(dischargeAt(record, readout))}`
            : `t = ${hours(record.peak_elapsed_seconds)} · ${m3s(record.peak_discharge_m3s)}`}
        </span>
      </div>
      <svg
        width={width}
        height={HEIGHT}
        role="img"
        aria-label={`Discharge at the Estrela gauge over ${hours(duration)}, peaking at ${m3s(record.peak_discharge_m3s)} at t = ${hours(record.peak_elapsed_seconds)}`}
        className="touch-none select-none"
        onPointerMove={onPointerMove}
        onPointerLeave={() => setHoverSeconds(null)}
      >
        {ticks.map((q) => (
          <g key={q}>
            <line x1={MARGIN.left} x2={width - MARGIN.right} y1={y(q)} y2={y(q)} className="stroke-line" strokeWidth={1} />
            <text x={MARGIN.left - 6} y={y(q)} dy="0.32em" textAnchor="end" className="fill-ink-muted text-[10px]">
              {kilo(q)}
            </text>
          </g>
        ))}
        {xTicks.map((h) => (
          <text key={h} x={x(h * 3600)} y={HEIGHT - 6} textAnchor="middle" className="fill-ink-muted text-[10px]">
            {h} h
          </text>
        ))}
        <text x={MARGIN.left - 6} y={MARGIN.top - 8} textAnchor="end" className="fill-ink-muted text-[10px]">
          m³/s
        </text>

        <line x1={peakX} x2={peakX} y1={MARGIN.top} y2={MARGIN.top + plotH} className="stroke-ink-muted" strokeDasharray="2 3" />
        <text x={peakX} y={MARGIN.top - 6} textAnchor={peakX > width - 50 ? 'end' : 'middle'} className="fill-ink-muted text-[10px]">
          peak
        </text>

        <path d={path} fill="none" stroke={SERIES_COLOR} strokeWidth={2} strokeLinejoin="round" />

        {marker !== null && (
          <g>
            <line x1={x(marker)} x2={x(marker)} y1={MARGIN.top} y2={MARGIN.top + plotH} className="stroke-accent" strokeWidth={2} />
            <circle
              cx={x(marker)}
              cy={y(dischargeAt(record, marker))}
              r={4.5}
              className="fill-accent stroke-canvas"
              strokeWidth={2}
            />
          </g>
        )}
        {hoverSeconds !== null && (
          <g pointerEvents="none">
            <line x1={x(hoverSeconds)} x2={x(hoverSeconds)} y1={MARGIN.top} y2={MARGIN.top + plotH} className="stroke-ink" strokeWidth={1} />
            <circle
              cx={x(hoverSeconds)}
              cy={y(dischargeAt(record, hoverSeconds))}
              r={4}
              fill={SERIES_COLOR}
              className="stroke-canvas"
              strokeWidth={2}
            />
          </g>
        )}
      </svg>
      <p className="text-xs leading-snug text-ink-muted">
        Station {record.station_code}, Porto Fluvial de Estrela: ANA's discharge, from the stage record through the
        station's own rating pairs. Peak {m3s(record.peak_discharge_m3s)} at t = {hours(record.peak_elapsed_seconds)}.
        {marker !== null && ' The vertical marker follows the timeline.'}
      </p>
    </div>
  )
}
