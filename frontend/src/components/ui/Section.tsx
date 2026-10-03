import type { ReactNode } from 'react'
import { IconChevron } from './icons'

interface SectionProps {
  title: ReactNode
  /** Drawn as a collapsible <details>, closed unless `defaultOpen`. */
  collapsible?: boolean
  defaultOpen?: boolean
  /** Shown after the title, e.g. a "changed" marker on a collapsed section. */
  aside?: ReactNode
  children: ReactNode
}

const frame = ''
const titleClass = 'text-[11px] font-semibold tracking-wider text-ink-muted uppercase'

/** One titled group of the sidebar under a small-caps label; the panel's gap separates the groups. */
export function Section({ title, collapsible, defaultOpen, aside, children }: SectionProps) {
  if (collapsible) {
    return (
      <details open={defaultOpen} className={`group/section ${frame}`}>
        <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded [&::-webkit-details-marker]:hidden">
          <IconChevron className="-ml-1 h-3.5 w-3.5 text-ink-muted transition-transform group-open/section:rotate-90" />
          <span className={titleClass}>{title}</span>
          {aside}
        </summary>
        <div className="mt-3 flex flex-col gap-3.5">{children}</div>
      </details>
    )
  }
  return (
    <section className={`flex flex-col gap-2.5 ${frame}`}>
      <h3 className={titleClass}>{title}</h3>
      {children}
    </section>
  )
}
