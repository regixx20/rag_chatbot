const iconProps = {
  width: 24,
  height: 24,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

function createIcon(Component) {
  Component.defaultProps = {
    className: '',
  }
  return Component
}

export const SparklesIcon = createIcon(function SparklesIcon({ className, ...props }) {
  return (
    <svg {...iconProps} className={className} {...props}>
      <path d="M12 2.5l1.2 3.3 3.3 1.2-3.3 1.2-1.2 3.3-1.2-3.3-3.3-1.2 3.3-1.2z" />
      <path d="M5 12.5l0.8 2.1 2.2 0.8-2.2 0.8-0.8 2.1-0.8-2.1-2.2-0.8 2.2-0.8z" />
      <path d="M18.5 13.5l0.7 1.7 1.8 0.6-1.8 0.6-0.7 1.7-0.7-1.7-1.8-0.6 1.8-0.6z" />
    </svg>
  )
})

export const DatabaseIcon = createIcon(function DatabaseIcon({ className, ...props }) {
  return (
    <svg {...iconProps} className={className} {...props}>
      <ellipse cx="12" cy="5" rx="7" ry="3" />
      <path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5" />
      <path d="M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />
    </svg>
  )
})

export const UploadIcon = createIcon(function UploadIcon({ className, ...props }) {
  return (
    <svg {...iconProps} className={className} {...props}>
      <path d="M4 17v2.5A1.5 1.5 0 0 0 5.5 21h13a1.5 1.5 0 0 0 1.5-1.5V17" />
      <path d="M12 3v12" />
      <path d="M8.5 6.5L12 3l3.5 3.5" />
    </svg>
  )
})

export const FileTextIcon = createIcon(function FileTextIcon({ className, ...props }) {
  return (
    <svg {...iconProps} className={className} {...props}>
      <path d="M15.5 2h-7A2.5 2.5 0 0 0 6 4.5v15A2.5 2.5 0 0 0 8.5 22h7a2.5 2.5 0 0 0 2.5-2.5V7.5z" />
      <path d="M15 2v5h5" />
      <path d="M9 13h6" />
      <path d="M9 17h3.5" />
    </svg>
  )
})

export const ImageIcon = createIcon(function ImageIcon({ className, ...props }) {
  return (
    <svg {...iconProps} className={className} {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" ry="2" />
      <path d="M3 16l4.5-4.5L12 16l3-3 6 6" />
      <circle cx="9" cy="9" r="1.8" />
    </svg>
  )
})

export const ArchiveIcon = createIcon(function ArchiveIcon({ className, ...props }) {
  return (
    <svg {...iconProps} className={className} {...props}>
      <rect x="3" y="4" width="18" height="5" rx="1.5" />
      <path d="M7 4v16h10V4" />
      <path d="M10 12h4" />
    </svg>
  )
})

export const FileIcon = createIcon(function FileIcon({ className, ...props }) {
  return (
    <svg {...iconProps} className={className} {...props}>
      <path d="M15 2H9.5A2.5 2.5 0 0 0 7 4.5v15A2.5 2.5 0 0 0 9.5 22h7a2.5 2.5 0 0 0 2.5-2.5V8z" />
      <path d="M15 2v6h6" />
    </svg>
  )
})

export const UserIcon = createIcon(function UserIcon({ className, ...props }) {
  return (
    <svg {...iconProps} className={className} {...props}>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5.5 20a6.5 6.5 0 0 1 13 0" />
    </svg>
  )
})

export const PaperclipIcon = createIcon(function PaperclipIcon({ className, ...props }) {
  return (
    <svg {...iconProps} className={className} {...props}>
      <path d="M16.5 6.5l-7.4 7.4a3 3 0 1 0 4.2 4.2l7-7a4.5 4.5 0 1 0-6.4-6.4l-7 7a6 6 0 0 0 8.5 8.5" />
    </svg>
  )
})

export const SendIcon = createIcon(function SendIcon({ className, ...props }) {
  return (
    <svg {...iconProps} className={className} {...props}>
      <path d="M3 11.5l18-9-4.5 18-5.3-6.2z" />
      <path d="M3 11.5l8.4 2.3" />
    </svg>
  )
})

export const CloseIcon = createIcon(function CloseIcon({ className, ...props }) {
  return (
    <svg {...iconProps} className={className} {...props}>
      <path d="M6 6l12 12" />
      <path d="M18 6l-12 12" />
    </svg>
  )
})

