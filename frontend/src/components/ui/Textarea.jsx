import { forwardRef } from 'react'
import { cn } from '../../lib/classNames'

export const Textarea = forwardRef(function Textarea(
  { className = '', disabled = false, ...props },
  ref
) {
  return (
    <textarea
      ref={ref}
      disabled={disabled}
      className={cn('textarea', disabled && 'textarea-disabled', className)}
      {...props}
    />
  )
})
