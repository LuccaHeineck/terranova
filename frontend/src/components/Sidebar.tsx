import type { ComponentType, ReactNode, SVGProps } from 'react'
import { IconClose, IconLog, IconResults, IconSetup } from './ui/icons'

export type SidebarTab = 'setup' | 'results' | 'log'

const TABS: { tab: SidebarTab; label: string; Icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { tab: 'setup', label: 'Setup', Icon: IconSetup },
  { tab: 'results', label: 'Results', Icon: IconResults },
  { tab: 'log', label: 'Log', Icon: IconLog },
]

/** A marker on a rail item: a run producing results, or an error to read. */
export type RailBadge = 'live' | 'error' | null

interface SidebarProps {
  tab: SidebarTab
  onTab: (tab: SidebarTab) => void
  /** Narrow screens only: whether the panel is drawn over the map. Wide screens always show it. */
  open: boolean
  onOpenChange: (open: boolean) => void
  badges: Partial<Record<SidebarTab, RailBadge>>
  panels: Record<SidebarTab, ReactNode>
}

const BADGE_CLASS: Record<Exclude<RailBadge, null>, string> = {
  live: 'bg-gauge motion-safe:animate-pulse',
  error: 'bg-danger',
}

/**
 * The left menu: an icon rail and the selected tab's panel. Every panel stays mounted and is only hidden, so
 * the setup form keeps its values across tabs and the top bar's Start button can always submit it.
 */
export function Sidebar({ tab, onTab, open, onOpenChange, badges, panels }: SidebarProps) {
  const select = (next: SidebarTab) => {
    // On a narrow screen the active item toggles the drawer; elsewhere it opens it on that tab.
    onOpenChange(next === tab ? !open : true)
    onTab(next)
  }
  const title = TABS.find((t) => t.tab === tab)!.label

  return (
    <>
      <nav aria-label="Panels" className="flex w-14 shrink-0 flex-col items-stretch gap-1 border-r border-basalt-line bg-basalt py-2">
        {TABS.map(({ tab: t, label, Icon }) => {
          const active = t === tab
          const badge = badges[t]
          return (
            <button
              key={t}
              type="button"
              onClick={() => select(t)}
              aria-current={active ? 'page' : undefined}
              className={`relative flex flex-col items-center gap-0.5 py-2 text-[11px] transition-colors ${
                active ? 'text-mist' : 'text-mist-muted hover:text-mist'
              }`}
            >
              <span
                aria-hidden="true"
                className={`absolute inset-y-1.5 left-0 w-0.5 rounded-r ${active ? 'bg-gauge' : 'bg-transparent'}`}
              />
              <span className="relative">
                <Icon />
                {badge && (
                  <span
                    aria-hidden="true"
                    className={`absolute -top-0.5 -right-1 h-2 w-2 rounded-full ring-2 ring-basalt ${BADGE_CLASS[badge]}`}
                  />
                )}
              </span>
              {label}
              {badge && <span className="sr-only">{badge === 'error' ? ' (error)' : ' (run in progress)'}</span>}
            </button>
          )
        })}
      </nav>

      <aside
        aria-label={title}
        className={`${
          open ? 'flex' : 'hidden'
        } absolute inset-y-0 left-14 z-1100 w-[300px] flex-col border-r border-basalt-line bg-basalt shadow-2xl min-[900px]:static min-[900px]:z-auto min-[900px]:flex min-[900px]:shadow-none`}
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-3">
          <h2 className="font-display text-lg font-semibold text-mist">{title}</h2>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Close panel"
            className="rounded p-1 text-mist-muted hover:text-mist min-[900px]:hidden"
          >
            <IconClose className="h-4 w-4" />
          </button>
        </div>
        {TABS.map(({ tab: t }) => (
          <div key={t} hidden={t !== tab} className="flex min-h-0 flex-1 flex-col">
            {panels[t]}
          </div>
        ))}
      </aside>
    </>
  )
}
