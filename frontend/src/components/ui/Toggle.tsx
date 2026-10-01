import type { ReactNode } from 'react'

interface ToggleProps {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  children: ReactNode
}

/** An on/off switch: a native checkbox with switch semantics, drawn as a track and knob. */
export function Toggle({ checked, onChange, disabled, children }: ToggleProps) {
  return (
    <label className="relative flex cursor-pointer items-center justify-between gap-3 has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50">
      <span className="text-[13px] font-medium text-mist">{children}</span>
      <input
        type="checkbox"
        role="switch"
        className="peer sr-only"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span
        aria-hidden="true"
        className="relative h-5 w-9 shrink-0 rounded-full bg-basalt-line transition-colors peer-checked:bg-gauge peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-gauge after:absolute after:top-0.5 after:left-0.5 after:h-4 after:w-4 after:rounded-full after:bg-mist after:transition-transform peer-checked:after:translate-x-4 peer-checked:after:bg-basalt"
      />
    </label>
  )
}
