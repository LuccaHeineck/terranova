import type { Resolution } from '../types/simulation'
import type { SimulationStatus } from '../hooks/useSimulationRun'
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
const STATUS: Record<Exclude<SimulationStatus, 'idle'>, { label: string; dot: string }> = {
  starting: { label: 'Starting…', dot: 'bg-live motion-safe:animate-pulse' },
  streaming: { label: 'Running', dot: 'bg-live motion-safe:animate-pulse' },
  done: { label: 'Done', dot: 'bg-accent' },
  stopped: { label: 'Stopped', dot: 'bg-ink-muted' },
  error: { label: 'Error', dot: 'bg-danger' },
}

const iconButton =
  'flex h-9 w-9 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-sunken hover:text-ink'

function ThemePicker({ theme, onTheme }: { theme: ThemeId; onTheme: (theme: ThemeId) => void }) {
  return (
    <Popover label="Theme" triggerClassName={iconButton} trigger={() => <IconTheme className="h-[18px] w-[18px]" />}>
      <PopoverHeading>Theme</PopoverHeading>
      <div role="radiogroup" aria-label="Theme" className="flex flex-col">
        {THEMES.map(({ id, label, swatch: [bg, accent] }) => (
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
            <span className="flex-1">{label}</span>
            {theme === id && <IconCheck className="h-4 w-4 text-accent" />}
          </button>
        ))}
      </div>
    </Popover>
  )
}

/** Panel toggle, wordmark, run status, About, theme, and the one primary action: Start, or Stop while running. */
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
  const busy = status === 'starting' || status === 'streaming'
  const shownStatus = status === 'idle' ? null : STATUS[status]

  return (
    <header className="flex items-center gap-2 px-2 sm:gap-3 sm:px-3">
      <button
        type="button"
        onClick={onTogglePanel}
        aria-expanded={panelOpen}
        aria-controls={PANEL_ID}
        aria-label={panelOpen ? 'Hide panel' : 'Show panel'}
        title={panelOpen ? 'Hide panel' : 'Show panel'}
        className={iconButton}
      >
        <IconPanel className={`h-[18px] w-[18px] transition-transform ${panelOpen ? '' : 'rotate-180'}`} />
      </button>

      <div className="flex min-w-0 items-baseline gap-3">
        <span className="font-serif text-[26px] leading-none text-ink">Terranova</span>
        <span className="hidden truncate text-[13px] text-ink-muted lg:inline">Flood simulation · Vale do Taquari</span>
      </div>

      <div className="ml-auto flex items-center gap-1.5 text-[13px] sm:gap-2">
        {gridShape && resolution && (
          <span className="mr-1 hidden text-ink-muted tabular-nums xl:inline">
            {gridShape[0].toLocaleString('en-US')} × {gridShape[1].toLocaleString('en-US')} cells · {resolution} m
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
          <span className="hidden sm:inline">About</span>
        </button>
        <ThemePicker theme={theme} onTheme={onTheme} />

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
            Stop
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
              Start<span className="hidden sm:inline"> simulation</span>
            </span>
          </button>
        )}
      </div>
    </header>
  )
}
