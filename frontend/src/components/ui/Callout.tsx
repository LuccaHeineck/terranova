import type { ReactNode } from 'react'
import { IconInfo, IconWarn } from './icons'

interface CalloutProps {
  tone: 'info' | 'warn' | 'error'
  id?: string
  children: ReactNode
}

const TONE = {
  info: { frame: 'border-mist-muted bg-basalt-raised', icon: 'text-mist-muted', Icon: IconInfo },
  warn: { frame: 'border-ochre bg-ochre/10', icon: 'text-ochre', Icon: IconWarn },
  error: { frame: 'border-danger bg-danger/10', icon: 'text-danger', Icon: IconWarn },
} as const

/** A note with a colored edge and icon, so its tone never rests on color alone. */
export function Callout({ tone, id, children }: CalloutProps) {
  const { frame, icon, Icon } = TONE[tone]
  return (
    <div
      id={id}
      role={tone === 'error' ? 'alert' : undefined}
      className={`flex gap-2 rounded border-l-2 px-2.5 py-2 text-xs leading-snug text-mist ${frame}`}
    >
      <Icon className={`mt-px h-4 w-4 shrink-0 ${icon}`} />
      <div className="min-w-0">{children}</div>
    </div>
  )
}
