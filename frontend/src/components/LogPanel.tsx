import { useEffect, useRef } from 'react'

interface LogPanelProps {
  log: string[]
}

/** Pixels from the bottom within which the log still counts as scrolled to the end. */
const STICK_TO_BOTTOM_PX = 24

/** The Log tab: the run's log lines as a console. */
export function LogPanel({ log }: LogPanelProps) {
  const logRef = useRef<HTMLUListElement | null>(null)
  const atBottomRef = useRef(true)

  // Follow new lines, unless the user has scrolled up to read older ones.
  useEffect(() => {
    const el = logRef.current
    if (el && atBottomRef.current) el.scrollTop = el.scrollHeight
  }, [log])

  return (
    <div className="flex min-h-0 flex-1 flex-col px-4 pt-1 pb-4">
      {log.length === 0 ? (
        <p className="text-[13px] text-mist-muted">Nothing logged yet. A run's progress appears here.</p>
      ) : (
        <ul
          ref={logRef}
          onScroll={(e) => {
            const el = e.currentTarget
            atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_TO_BOTTOM_PX
          }}
          className="min-h-0 flex-1 overflow-y-auto rounded border border-basalt-line bg-[#151b1d] p-2.5 font-mono text-[11px] leading-relaxed text-mist/90"
        >
          {log.map((line, i) => (
            <li key={i} className="wrap-break-word">
              {line}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
