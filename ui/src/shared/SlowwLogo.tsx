/**
 * Sloww AI logo — the three interweaving S-curves
 * Each instance gets a unique gradient ID to avoid SVG conflicts.
 */
let _uid = 0

export function SlowwLogo({ size = 28, className = '' }: { size?: number; className?: string }) {
  const id = `sGrad-${++_uid}`

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="15 15 75 90"
      className={className}
      aria-label="Sloww AI"
    >
      <defs>
        <linearGradient id={id} x1="0%" y1="100%" x2="100%" y2="0%" gradientTransform="rotate(45)">
          <stop offset="0%" stopColor="#fff" />
        </linearGradient>
      </defs>
      <g stroke={`url(#${id})`} fill="none" strokeWidth="5" strokeLinecap="butt">
        <path d="M 82.6 34 A 24 24 0 0 0 36 42 C 36 60, 68 60, 68 78 A 8 8 0 0 1 60 86" />
        <path d="M 73.86 34 A 16 16 0 0 0 44 42 C 44 60, 76 60, 76 78 A 16 16 0 0 1 46.14 86" />
        <path d="M 60 34 A 8 8 0 0 0 52 42 C 52 60, 84 60, 84 78 A 24 24 0 0 1 37.4 86" />
      </g>
    </svg>
  )
}
