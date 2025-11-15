import { forwardRef } from 'react'
import { cn } from '../../lib/classNames'

export const ScrollArea = forwardRef(function ScrollArea(
  { className = '', children, ...props },
  ref
) {
  return (
    <div ref={ref} className={cn('scroll-area', className)} {...props}>
      {children}
    </div>
  )
})
