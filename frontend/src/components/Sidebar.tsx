import type { ComponentType, ReactNode, SVGProps } from 'react'
import { useI18n } from '../i18n'
import { IconClose, IconLog, IconResults, IconSetup } from './ui/icons'

export type SidebarTab = 'setup' | 'results' | 'log'

/** What the main area shows: the map with the selected tab's panel beside it, or the About page over it. */
export type Page = 'map' | 'about'

const TABS: { tab: SidebarTab; Icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { tab: 'setup', Icon: IconSetup },
  { tab: 'results', Icon: IconResults },
  { tab: 'log', Icon: IconLog },
]

/** At this width and up the panel sits beside the map; below it, it is a drawer over the map (min-[900px] below). */
export const WIDE_SCREEN_QUERY = '(min-width: 900px)'

/** A marker on a tab: a run producing results, or an error to read. */
export type RailBadge = 'live' | 'error' | null

interface SidebarProps {
  tab: SidebarTab
  onTab: (tab: SidebarTab) => void
  page: Page
  onPage: (page: Page) => void
  /** Whether the panel is shown: beside the map on a wide screen, as a drawer over it on a narrow one. */
  open: boolean
  onOpenChange: (open: boolean) => void
  badges: Partial<Record<SidebarTab, RailBadge>>
  panels: Record<SidebarTab, ReactNode>
}

const BADGE_CLASS: Record<Exclude<RailBadge, null>, string> = {
  live: 'bg-live motion-safe:animate-pulse',
  error: 'bg-danger',
}

/** The panel's id: the top bar's toggle controls it. */
export const PANEL_ID = 'sidebar-panel'

/**
 * The left panel: a tab strip over the selected tab's content. The top bar's toggle collapses it to give the map
 * the full width. Every panel stays mounted and is only hidden, so the setup form keeps its values across tabs
 * and the top bar's Start button can always submit it. About is a page rather than a panel: it covers the map
 * (see App).
 */
export function Sidebar({ tab, onTab, page, onPage, open, onOpenChange, badges, panels }: SidebarProps) {
  const { t } = useI18n()
  const shown = page === 'map' && open
  const select = (next: SidebarTab) => {
    onTab(next)
    onPage('map')
    onOpenChange(true)
  }

  return (
    <aside
      id={PANEL_ID}
      aria-label={t.sidebar.panels}
      className={`${
        shown ? 'flex' : 'hidden'
      } absolute inset-y-0 left-0 z-1100 w-[320px] max-w-[calc(100vw-1rem)] flex-col rounded-r-xl bg-canvas shadow-2xl min-[900px]:static min-[900px]:z-auto min-[900px]:shrink-0 min-[900px]:rounded-none min-[900px]:shadow-none`}
    >
      <div className="flex items-center gap-1 px-3 pt-1 pb-3">
        <div role="tablist" aria-label={t.sidebar.panels} className="grid flex-1 grid-cols-3 gap-0.5 rounded-lg bg-sunken p-0.5">
          {TABS.map(({ tab: id, Icon }) => {
            const active = id === tab
            const badge = badges[id]
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => select(id)}
                className={`flex items-center justify-center gap-1.5 rounded-md py-1.5 text-[13px] font-medium transition-colors ${
                  active ? 'bg-surface text-ink shadow-sm' : 'text-ink-muted hover:text-ink'
                }`}
              >
                <span className="relative">
                  <Icon className="h-4 w-4" />
                  {badge && (
                    <span
                      aria-hidden="true"
                      className={`absolute -top-0.5 -right-1 h-2 w-2 rounded-full ring-2 ring-sunken ${BADGE_CLASS[badge]}`}
                    />
                  )}
                </span>
                {t.sidebar.tabs[id]}
                {badge && <span className="sr-only">{badge === 'error' ? t.sidebar.badgeError : t.sidebar.badgeLive}</span>}
              </button>
            )
          })}
        </div>
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          aria-label={t.sidebar.closePanel}
          className="rounded-lg p-1.5 text-ink-muted hover:bg-sunken hover:text-ink min-[900px]:hidden"
        >
          <IconClose className="h-4 w-4" />
        </button>
      </div>
      {TABS.map(({ tab: id }) => (
        <div key={id} role="tabpanel" hidden={id !== tab} className="flex min-h-0 flex-1 flex-col">
          {panels[id]}
        </div>
      ))}
    </aside>
  )
}
