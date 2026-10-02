import type { SVGProps } from 'react'

/** A handful of 20px stroke icons, drawn inline so the app needs no icon library. */
function Icon({ children, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 20 20"
      width={20}
      height={20}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  )
}

export const IconSetup = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M4 5h12M4 10h12M4 15h12" />
    <circle cx="7" cy="5" r="1.6" fill="currentColor" />
    <circle cx="13" cy="10" r="1.6" fill="currentColor" />
    <circle cx="9" cy="15" r="1.6" fill="currentColor" />
  </Icon>
)

/** Results: a staff-gauge ruler with a water line. */
export const IconResults = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M6 3v14M6 5h3M6 8h2M6 11h3M6 14h2" />
    <path d="M11 12c1.2-1 2.3-1 3.5 0s2.3 1 3.5 0" />
  </Icon>
)

export const IconLog = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <rect x="3" y="4" width="14" height="12" rx="1.5" />
    <path d="M6 8l2 2-2 2M10 12h4" />
  </Icon>
)

export const IconPlay = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M7 5l8 5-8 5z" fill="currentColor" />
  </Icon>
)

export const IconPause = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M7 5v10M13 5v10" strokeWidth={2.4} />
  </Icon>
)

export const IconStop = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <rect x="5.5" y="5.5" width="9" height="9" rx="1" fill="currentColor" />
  </Icon>
)

export const IconWarn = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M10 3l8 14H2z" />
    <path d="M10 8v4M10 14.5v.01" />
  </Icon>
)

export const IconInfo = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <circle cx="10" cy="10" r="7" />
    <path d="M10 9v5M10 6.5v.01" />
  </Icon>
)

export const IconChevron = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M8 5l5 5-5 5" />
  </Icon>
)

export const IconClose = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M5 5l10 10M15 5L5 15" />
  </Icon>
)

/** The 3x3 neighborhood a cell flows into: 8 lit neighbors for Moore, the 4 orthogonal ones for von Neumann. */
export function NeighborhoodGlyph({ kind }: { kind: 'moore' | 'von_neumann' }) {
  const cells = []
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      const center = r === 1 && c === 1
      const orthogonal = r === 1 || c === 1
      const lit = !center && (kind === 'moore' || orthogonal)
      cells.push(
        <rect
          key={`${r}${c}`}
          x={c * 5 + 0.5}
          y={r * 5 + 0.5}
          width={4}
          height={4}
          rx={0.6}
          fill={center ? 'none' : 'currentColor'}
          stroke={center ? 'currentColor' : 'none'}
          strokeWidth={1}
          opacity={center || lit ? 1 : 0.22}
        />,
      )
    }
  }
  return (
    <svg viewBox="0 0 15 15" width={15} height={15} aria-hidden="true" className="shrink-0">
      {cells}
    </svg>
  )
}

/** About: an open book. */
export const IconAbout = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <path d="M10 5.5C8.5 4.3 6.3 4 3.5 4.3v10.4c2.8-.3 5 0 6.5 1.3 1.5-1.3 3.7-1.6 6.5-1.3V4.3C13.7 4 11.5 4.3 10 5.5z" />
    <path d="M10 5.5V16" />
  </Icon>
)

/** The side panel's edge with a chevron: points left to collapse the panel, right (rotated) to expand it. */
export const IconPanel = (props: SVGProps<SVGSVGElement>) => (
  <Icon {...props}>
    <rect x="3" y="4" width="14" height="12" rx="1.5" />
    <path d="M8 4v12M13.5 8l-2 2 2 2" />
  </Icon>
)
