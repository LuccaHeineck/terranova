import { useId } from 'react'
import type { ReactNode } from 'react'

interface NumberFieldProps {
  label: string
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  /** The input's own `step` (what the browser validates against). */
  step?: number | 'any'
  /** How far the -/+ buttons move the value. */
  stepBy?: number
  unit?: string
  disabled?: boolean
  /** The id of a hint elsewhere that describes this field. */
  describedBy?: string
  /** A hint under the field. */
  children?: ReactNode
}

export const fieldBoxClass =
  'rounded-md border border-line bg-surface px-2 py-1 text-[13px] text-ink tabular-nums transition-colors hover:border-ink-muted focus-visible:border-accent disabled:cursor-not-allowed disabled:opacity-50'

const stepperClass =
  'flex w-7 items-center justify-center text-base text-ink-muted transition-colors hover:bg-sunken hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent'

/** A labelled number box between -/+ steppers. */
export function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  stepBy = 1,
  unit,
  disabled,
  describedBy,
  children,
}: NumberFieldProps) {
  const id = useId()
  const nudge = (direction: 1 | -1) => {
    let next = value + direction * stepBy
    if (min !== undefined) next = Math.max(min, next)
    if (max !== undefined) next = Math.min(max, next)
    onChange(next)
  }
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-[13px] font-medium text-ink">
          {label}
        </label>
        <div className="flex h-7 overflow-hidden rounded-md border border-line bg-surface">
          <button
            type="button"
            onClick={() => nudge(-1)}
            disabled={disabled || (min !== undefined && value <= min)}
            aria-label={`Decrease ${label.toLowerCase()}`}
            className={stepperClass}
          >
            −
          </button>
          <div className="flex items-center border-x border-line">
            <input
              id={id}
              type="number"
              min={min}
              max={max}
              step={step}
              value={value}
              disabled={disabled}
              onChange={(e) => onChange(Number(e.target.value))}
              aria-describedby={describedBy}
              className="w-16 bg-transparent px-1.5 text-right text-[13px] text-ink tabular-nums outline-none disabled:opacity-50"
            />
            {unit && <span className="pr-1.5 text-xs text-ink-muted">{unit}</span>}
          </div>
          <button
            type="button"
            onClick={() => nudge(1)}
            disabled={disabled || (max !== undefined && value >= max)}
            aria-label={`Increase ${label.toLowerCase()}`}
            className={stepperClass}
          >
            +
          </button>
        </div>
      </div>
      {children}
    </div>
  )
}
