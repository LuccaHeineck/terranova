import type { ReactNode } from 'react'

/**
 * Documented results quoted on the page (docs/project-plan.md, docs/tcc-deviations.md sections 16, 21 and 23).
 * They describe the validated May 2024 run on the 90 m grid with the Moore neighborhood, not whatever is on the
 * map; update them by hand if those results are ever re-run.
 */
export const DOCUMENTED = {
  peakStageM: 33.66,
  temporalCsi: 0.9,
  fastCsi: 0.896,
  fastSeconds: '≈ 70 ms',
  temporalMinutes: '≈ 8–24 min',
} as const

export type SectionId = 'about-problem' | 'about-model' | 'about-engines' | 'about-data' | 'about-usage' | 'about-limits'

/** Everything the About page says, in one language; AboutPage.tsx lays it out. */
export interface AboutCopy {
  kicker: string
  title: string
  lede: ReactNode
  credits: string
  openSimulator: string
  howToUse: string
  onThisPage: string
  nav: Record<SectionId, string>
  problem: ReactNode[]
  model: {
    intro: ReactNode
    stepLabel: (n: number) => string
    steps: { title: string; body: ReactNode }[]
    outro: ReactNode
  }
  engines: {
    intro: string
    csiAtPeak: string
    runTime: string
    temporal: { name: string; tagline: string; body: string }
    fast: { name: string; tagline: string; body: string }
    csi: string
  }
  data: {
    intro: string
    headers: { input: string; source: string; usedAs: string }
    rows: { what: string; source: string; use: string }[]
  }
  usage: { steps: { title: string; body: ReactNode }[]; tip: ReactNode }
  limitsTitle: string
  limits: ReactNode[]
  builtWith: string
}
