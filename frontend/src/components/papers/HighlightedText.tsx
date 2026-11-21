import { useMemo } from 'react'

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** Highlights a verified quote inside page text, tolerating whitespace changes. */
export function HighlightedText({ text, quote }: { text: string; quote: string | null }) {
  const parts = useMemo(() => {
    if (!quote) return null
    const tokens = quote.trim().split(/\s+/).slice(0, 60).map(escapeRegExp)
    if (tokens.length === 0 || tokens.join('').length < 4) return null
    const pattern = new RegExp(`(${tokens.join('\\s+')})`, 'gi')
    return text.split(pattern)
  }, [quote, text])

  if (!parts) return <>{text}</>
  return (
    <>
      {parts.map((part, index) => (
        index % 2 === 1
          ? <mark key={index} className="rounded bg-warning/25 px-0.5 text-[#FFE9AE]">{part}</mark>
          : <span key={index}>{part}</span>
      ))}
    </>
  )
}
