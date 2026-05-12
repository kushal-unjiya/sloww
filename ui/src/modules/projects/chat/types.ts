import type { ChatCitationDTO } from '../../../shared/api'

export type StreamingStatus = 'idle' | 'connecting' | 'streaming' | 'complete' | 'error'

export type ChatActivityLine = {
  node: string
  message: string
  phase: 'running' | 'done'
  reason?: string | null
  llm_calls?: { provider: string; model: string }[]
  role?: string
  inputPreview?: string | null
  outputPreview?: string | null
  metadata?: Record<string, unknown>
  ts?: number
}

export type ChatMessageVM = {
  id: string
  role: 'user' | 'assistant'
  text: string
  citations?: ChatCitationDTO[]
  activity?: ChatActivityLine[]
  llm_calls?: { provider: string; model: string }[]
  latencySeconds?: number
  chartPayload?: ChartPayload | null
  isError?: boolean
  errorType?: 'network' | 'stream_interrupted' | 'unknown'
  partialContent?: string
  canRetry?: boolean
}

export type NormalizedCitation = {
  id: string
  label: string
  docTitle: string
  page?: number | null
  excerpt: string
  raw?: ChatCitationDTO
}

export type ChartPayload = {
  chart_type?: 'bar' | 'line' | 'pie' | string
  title?: string
  x?: string[]
  y?: number[]
  labels?: string[]
  series?: { name?: string; x?: string[]; y?: number[]; values?: number[] }[]
  source_chunk_ids?: string[]
  [key: string]: unknown
}

export type ChatStreamEvent =
  | { type: 'status'; phase: 'start' | 'progress' | 'end'; node?: string; message?: string; llm_calls?: { provider: string; model: string }[] }
  | {
      type: 'trace'
      phase: 'start' | 'progress' | 'end'
      action?: string
      message?: string
      reason?: string | null
      llm_calls?: { provider: string; model: string }[]
      role?: string
      input_preview?: string | null
      output_preview?: string | null
      metadata?: Record<string, unknown>
      ts?: number
    }
  | {
      type: 'agent_trace'
      agent_id?: string
      label?: string
      role?: string
      phase?: 'start' | 'progress' | 'end' | 'error'
      message?: string
      input_preview?: string | null
      output_preview?: string | null
      metadata?: Record<string, unknown>
      ts?: number
    }
  | { type: 'error'; message?: string; error_type?: string; recoverable?: boolean }
  | { type: 'token'; content?: string }
  | { type: 'done'; citations?: ChatCitationDTO[]; chart_payload?: ChartPayload | null; warning?: string | null; llm_calls?: { provider: string; model: string }[]; latency_seconds?: number }
  | { type: string; [key: string]: unknown }
