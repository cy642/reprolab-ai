/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#0B1020',
        surface: '#121A2B',
        elevated: '#1A2438',
        primary: '#8B5CF6',
        accent: '#22D3EE',
        ink: '#F3F6FC',
        muted: '#8C99B2',
        line: '#26324A',
        success: '#34D399',
        warning: '#FBBF24',
        danger: '#FB7185',
      },
      fontFamily: {
        sans: ['Noto Sans SC', 'Manrope', 'sans-serif'],
        display: ['Manrope', 'Noto Sans SC', 'sans-serif'],
        mono: ['IBM Plex Mono', 'monospace'],
      },
      boxShadow: {
        card: '0 18px 50px rgba(0, 0, 0, 0.18)',
        lift: '0 18px 50px rgba(0, 0, 0, 0.3)',
        focus: '0 0 0 3px rgba(139, 92, 246, 0.18)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '.4' },
        },
        scan: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(400%)' },
        },
      },
      animation: {
        'fade-up': 'fade-up .45s ease-out both',
        'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
        scan: 'scan 3s linear infinite',
      },
    },
  },
  plugins: [],
}
