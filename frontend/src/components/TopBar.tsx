import type { Resolution } from '../types/simulation'
import type { SimulationStatus } from '../hooks/useSimulationRun'
import { LOCALES, useI18n } from '../i18n'
import { THEMES } from '../theme'
import type { ThemeId } from '../theme'
import { RUN_SETUP_FORM_ID } from './ConfigPanel'
import { PANEL_ID } from './Sidebar'
import type { Page } from './Sidebar'
import { Popover, PopoverHeading } from './ui/Popover'
import { IconAbout, IconCheck, IconPanel, IconPlay, IconStop, IconTheme } from './ui/icons'

interface TopBarProps {
  status: SimulationStatus
  gridShape: [number, number] | null
  /** The grid the shown result ran on, if any. */
  resolution: Resolution | null
  onStop: () => void
  /** Whether the side panel is shown (it is always hidden under the About page). */
  panelOpen: boolean
  onTogglePanel: () => void
  page: Page
  onPage: (page: Page) => void
  theme: ThemeId
  onTheme: (theme: ThemeId) => void
}

// Idle says nothing worth a pill: the status only shows once a run has started.
const STATUS_DOT: Record<Exclude<SimulationStatus, 'idle'>, string> = {
  starting: 'bg-live motion-safe:animate-pulse',
  streaming: 'bg-live motion-safe:animate-pulse',
  done: 'bg-accent',
  stopped: 'bg-ink-muted',
  error: 'bg-danger',
}

const iconButton =
  'flex h-9 w-9 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-sunken hover:text-ink'

/**
 * Theme and, tucked under it, the language: a quiet menu behind the half-circle icon, since neither is something
 * to change mid-demo. `?theme=` and `?lang=` in the URL do the same.
 */
function DisplayMenu({ theme, onTheme }: { theme: ThemeId; onTheme: (theme: ThemeId) => void }) {
  const { t, locale, setLocale } = useI18n()
  return (
    <Popover label={t.topBar.display} triggerClassName={iconButton} trigger={() => <IconTheme className="h-[18px] w-[18px]" />}>
      <PopoverHeading>{t.topBar.theme}</PopoverHeading>
      <div role="radiogroup" aria-label={t.topBar.theme} className="flex flex-col">
        {THEMES.map(({ id, swatch: [bg, accent] }) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={theme === id}
            onClick={() => onTheme(id)}
            className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-sunken"
          >
            <span
              aria-hidden="true"
              className="h-4 w-4 shrink-0 rounded-full ring-1 ring-line"
              style={{ background: `linear-gradient(135deg, ${bg} 0 50%, ${accent} 50% 100%)` }}
            />
            <span className="flex-1">{t.topBar.themes[id]}</span>
            {theme === id && <IconCheck className="h-4 w-4 text-accent" />}
          </button>
        ))}
      </div>
      <div className="mx-2 mt-1 flex items-center justify-between gap-3 border-t border-line pt-2 pb-1">
        <span className="text-[11px] text-ink-muted">{t.topBar.language}</span>
        <div role="radiogroup" aria-label={t.topBar.language} className="flex gap-0.5 text-[11px]">
          {LOCALES.map(({ id, label, short }) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={locale === id}
              aria-label={label}
              title={label}
              lang={id}
              onClick={() => setLocale(id)}
              className={`rounded px-1.5 py-0.5 font-semibold tracking-wide transition-colors ${
                locale === id ? 'bg-sunken text-ink' : 'text-ink-muted hover:text-ink'
              }`}
            >
              {short}
            </button>
          ))}
        </div>
      </div>
    </Popover>
  )
}

/** Panel toggle, wordmark, run status, About, display, and the one primary action: Start, or Stop while running. */
export function TopBar({
  status,
  gridShape,
  resolution,
  onStop,
  panelOpen,
  onTogglePanel,
  page,
  onPage,
  theme,
  onTheme,
}: TopBarProps) {
  const { t } = useI18n()
  const busy = status === 'starting' || status === 'streaming'
  const shownStatus = status === 'idle' ? null : { label: t.topBar.status[status], dot: STATUS_DOT[status] }

  return (
    <header className="flex items-center gap-2 px-2 sm:gap-3 sm:px-3">
      <button
        type="button"
        onClick={onTogglePanel}
        aria-expanded={panelOpen}
        aria-controls={PANEL_ID}
        aria-label={panelOpen ? t.topBar.hidePanel : t.topBar.showPanel}
        title={panelOpen ? t.topBar.hidePanel : t.topBar.showPanel}
        className={iconButton}
      >
        <IconPanel className={`h-[18px] w-[18px] transition-transform ${panelOpen ? '' : 'rotate-180'}`} />
      </button>

      <div className="flex min-w-0 items-baseline gap-3">
        <span className="font-serif text-[26px] leading-none text-ink">Terranova</span>
        <span className="hidden truncate text-[13px] text-ink-muted lg:inline">{t.topBar.tagline}</span>
      </div>

      <div className="ml-auto flex items-center gap-1.5 text-[13px] sm:gap-2">
        {gridShape && resolution && (
          <span className="mr-1 hidden text-ink-muted tabular-nums xl:inline">
            {t.topBar.gridInfo(gridShape[0], gridShape[1], resolution)}
          </span>
        )}
        {shownStatus && (
          <span role="status" className="flex items-center gap-2 rounded-full bg-surface px-2.5 py-1 text-ink ring-1 ring-line">
            <span aria-hidden="true" className={`h-2 w-2 rounded-full ${shownStatus.dot}`} />
            {shownStatus.label}
          </span>
        )}

        <button
          type="button"
          onClick={() => onPage(page === 'about' ? 'map' : 'about')}
          aria-pressed={page === 'about'}
          className={`flex h-9 items-center gap-1.5 rounded-lg px-2.5 font-medium transition-colors ${
            page === 'about' ? 'bg-sunken text-ink' : 'text-ink-muted hover:bg-sunken hover:text-ink'
          }`}
        >
          <IconAbout className="h-[18px] w-[18px]" />
          <span className="hidden sm:inline">{t.topBar.about}</span>
        </button>
        <DisplayMenu theme={theme} onTheme={onTheme} />

        {/* Distinct keys: if React reused one <button> and flipped its type from "button" to "submit"
            during the Stop click, the click's default action would submit the form and start a new run. */}
        {busy ? (
          <button
            key="stop"
            type="button"
            onClick={onStop}
            className="ml-1 flex h-9 items-center gap-1.5 rounded-lg bg-surface px-3.5 font-semibold text-ink ring-1 ring-line transition-colors hover:bg-sunken"
          >
            <IconStop className="h-4 w-4 text-danger" />
            {t.topBar.stop}
          </button>
        ) : (
          <button
            key="start"
            type="submit"
            form={RUN_SETUP_FORM_ID}
            className="ml-1 flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3.5 font-semibold text-canvas shadow-sm transition-colors hover:bg-accent-strong"
          >
            <IconPlay className="h-4 w-4" />
            <span>
              {t.topBar.start}
              <span className="hidden sm:inline">{t.topBar.startSuffix}</span>
            </span>
          </button>
        )}
      </div>
    </header>
  )
}
