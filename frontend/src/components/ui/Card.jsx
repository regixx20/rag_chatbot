import { cn } from '../../lib/classNames'

export function Card({ className = '', ...props }) {
  return <div className={cn('card', className)} {...props} />
}
