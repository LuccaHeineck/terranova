import type { Resolution } from '../types/simulation'
import type { SimulationStatus } from '../hooks/useSimulationRun'
import { LOCALES, useI18n } from '../i18n'
import { RUN_SETUP_FORM_ID } from './ConfigPanel'
import { PANEL_ID } from './Sidebar'
import type { Page } from './Sidebar'
import { Popover, PopoverHeading } from './ui/Popover'
import { IconAbout, IconCheck, IconGlobe, IconPanel, IconPlay, IconStop } from './ui/icons'

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

/** The UI language, tucked behind a quiet globe button: not something to change mid-demo. `?lang=` does the same. */
function LanguageMenu() {
  const { t, locale, setLocale } = useI18n()
  return (
    <Popover label={t.topBar.language} triggerClassName={iconButton} trigger={() => <IconGlobe className="h-[18px] w-[18px]" />}>
      <PopoverHeading>{t.topBar.language}</PopoverHeading>
      <div role="radiogroup" aria-label={t.topBar.language} className="flex flex-col">
        {LOCALES.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={locale === id}
            lang={id}
            onClick={() => setLocale(id)}
            className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-sunken"
          >
            <span className="flex-1">{label}</span>
            {locale === id && <IconCheck className="h-4 w-4 text-accent" />}
          </button>
        ))}
      </div>
    </Popover>
  )
}

/** Panel toggle, wordmark, run status, About, language, and the one primary action: Start, or Stop while running. */
export function TopBar({
  status,
  gridShape,
  resolution,
  onStop,
  panelOpen,
  onTogglePanel,
  page,
  onPage,
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
        <LanguageMenu />

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
