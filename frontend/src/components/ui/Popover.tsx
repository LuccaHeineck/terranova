import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'

interface PopoverProps {
  /** The trigger's content; `open` lets it reflect the state (a rotated chevron, a pressed look). */
  trigger: (open: boolean) => ReactNode
  /** Accessible name of the trigger, when its content is only an icon. */
  label?: string
  triggerClassName: string
  /** Which edge of the trigger the panel lines up with. */
  align?: 'left' | 'right'
  /** Opens above the trigger instead of below it. */
  above?: boolean
  children: ReactNode
}

/** A button that opens a small floating panel; closes on Escape or on a click anywhere outside it. */
export function Popover({ trigger, label, triggerClassName, align = 'right', above = false, children }: PopoverProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const panelId = useId()

  useEffect(() => {
    if (!open) return
    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className={triggerClassName}
      >
        {trigger(open)}
      </button>
      {open && (
        <div
          id={panelId}
          className={`float-card absolute z-1200 min-w-56 rounded-xl p-1.5 text-ink ${align === 'right' ? 'right-0' : 'left-0'} ${
            above ? 'bottom-full mb-2' : 'top-full mt-2'
          }`}
        >
          {children}
        </div>
      )}
    </div>
  )
}

/** A small caps heading inside a popover. */
export function PopoverHeading({ children }: { children: ReactNode }) {
  return <div className="px-2 pt-1.5 pb-1 text-[11px] font-semibold tracking-wider text-ink-muted uppercase">{children}</div>
}
