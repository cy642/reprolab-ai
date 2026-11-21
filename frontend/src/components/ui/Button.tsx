import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/utils'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: 'sm' | 'md'
  icon?: ReactNode
}

const variants: Record<ButtonVariant, string> = {
  primary: 'border-primary/60 bg-primary text-white shadow-[0_8px_24px_rgba(139,92,246,.2)] hover:bg-[#9D71F7] hover:border-[#B79AFB]',
  secondary: 'border-line bg-elevated/80 text-ink hover:border-[#3B4A68] hover:bg-[#202D46]',
  ghost: 'border-transparent bg-transparent text-muted hover:bg-white/[.04] hover:text-ink',
  danger: 'border-danger/20 bg-danger/10 text-danger hover:bg-danger/15',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  className,
  children,
  type = 'button',
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        'inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border font-medium transition-all duration-200 outline-none focus-visible:shadow-focus disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'h-8 px-3 text-xs' : 'h-10 px-4 text-[13px]',
        variants[variant],
        className,
      )}
      {...props}
    >
      {icon}
      {children}
    </button>
  )
}
