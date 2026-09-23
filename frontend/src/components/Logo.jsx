export function Logo({ size = 28 }) {
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      {/* A page with text lines, and a lens picking one of them: search inside documents */}
      <path d="M9 7.5h9l5 5v12a1.5 1.5 0 0 1-1.5 1.5h-12A1.5 1.5 0 0 1 8 24.5v-15.5A1.5 1.5 0 0 1 9 7.5z" fill="none" stroke="#fff" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M11.5 14h7M11.5 17.5h4.5" stroke="#fff" strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="19.5" cy="21" r="3" fill="var(--accent)" stroke="#fff" strokeWidth="1.7" />
      <path d="M21.7 23.2l2 2" stroke="#fff" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  )
}
