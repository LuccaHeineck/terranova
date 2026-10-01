import type { ReactNode } from 'react'

interface OptionCardProps {
  name: string
  checked: boolean
  disabled?: boolean
  onSelect: () => void
  title: ReactNode
  description: ReactNode
}

/** A larger radio choice with a one-line description; the selected card takes a gauge-yellow edge. */
export function OptionCard({ name, checked, disabled, onSelect, title, description }: OptionCardProps) {
  return (
    <label className="relative flex cursor-pointer flex-col gap-0.5 rounded-md border border-basalt-line bg-basalt-raised py-2 pr-2.5 pl-3.5 transition-colors hover:border-mist-muted has-[:checked]:border-gauge has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-gauge">
      <input type="radio" name={name} className="sr-only" checked={checked} disabled={disabled} onChange={onSelect} />
      <span
        aria-hidden="true"
        className={`absolute inset-y-1.5 left-1 w-1 rounded-full ${checked ? 'bg-gauge' : 'bg-transparent'}`}
      />
      <span className="font-display text-[15px] font-semibold text-mist">{title}</span>
      <span className="text-xs leading-snug text-mist-muted">{description}</span>
    </label>
  )
}
