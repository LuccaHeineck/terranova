import { useId } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { fieldBoxClass } from './NumberField'

interface SliderMark {
  value: number
  label: string
}

interface SliderFieldProps {
  label: string
  value: number
  onChange: (value: number) => void
  min: number
  max: number
  /** 'log' spreads a wide range (1 to 10,000) so its small end is still reachable by dragging. */
  scale?: 'linear' | 'log'
  /** Slider values snap to multiples of this, so they stay valid for the number box's `step`. */
  quantum: number
  /** The number box's own `step`. */
  inputStep: number | 'any'
  marks?: readonly SliderMark[]
  unit?: string
  disabled?: boolean
  describedBy?: string
  /** A readout or hint under the slider. */
  children?: ReactNode
}

/** Slider positions run 0..RESOLUTION; the value is mapped onto them linearly or logarithmically. */
const RESOLUTION = 1000

function decimalsOf(quantum: number): number {
  return (String(quantum).split('.')[1] ?? '').length
}

/** A slider and an editable number box for the same value. */
export function SliderField({
  label,
  value,
  onChange,
  min,
  max,
  scale = 'linear',
  quantum,
  inputStep,
  marks = [],
  unit,
  disabled,
  describedBy,
  children,
}: SliderFieldProps) {
  const id = useId()
  const fractionOf = (v: number) => {
    const clamped = Math.min(max, Math.max(min, v))
    return scale === 'log' ? Math.log(clamped / min) / Math.log(max / min) : (clamped - min) / (max - min)
  }
  const valueAt = (position: number) => {
    const f = position / RESOLUTION
    const raw = scale === 'log' ? min * (max / min) ** f : min + (max - min) * f
    const snapped = Math.min(max, Math.max(min, Math.round(raw / quantum) * quantum))
    return Number(snapped.toFixed(decimalsOf(quantum)))
  }
  const fraction = fractionOf(value)

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-[13px] font-medium text-mist">
          {label}
        </label>
        <div className="flex items-center gap-1">
          <input
            id={id}
            type="number"
            min={min}
            max={max}
            step={inputStep}
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(Number(e.target.value))}
            aria-describedby={describedBy}
            className={`${fieldBoxClass} h-7 w-20 text-right`}
          />
          {unit && <span className="text-xs text-mist-muted">{unit}</span>}
        </div>
      </div>
      <div className={`relative ${marks.length ? 'pb-3.5' : ''}`}>
        <input
          type="range"
          min={0}
          max={RESOLUTION}
          value={Math.round(fraction * RESOLUTION)}
          disabled={disabled}
          onChange={(e) => onChange(valueAt(Number(e.target.value)))}
          aria-label={label}
          aria-valuetext={`${value}${unit ? ` ${unit}` : ''}`}
          className="range w-full"
          style={{ '--fill': `${fraction * 100}%` } as CSSProperties}
        />
        {marks
          .filter((mark) => mark.value >= min && mark.value <= max)
          .map((mark) => {
            const f = fractionOf(mark.value)
            return (
              <span
                key={mark.label}
                aria-hidden="true"
                className="absolute bottom-0 flex flex-col items-center text-[10px] leading-none text-mist-muted"
                // Track ends sit half a thumb (7px) in from the input's edges.
                style={{
                  left: `calc(7px + (100% - 14px) * ${f})`,
                  transform: f > 0.9 ? 'translateX(-100%)' : 'translateX(-50%)',
                }}
              >
                {mark.label}
              </span>
            )
          })}
      </div>
      {children}
    </div>
  )
}
