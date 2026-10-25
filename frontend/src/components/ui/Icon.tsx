/** A small inline icon set (24px grid, 1.75 stroke) - no icon-font dependency. */
const PATHS = {
  check: 'M5 12.5l4.5 4.5L19 7.5',
  alert:
    'M12 8v5m0 3.5v.01M10.3 3.9L2.6 17.3A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.7L13.7 3.9a2 2 0 0 0-3.4 0z',
  info: 'M12 11v6m0-9.5v.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z',
  x: 'M6 6l12 12M18 6L6 18',
  sun: 'M12 4V2m0 20v-2m8-8h2M2 12h2m13.66-5.66l1.41-1.41M4.93 19.07l1.41-1.41m0-11.32L4.93 4.93m14.14 14.14l-1.41-1.41M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z',
  moon: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z',
  book: 'M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2V5zm0 14a2 2 0 0 1 2-2h13',
  download: 'M12 4v11m0 0l-4.5-4.5M12 15l4.5-4.5M5 20h14',
  chevronLeft: 'M15 6l-6 6 6 6',
  chevronRight: 'M9 6l6 6-6 6',
  arrowRight: 'M5 12h14m-5-5l5 5-5 5',
  clock: 'M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0z',
  table: 'M3 5h18v14H3zM3 10h18M3 15h18M9 5v14',
  menu: 'M4 7h16M4 12h16M4 17h16',
} as const

export type IconName = keyof typeof PATHS

export function Icon({
  name,
  size = 18,
  label,
}: {
  name: IconName
  size?: number
  label?: string
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
