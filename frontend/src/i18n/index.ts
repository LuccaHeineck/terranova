import { useSyncExternalStore } from 'react'
import { en } from './en'
import type { Messages } from './en'
import { ptBR } from './pt-BR'
import { getLocale, setLocale, subscribe } from './store'
import type { Locale } from './store'

export { exp, int, num, upTo } from './format'
export { getLocale, LOCALES, setLocale } from './store'
export type { Locale } from './store'
export type { Messages } from './en'

const MESSAGES: Record<Locale, Messages> = { en, 'pt-BR': ptBR }

/** The current language's strings, for code outside React (log lines, export legends, notices). */
export function messages(): Messages {
  return MESSAGES[getLocale()]
}

/** The current language's strings; the component re-renders when the language changes. */
export function useI18n(): { locale: Locale; t: Messages; setLocale: (locale: Locale) => void } {
  const locale = useSyncExternalStore(subscribe, getLocale)
  return { locale, t: MESSAGES[locale], setLocale }
}
