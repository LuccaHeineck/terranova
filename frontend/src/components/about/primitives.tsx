import type { ReactNode } from 'react'

/** A UI control's name as the app labels it, so the instructions read like the screen. */
export function Ui({ children }: { children: ReactNode }) {
  return (
    <span className="rounded bg-surface px-1.5 py-px font-medium whitespace-nowrap text-ink">{children}</span>
  )
}

export function Formula({ children }: { children: ReactNode }) {
  return <code className="rounded bg-sunken px-1.5 py-px font-mono whitespace-nowrap text-[12.5px] text-accent">{children}</code>
}

export function Strong({ children }: { children: ReactNode }) {
  return <strong className="font-semibold text-ink">{children}</strong>
}
