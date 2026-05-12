import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

import type { NormalizedCitation } from './types'

type CitationPanelContextValue = {
  activeCitation: NormalizedCitation | null
  activeBadgeId: string | null
  allSources: NormalizedCitation[]
  openCitation: (citation: NormalizedCitation, all?: NormalizedCitation[], badgeId?: string) => void
  closeCitation: () => void
}

const CitationPanelContext = createContext<CitationPanelContextValue>({
  activeCitation: null,
  activeBadgeId: null,
  allSources: [],
  openCitation: () => {},
  closeCitation: () => {},
})

export function CitationPanelProvider({ children }: { children: ReactNode }) {
  const [activeCitation, setActiveCitation] = useState<NormalizedCitation | null>(null)
  const [activeBadgeId, setActiveBadgeId] = useState<string | null>(null)
  const [allSources, setAllSources] = useState<NormalizedCitation[]>([])

  const openCitation = useCallback(
    (citation: NormalizedCitation, all: NormalizedCitation[] = [], badgeId?: string) => {
      if (badgeId && activeBadgeId === badgeId) {
        setActiveCitation(null)
        setActiveBadgeId(null)
        setAllSources([])
        return
      }
      setActiveCitation(citation)
      setActiveBadgeId(badgeId ?? null)
      setAllSources(all)
    },
    [activeBadgeId],
  )

  const closeCitation = useCallback(() => {
    setActiveCitation(null)
    setActiveBadgeId(null)
    setAllSources([])
  }, [])

  return (
    <CitationPanelContext.Provider value={{ activeCitation, activeBadgeId, allSources, openCitation, closeCitation }}>
      {children}
    </CitationPanelContext.Provider>
  )
}

export function useCitationPanel() {
  return useContext(CitationPanelContext)
}
