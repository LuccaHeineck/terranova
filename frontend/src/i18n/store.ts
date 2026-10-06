/**
 * The UI language, as a tiny external store: React components subscribe through useI18n (i18n/index.ts), and
 * plain modules (log lines, export legends, notices) read it at call time.
 */
export type Locale = 'en' | 'pt-BR'

export const LOCALES: { id: Locale; label: string; short: string }[] = [
  { id: 'en', label: 'English', short: 'EN' },
  { id: 'pt-BR', label: 'Português (Brasil)', short: 'PT' },
]

const STORAGE_KEY = 'terranova.lang'

function parse(value: string | null): Locale | null {
  if (!value) return null
  const v = value.toLowerCase()
  if (v === 'en' || v.startsWith('en-')) return 'en'
  if (v === 'pt' || v.startsWith('pt-')) return 'pt-BR'
  return null
}

/** A `?lang=` in the URL (en, pt, pt-BR), else the language picked last time in this browser, else English. */
function initialLocale(): Locale {
  const fromUrl = parse(new URLSearchParams(window.location.search).get('lang'))
  if (fromUrl) return fromUrl
  try {
    return parse(localStorage.getItem(STORAGE_KEY)) ?? 'en'
  } catch {
    // Storage blocked (private mode, site data off): fall back to English.
    return 'en'
  }
}

let current: Locale = initialLocale()
document.documentElement.lang = current
const listeners = new Set<() => void>()

export function getLocale(): Locale {
  return current
}

export function setLocale(locale: Locale) {
  if (locale === current) return
  current = locale
  document.documentElement.lang = locale
  try {
    localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    // Not remembered across visits, but still applied now.
  }
  for (const listener of listeners) listener()
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
