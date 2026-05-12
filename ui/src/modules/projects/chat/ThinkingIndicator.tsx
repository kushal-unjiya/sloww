const THINKING = [
  'Understanding your request',
  'Searching connected knowledge',
  'Drafting a response',
  'Finalizing the answer',
]

export function ThinkingIndicator({ step = 0 }: { step?: number }) {
  const idx = Math.max(0, step % THINKING.length)
  return <span className="text-zinc-500 text-xs">{THINKING[idx]}…</span>
}
