import { useEffect, useRef, useState } from 'react'

import { useCitationPanel } from './citation-panel-context'
import type { ChatMessageVM, StreamingStatus } from './types'
import { AssistantMessage } from './AssistantMessage'
import { UserMessage } from './UserMessage'

export function ChatMessages({ messages, status, currentAssistantMessageId }: { messages: ChatMessageVM[]; status: StreamingStatus; currentAssistantMessageId: string | null }) {
  const scrollerRef = useRef<HTMLDivElement>(null)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const { activeCitation } = useCitationPanel()

  useEffect(() => {
    const el = scrollerRef.current
    if (!el) return
    if (isAtBottom) {
      el.scrollTop = el.scrollHeight
    }
  }, [messages, isAtBottom])

  return (
    <div className="flex-1 min-h-0 flex overflow-hidden">
      <div
        ref={scrollerRef}
        onScroll={(e) => {
          const el = e.currentTarget
          setIsAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 120)
        }}
        className="flex-1 overflow-y-auto px-8 py-8"
      >
        <div className="max-w-2xl mx-auto space-y-3">
          {messages.map((m) =>
            m.role === 'user' ? (
              <UserMessage key={m.id} text={m.text} />
            ) : (
              <AssistantMessage key={m.id} message={m} isActiveStreaming={currentAssistantMessageId === m.id} status={status} />
            ),
          )}
        </div>
      </div>
      {activeCitation ? <div id="citation-panel-anchor" /> : null}
    </div>
  )
}
