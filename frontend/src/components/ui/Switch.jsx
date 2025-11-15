import { forwardRef } from 'react'
import { cn } from '../../lib/classNames'

export const Switch = forwardRef(function Switch(
  { id, checked = false, onCheckedChange, className = '', disabled = false, ...props },
  ref
) {
  const handleClick = () => {
    if (disabled) return
    onCheckedChange?.(!checked)
  }

  return (
    <button
      id={id}
      ref={ref}
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={handleClick}
      disabled={disabled}
      className={cn('switch', checked && 'switch-checked', disabled && 'switch-disabled', className)}
      {...props}
    >
      <span className="switch-thumb" />
    </button>
  )
})
