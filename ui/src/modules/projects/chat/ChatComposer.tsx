import type { StreamingStatus } from './types'

export function ChatComposer({
  chatInput,
  setChatInput,
  onSend,
  onStop,
  disabled,
  sourceCount,
  status,
}: {
  chatInput: string
  setChatInput: (v: string) => void
  onSend: () => void
  onStop: () => void
  disabled: boolean
  sourceCount: number
  status: StreamingStatus
}) {
  const isStreaming = status === 'connecting' || status === 'streaming'
  return (
    <div className="max-w-2xl mx-auto">
      <div className="relative bg-zinc-950 border border-zinc-800 rounded-xl flex flex-row items-center gap-2 px-2.5 py-1.5 focus-within:border-zinc-700 transition-colors">
        <textarea
          placeholder="Ask about your sources…"
          rows={1}
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              onSend()
            }
          }}
          className="chat-composer-input flex-1 min-w-0 bg-transparent border-none focus:ring-0 resize-none px-2 py-0 text-zinc-200 placeholder-zinc-600 text-sm focus:outline-none h-9 min-h-9 max-h-24 leading-9 overflow-y-auto"
        />
        <p className="text-[11px] text-zinc-600 tabular-nums shrink-0 whitespace-nowrap">{sourceCount} {sourceCount === 1 ? 'source' : 'sources'}</p>
        {isStreaming ? (
          <button type="button" onClick={onStop} className="shrink-0 w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center hover:bg-zinc-700 transition-colors text-zinc-300" aria-label="Stop streaming">
            <span className="material-symbols-outlined text-[18px]">stop</span>
          </button>
        ) : (
          <button type="button" onClick={onSend} disabled={disabled} className="shrink-0 w-8 h-8 rounded-full bg-zinc-800 flex items-center justify-center hover:bg-zinc-700 transition-colors text-zinc-300 disabled:opacity-50" aria-label="Send message">
            <span className="material-symbols-outlined text-[18px]">arrow_upward</span>
          </button>
        )}
      </div>
    </div>
  )
}
