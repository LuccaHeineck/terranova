import type { ComponentType, ReactNode, SVGProps } from 'react'
import { IconAbout, IconClose, IconLog, IconPanel, IconResults, IconSetup } from './ui/icons'

export type SidebarTab = 'setup' | 'results' | 'log'

/** What the main area shows: the map with the selected tab's panel beside it, or the About page over it. */
export type Page = 'map' | 'about'

const TABS: { tab: SidebarTab; label: string; Icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { tab: 'setup', label: 'Setup', Icon: IconSetup },
  { tab: 'results', label: 'Results', Icon: IconResults },
  { tab: 'log', label: 'Log', Icon: IconLog },
]

/** At this width and up the panel sits beside the map; below it, it is a drawer over the map (min-[900px] below). */
export const WIDE_SCREEN_QUERY = '(min-width: 900px)'

/** A marker on a rail item: a run producing results, or an error to read. */
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
  live: 'bg-gauge motion-safe:animate-pulse',
  error: 'bg-danger',
}

const PANEL_ID = 'sidebar-panel'

interface RailButtonProps {
  label: string
  Icon: ComponentType<SVGProps<SVGSVGElement>>
  active: boolean
  badge?: RailBadge
  onClick: () => void
}

function RailButton({ label, Icon, active, badge, onClick }: RailButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
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
}

/**
 * The left menu: an icon rail and the selected tab's panel, which collapses to give the map the full width. Every
 * panel stays mounted and is only hidden, so the setup form keeps its values across tabs and the top bar's Start
 * button can always submit it. About is a page rather than a panel: it covers the map (see App).
 */
export function Sidebar({ tab, onTab, page, onPage, open, onOpenChange, badges, panels }: SidebarProps) {
  const onMap = page === 'map'
  const select = (next: SidebarTab) => {
    // From the About page any tab goes back to the map with its panel open; on the map the active item toggles
    // the panel, as in an editor's activity bar.
    onOpenChange(onMap && next === tab ? !open : true)
    onTab(next)
    onPage('map')
  }
  const title = TABS.find((t) => t.tab === tab)!.label
  const shown = onMap && open

  return (
    <>
      <nav aria-label="Panels" className="flex w-14 shrink-0 flex-col items-stretch gap-1 border-r border-basalt-line bg-basalt py-2">
        {TABS.map(({ tab: t, label, Icon }) => (
          // With the panel collapsed no tab is marked, so the rail itself shows the panel is closed.
          <RailButton key={t} label={label} Icon={Icon} active={shown && t === tab} badge={badges[t]} onClick={() => select(t)} />
        ))}

        <div className="mt-auto flex flex-col items-stretch gap-1">
          <RailButton label="About" Icon={IconAbout} active={!onMap} onClick={() => onPage(onMap ? 'about' : 'map')} />
          {onMap && (
            <button
              type="button"
              onClick={() => onOpenChange(!open)}
              aria-expanded={open}
              aria-controls={PANEL_ID}
              aria-label={open ? 'Collapse panel' : 'Expand panel'}
              title={open ? 'Collapse panel' : 'Expand panel'}
              className="mx-auto mt-1 rounded p-1.5 text-mist-muted transition-colors hover:bg-basalt-raised hover:text-mist"
            >
              <IconPanel className={`h-[18px] w-[18px] transition-transform ${open ? '' : 'rotate-180'}`} />
            </button>
          )}
        </div>
      </nav>

      <aside
        id={PANEL_ID}
        aria-label={title}
        className={`${
          shown ? 'flex' : 'hidden'
        } absolute inset-y-0 left-14 z-1100 w-[300px] flex-col border-r border-basalt-line bg-basalt shadow-2xl min-[900px]:static min-[900px]:z-auto min-[900px]:shadow-none`}
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-3">
          <h2 className="font-display text-lg font-semibold text-mist">{title}</h2>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Collapse panel"
            title="Collapse panel"
            className="rounded p-1 text-mist-muted hover:text-mist"
          >
            <IconClose className="h-4 w-4 min-[900px]:hidden" />
            <IconPanel className="hidden h-4 w-4 min-[900px]:block" />
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
