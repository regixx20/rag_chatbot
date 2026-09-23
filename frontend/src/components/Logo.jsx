export function Logo({ size = 28 }) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="logo-gradient" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="var(--logo-from)" />
          <stop offset="1" stopColor="var(--logo-to)" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#logo-gradient)" />
      {/* Stacked pages + spark: documents feeding the answer */}
      <rect x="8" y="10" width="11" height="14" rx="2.2" fill="none" stroke="#fff" strokeOpacity=".55" strokeWidth="1.6" />
      <rect x="11" y="7.5" width="11" height="14" rx="2.2" fill="#fff" fillOpacity=".18" stroke="#fff" strokeWidth="1.6" />
      <path d="M22.5 17.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z" fill="#fff" />
    </svg>
  )
}
