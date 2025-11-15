import { cn } from '../../lib/classNames'

const variants = {
  default: 'badge',
  accent: 'badge badge-accent',
  muted: 'badge badge-muted',
  outline: 'badge badge-outline',
}

export function Badge({ variant = 'default', className = '', ...props }) {
  const variantClass = variants[variant] || variants.default
  return <span className={cn(variantClass, className)} {...props} />
}
