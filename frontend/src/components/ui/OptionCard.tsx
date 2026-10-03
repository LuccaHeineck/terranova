import type { ReactNode } from 'react'

interface OptionCardProps {
  name: string
  checked: boolean
  disabled?: boolean
  onSelect: () => void
  title: ReactNode
  description: ReactNode
}

/** A larger radio choice with a one-line description; the selected card takes an accent edge and dot. */
export function OptionCard({ name, checked, disabled, onSelect, title, description }: OptionCardProps) {
  return (
    <label className="relative flex cursor-pointer flex-col gap-0.5 rounded-lg border border-line bg-surface px-3 py-2.5 transition-colors hover:border-ink-muted/60 has-[:checked]:border-accent has-[:checked]:ring-1 has-[:checked]:ring-accent has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent">
      <input type="radio" name={name} className="sr-only" checked={checked} disabled={disabled} onChange={onSelect} />
      <span
        aria-hidden="true"
        className={`absolute top-2.5 right-2.5 h-3.5 w-3.5 rounded-full border-2 ${
          checked ? 'border-accent bg-accent shadow-[inset_0_0_0_2px_var(--color-surface)]' : 'border-line'
        }`}
      />
      <span className="pr-5 text-[14px] font-semibold text-ink">{title}</span>
      <span className="text-xs leading-snug text-ink-muted">{description}</span>
    </label>
  )
}
