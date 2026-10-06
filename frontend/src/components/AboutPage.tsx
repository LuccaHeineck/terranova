import { useRef } from 'react'
import type { ReactNode } from 'react'
import { num, useI18n } from '../i18n'
import type { Locale } from '../i18n'
import { aboutEn } from './about/copy.en'
import { aboutPtBR } from './about/copy.pt-BR'
import { DOCUMENTED } from './about/content'
import type { AboutCopy, SectionId } from './about/content'

const COPY: Record<Locale, AboutCopy> = { en: aboutEn, 'pt-BR': aboutPtBR }

const SECTION_IDS: SectionId[] = [
  'about-problem',
  'about-model',
  'about-engines',
  'about-data',
  'about-usage',
  'about-limits',
]

function AboutSection({ id, title, children }: { id: SectionId; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-6 border-t border-line pt-8">
      <h2 id={`${id}-title`} className="mb-4 font-serif text-[34px] leading-tight text-ink">
        {title}
      </h2>
      <div className="flex flex-col gap-4 text-[15px] leading-relaxed text-ink/85">{children}</div>
    </section>
  )
}

function RuleStep({ label, title, children }: { label: string; title: string; children: ReactNode }) {
  return (
    <li className="flex flex-col gap-1.5 rounded-xl border border-line bg-surface p-4">
      <span className="font-display text-xs font-semibold tracking-wide text-accent uppercase">{label}</span>
      <span className="font-display text-base font-semibold text-ink">{title}</span>
      <div className="text-sm leading-relaxed text-ink/80">{children}</div>
    </li>
  )
}

interface EngineCardProps {
  name: string
  tagline: string
  stats: { label: string; value: string }[]
  children: ReactNode
}

