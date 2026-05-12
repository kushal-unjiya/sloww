import { useCitationPanel } from './citation-panel-context'

export function CitationPanel() {
  const { activeCitation, closeCitation } = useCitationPanel()
  if (!activeCitation) return null

  return (
    <aside className="w-[40%] min-w-[280px] max-w-[520px] shrink-0 border-l border-zinc-800 bg-zinc-950/80 flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div className="min-w-0">
          <p className="text-sm text-zinc-200 font-medium truncate">{activeCitation.docTitle}</p>
          {activeCitation.page != null ? <p className="text-xs text-zinc-500">Page {activeCitation.page}</p> : null}
        </div>
        <button type="button" onClick={closeCitation} className="text-zinc-500 hover:text-zinc-300">
          ✕
        </button>
      </div>
      <div className="p-4 overflow-auto">
        <p className="text-xs text-zinc-300 whitespace-pre-wrap leading-relaxed">{activeCitation.excerpt}</p>
      </div>
    </aside>
  )
}
