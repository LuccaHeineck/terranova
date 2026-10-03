import { useState } from 'react'

/** The chrome's palettes (index.css). Only the chrome changes: the map's own colors stay the same in all of them. */
export type ThemeId = 'paper' | 'night' | 'basalt'

export const THEMES: { id: ThemeId; label: string; swatch: [string, string] }[] = [
  { id: 'paper', label: 'Paper', swatch: ['#f4f3ef', '#0f6b66'] },
  { id: 'night', label: 'Night', swatch: ['#0e1316', '#4fd1c0'] },
  { id: 'basalt', label: 'Basalt (original)', swatch: ['#1d2427', '#e9c23a'] },
]

const STORAGE_KEY = 'terranova.theme'
const DEFAULT_THEME: ThemeId = 'paper'

const isTheme = (id: string | null): id is ThemeId => THEMES.some((t) => t.id === id)

/**
 * A `?theme=` in the URL (to open palettes side by side), else the theme picked last time in this browser, if
 * storage is readable and the choice still exists.
 */
export function storedTheme(): ThemeId {
  const fromUrl = new URLSearchParams(window.location.search).get('theme')
  if (isTheme(fromUrl)) return fromUrl
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (isTheme(stored)) return stored
  } catch {
    // Storage blocked (private mode, site data off): fall back to the default.
  }
  return DEFAULT_THEME
}

export function applyTheme(id: ThemeId) {
  document.documentElement.dataset.theme = id
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEMES.find((t) => t.id === id)!.swatch[0])
}

export function useTheme(): [ThemeId, (id: ThemeId) => void] {
  const [theme, setTheme] = useState<ThemeId>(storedTheme)
  const select = (id: ThemeId) => {
    setTheme(id)
    applyTheme(id)
    try {
      localStorage.setItem(STORAGE_KEY, id)
    } catch {
      // Not remembered across visits, but still applied now.
    }
  }
  return [theme, select]
}
