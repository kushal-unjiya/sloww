import type { ChatStreamEvent } from './types'

export async function consumeSSEStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (evt: ChatStreamEvent) => void,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      const line = frame
        .split('\n')
        .find((l) => l.startsWith('data: '))
      if (!line) continue
      try {
        const evt = JSON.parse(line.slice(6)) as ChatStreamEvent
        if (evt.type === 'agent_trace') {
          onEvent({
            type: 'trace',
            phase: evt.phase === 'end' ? 'end' : evt.phase === 'error' ? 'end' : 'start',
            action: evt.label ?? evt.agent_id ?? 'agent',
            message: evt.message,
            reason: [
              evt.role ? `Role: ${evt.role}` : null,
              evt.input_preview ? `Input: ${evt.input_preview}` : null,
              evt.output_preview ? `Output: ${evt.output_preview}` : null,
            ].filter(Boolean).join(' · ') || null,
            role: evt.role,
            input_preview: evt.input_preview,
            output_preview: evt.output_preview,
            metadata: evt.metadata,
            ts: evt.ts,
          })
          continue
        }
        onEvent(evt)
      } catch {
        // ignore malformed chunks
      }
    }
  }
}