function EngineCard({ name, tagline, stats, children }: EngineCardProps) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-5">
      <div>
        <h3 className="font-display text-lg font-semibold text-ink">{name}</h3>
        <p className="text-sm text-ink-muted">{tagline}</p>
      </div>
      <div className="text-sm leading-relaxed text-ink/80">{children}</div>
      <dl className="mt-auto grid grid-cols-2 gap-3 border-t border-line pt-3">
        {stats.map(({ label, value }) => (
          <div key={label}>
            <dt className="text-xs text-ink-muted">{label}</dt>
            <dd className="font-serif text-3xl leading-tight text-ink tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function UsageStep({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <li className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3">
      <span
        aria-hidden="true"
        className="flex h-7 w-7 items-center justify-center rounded-full border border-accent font-display text-sm font-semibold text-accent"
      >
        {n}
      </span>
      <div className="flex flex-col gap-1">
        <h3 className="font-display text-lg font-semibold text-ink">{title}</h3>
        <div>{children}</div>
      </div>
    </li>
  )
}

interface AboutPageProps {
  /** Back to the map. */
  onClose: () => void
}

/** The project's introduction and user guide, shown in place of the map from the top bar's About button. */
export function AboutPage({ onClose }: AboutPageProps) {
  const { locale } = useI18n()
  const c = COPY[locale]
  const scrollRef = useRef<HTMLDivElement | null>(null)
  // Scroll the page's own container rather than following a #hash link, which would change the app's URL.
  const goTo = (id: SectionId) =>
    scrollRef.current?.querySelector(`#${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto bg-canvas">
      <article className="mx-auto flex max-w-[860px] flex-col gap-10 px-4 py-10 sm:px-8 sm:py-14">
        <header className="flex flex-col gap-5">
          <span className="font-display text-xs font-semibold tracking-[0.18em] text-accent uppercase">{c.kicker}</span>
          <h1 className="font-serif text-5xl leading-[1.05] text-ink sm:text-6xl">{c.title}</h1>
          <p className="max-w-[68ch] text-lg leading-relaxed text-ink/85">{c.lede}</p>
          <p className="text-sm text-ink-muted">{c.credits}</p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-canvas transition-colors hover:bg-accent-strong"
            >
              {c.openSimulator}
            </button>
            <button
              type="button"
              onClick={() => goTo('about-usage')}
              className="rounded-lg border border-ink-muted px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-ink hover:bg-surface"
            >
              {c.howToUse}
            </button>
          </div>
          <nav aria-label={c.onThisPage} className="flex flex-wrap gap-x-4 gap-y-1.5 pt-2 text-sm">
            {SECTION_IDS.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => goTo(id)}
                className="text-ink-muted underline-offset-4 hover:text-ink hover:underline"
              >
                {c.nav[id]}
              </button>
            ))}
          </nav>
        </header>

        <AboutSection id="about-problem" title={c.nav['about-problem']}>
          {c.problem.map((paragraph, i) => (
            <p key={i}>{paragraph}</p>
          ))}
        </AboutSection>

        <AboutSection id="about-model" title={c.nav['about-model']}>
          <p>{c.model.intro}</p>
          <ol className="grid gap-3 sm:grid-cols-3">
            {c.model.steps.map(({ title, body }, i) => (
              <RuleStep key={title} label={c.model.stepLabel(i + 1)} title={title}>
                {body}
              </RuleStep>
            ))}
          </ol>
          <p>{c.model.outro}</p>
        </AboutSection>

        <AboutSection id="about-engines" title={c.nav['about-engines']}>
          <p>{c.engines.intro}</p>
          <div className="grid gap-4 md:grid-cols-2">
            <EngineCard
              name={c.engines.temporal.name}
              tagline={c.engines.temporal.tagline}
              stats={[
                { label: c.engines.csiAtPeak, value: num(DOCUMENTED.temporalCsi, 2) },
                { label: c.engines.runTime, value: DOCUMENTED.temporalMinutes },
              ]}
            >
              {c.engines.temporal.body}
            </EngineCard>
            <EngineCard
              name={c.engines.fast.name}
              tagline={c.engines.fast.tagline}
              stats={[
                { label: c.engines.csiAtPeak, value: num(DOCUMENTED.fastCsi, 3) },
                { label: c.engines.runTime, value: DOCUMENTED.fastSeconds },
              ]}
            >
              {c.engines.fast.body}
            </EngineCard>
          </div>
          <p>{c.engines.csi}</p>
        </AboutSection>

        <AboutSection id="about-data" title={c.nav['about-data']}>
          <p>{c.data.intro}</p>
          <div className="overflow-hidden rounded-xl border border-line">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface text-xs text-ink-muted">
                <tr>
                  <th scope="col" className="px-4 py-2.5 font-medium">{c.data.headers.input}</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">{c.data.headers.source}</th>
                  <th scope="col" className="hidden px-4 py-2.5 font-medium sm:table-cell">{c.data.headers.usedAs}</th>
                </tr>
              </thead>
              <tbody>
                {c.data.rows.map(({ what, source, use }) => (
                  <tr key={what} className="border-t border-line align-top">
                    <th scope="row" className="px-4 py-3 font-display font-semibold whitespace-nowrap text-ink">
                      {what}
                    </th>
                    <td className="px-4 py-3 text-ink/80">
                      {source}
                      <span className="mt-1 block text-ink-muted sm:hidden">{use}</span>
                    </td>
                    <td className="hidden px-4 py-3 text-ink/80 sm:table-cell">{use}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AboutSection>

        <AboutSection id="about-usage" title={c.nav['about-usage']}>
          <ol className="flex flex-col gap-5">
            {c.usage.steps.map(({ title, body }, i) => (
              <UsageStep key={title} n={i + 1} title={title}>
                {body}
              </UsageStep>
            ))}
          </ol>
          <p className="text-sm text-ink-muted">{c.usage.tip}</p>
        </AboutSection>

        <AboutSection id="about-limits" title={c.limitsTitle}>
          <ul className="flex list-disc flex-col gap-2 pl-5 marker:text-ink-muted">
            {c.limits.map((limit, i) => (
              <li key={i}>{limit}</li>
            ))}
          </ul>
        </AboutSection>

        <footer className="flex flex-col gap-3 border-t border-line pt-8 text-sm text-ink-muted">
          <p>{c.builtWith}</p>
          <button
            type="button"
            onClick={onClose}
            className="self-start rounded-lg border border-accent px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-accent hover:text-canvas"
          >
            {c.openSimulator}
          </button>
        </footer>
      </article>
    </div>
  )
}
