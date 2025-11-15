import { cn } from '../../lib/classNames'

export function Label({ htmlFor, className = '', children, ...props }) {
  return (
    <label htmlFor={htmlFor} className={cn('label', className)} {...props}>
      {children}
    </label>
  )
}
