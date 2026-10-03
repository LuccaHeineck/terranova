import type { ReactNode } from 'react'

export interface SegmentOption<T extends string | number> {
  value: T
  label: ReactNode
  /** A short second line under the label. */
  caption?: ReactNode
  /** 'warn' draws the caption in the warning color (while not selected), for options that are not validated. */
  captionTone?: 'muted' | 'warn'
}

interface SegmentedProps<T extends string | number> {
  /** The radio group's name; native radios give the group arrow-key navigation. */
  name: string
  label: string
  value: T
  options: readonly SegmentOption<T>[]
  onChange: (value: T) => void
  disabled?: boolean
}

/** A row of mutually exclusive choices: native radios, visually hidden, under segment-styled labels. */
export function Segmented<T extends string | number>({ name, label, value, options, onChange, disabled }: SegmentedProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="grid gap-0.5 rounded-lg bg-sunken p-0.5"
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      {options.map((option) => (
        <label
          key={option.value}
          className="group/seg relative flex cursor-pointer flex-col items-center justify-center rounded-md px-2 py-1.5 text-center text-ink-muted transition-colors hover:text-ink has-[:checked]:bg-surface has-[:checked]:text-ink has-[:checked]:shadow-sm has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-accent"
        >
          <input
            type="radio"
            name={name}
            className="sr-only"
            checked={value === option.value}
            disabled={disabled}
            onChange={() => onChange(option.value)}
          />
          <span className="flex items-center gap-1.5 text-[13px] font-medium">{option.label}</span>
          {option.caption && (
            <span
              className={`text-[11px] leading-tight group-has-[:checked]/seg:text-ink-muted ${
                option.captionTone === 'warn' ? 'text-warn' : 'text-ink-muted'
              }`}
            >
              {option.caption}
            </span>
          )}
        </label>
      ))}
    </div>
  )
}
