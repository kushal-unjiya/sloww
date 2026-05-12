import { useMemo, type ReactNode } from 'react'

import type { ChatCitationDTO } from '../../shared/api'
import { useCitationPanel } from './chat/citation-panel-context'
import type { NormalizedCitation } from './chat/types'

const BRACKET_TOKEN = /\[([^\]]+)\]/g
const UUID_IN_BRACKET = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const NUM_REF = /^\d+$/

type CitationMaps = {
  byRefNum: Map<number, ChatCitationDTO>
  byChunkId: Map<string, ChatCitationDTO>
}

function buildCitationMaps(citations: ChatCitationDTO[] | undefined): CitationMaps {
  const byRefNum = new Map<number, ChatCitationDTO>()
  const byChunkId = new Map<string, ChatCitationDTO>()
  for (const c of citations ?? []) {
    if (c.ref_num != null) byRefNum.set(c.ref_num, c)
    if (c.chunk_id) byChunkId.set(c.chunk_id, c)
  }
  return { byRefNum, byChunkId }
}

function resolveCitation(inner: string, maps: CitationMaps): ChatCitationDTO | undefined {
  const trimmed = inner.trim()
  if (NUM_REF.test(trimmed)) return maps.byRefNum.get(Number.parseInt(trimmed, 10))
  if (UUID_IN_BRACKET.test(trimmed)) return maps.byChunkId.get(trimmed)
  return maps.byChunkId.get(trimmed)
}

function normalize(c: ChatCitationDTO, fallback: string): NormalizedCitation {
  const label = c.ref_num != null ? String(c.ref_num) : fallback
  const excerpt = c.raw_text?.trim() || c.excerpt_80?.trim() || 'No retrieved text available for this reference.'
  return {
    id: c.chunk_id || `${c.document_id || 'doc'}-${label}`,
    label,
    docTitle: c.doc_title?.trim() || 'Document',
    page: c.page,
    excerpt,
    raw: c,
  }
}

export function AssistantMessageText({ text, citations, messageId }: { text: string; citations?: ChatCitationDTO[]; messageId?: string }) {
  const maps = useMemo(() => buildCitationMaps(citations), [citations])
  const { openCitation } = useCitationPanel()

  const allSources = useMemo(() => {
    return (citations ?? []).map((c, i) => normalize(c, String(i + 1)))
  }, [citations])

  const parts = useMemo(() => {
    const nodes: ReactNode[] = []
    let last = 0
    let key = 0
    BRACKET_TOKEN.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = BRACKET_TOKEN.exec(text)) !== null) {
      if (m.index > last) nodes.push(<span key={`t-${key++}`}>{text.slice(last, m.index)}</span>)
      const inner = m[1]
      const cite = resolveCitation(inner, maps)
      const label = cite?.ref_num != null ? String(cite.ref_num) : NUM_REF.test(inner.trim()) ? inner.trim() : '?'
      const citation = cite ? normalize(cite, label) : undefined
      const badgeId = `${messageId || 'msg'}-${m.index}`
      nodes.push(
        <button
          key={`c-${key++}-${m.index}`}
          type="button"
          onClick={() => citation && openCitation(citation, allSources, badgeId)}
          className="inline-flex h-[1.15em] min-w-[1.15em] cursor-pointer items-center justify-center rounded border border-amber-600/60 bg-amber-500/15 px-1 text-[10px] font-semibold text-amber-200/95 tabular-nums hover:bg-amber-500/30 hover:border-amber-500 transition-colors align-baseline leading-none -translate-y-[0.05em]"
          aria-label={`Reference ${label}`}
        >
          {label}
        </button>,
      )
      last = m.index + m[0].length
    }
    if (last < text.length) nodes.push(<span key={`t-${key++}`}>{text.slice(last)}</span>)
    return nodes.length > 0 ? nodes : text
  }, [allSources, maps, messageId, openCitation, text])

  return <div className="whitespace-pre-wrap">{parts}</div>
}
