export function UserMessage({ text }: { text: string }) {
  return (
    <div className="rounded-2xl px-4 py-3 text-sm leading-relaxed border bg-zinc-950 border-zinc-800 text-zinc-200">
      <div className="text-[11px] uppercase tracking-wider text-zinc-500 mb-1">You</div>
      <div className="whitespace-pre-wrap">{text}</div>
    </div>
  )
}
