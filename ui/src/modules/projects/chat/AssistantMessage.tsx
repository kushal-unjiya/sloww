import { AssistantMessageText } from '../AssistantMessageText'
import { useEffect, useMemo, useState } from 'react'
import type { ChatMessageVM, StreamingStatus } from './types'
import { StreamingIndicator } from './StreamingIndicator'
import { ThinkingIndicator } from './ThinkingIndicator'

export function AssistantMessage({ message, isActiveStreaming, status }: { message: ChatMessageVM; isActiveStreaming: boolean; status: StreamingStatus }) {
  const [workOpen, setWorkOpen] = useState(isActiveStreaming || (message.activity?.length ?? 0) > 0)
  const chartPoints = useMemo(() => normalizeChartPayload(message.chartPayload), [message.chartPayload])

  useEffect(() => {
    if (isActiveStreaming || (message.activity?.length ?? 0) > 0) setWorkOpen(true)
  }, [isActiveStreaming, message.activity?.length])

  return (
    <div className="rounded-2xl px-4 py-3 text-sm leading-relaxed border bg-zinc-900 border-zinc-800 text-zinc-100">
      <div className="mb-1 flex items-center justify-between gap-3 text-[11px] uppercase tracking-wider text-zinc-500">
        <span>Assistant</span>
        {typeof message.latencySeconds === 'number' ? (
          <span className="normal-case tracking-normal text-zinc-600">{message.latencySeconds.toFixed(2)}s</span>
        ) : null}
      </div>
      {message.activity && message.activity.length > 0 ? (
        <div className="mb-2 rounded-lg border border-zinc-800/90 bg-zinc-950/70 text-[11px] leading-snug">
          <button
            type="button"
            onClick={() => setWorkOpen((v) => !v)}
            className="flex w-full items-center justify-between gap-3 px-2.5 py-2 text-left"
            aria-expanded={workOpen}
          >
            <span className="text-[9px] font-semibold uppercase tracking-wider text-zinc-600">
              Agent work {message.activity.length ? `(${message.activity.length})` : ''}
            </span>
            <span className="text-zinc-600">{workOpen ? 'Hide' : 'Show'}</span>
          </button>
          {workOpen ? (
            <ul className="space-y-1 border-t border-zinc-900 px-2.5 py-2">
              {message.activity.map((a, i) => (
                <li key={`${message.id}-${i}`} className="flex items-start gap-2">
                  <span className="w-4 shrink-0 text-center text-zinc-600">{a.phase === 'done' ? '✓' : '⋯'}</span>
                  <span className={a.phase === 'done' ? 'text-zinc-500' : 'text-zinc-300'}>
                    <span>{a.message}</span>
                    {a.role ? <span className="ml-1 text-zinc-600">({a.role})</span> : null}
                    {a.reason ? <span className="block text-[10px] leading-snug text-zinc-600">{a.reason}</span> : null}
                    {a.inputPreview ? <span className="block text-[10px] leading-snug text-zinc-600">Input: {a.inputPreview}</span> : null}
                    {a.outputPreview ? <span className="block text-[10px] leading-snug text-zinc-600">Output: {a.outputPreview}</span> : null}
                    {a.metadata ? <span className="block text-[10px] leading-snug text-zinc-600">{formatMetadata(a.metadata)}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {!message.text && isActiveStreaming ? (
        status === 'connecting' ? <ThinkingIndicator /> : <StreamingIndicator />
      ) : (
        <AssistantMessageText text={message.text} citations={message.citations} messageId={message.id} />
      )}
      {chartPoints.length > 0 ? <MiniChart points={chartPoints} title={String(message.chartPayload?.title || 'Chart')} /> : null}
      <div className="mt-3 pt-2 border-t border-zinc-800 flex items-center gap-2 text-[10px] text-zinc-500">
        <button type="button" className="hover:text-zinc-300">Copy</button>
        <button type="button" className="hover:text-zinc-300" disabled={!message.canRetry}>Retry</button>
        <button type="button" className="hover:text-zinc-300">Share</button>
      </div>
    </div>
  )
}

function formatMetadata(metadata: Record<string, unknown>): string {
  const parts = Object.entries(metadata)
    .map(([key, value]) => `${key}: ${formatValue(value)}`)
    .filter((part) => !part.endsWith(': '))
  return parts.join(' · ')
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => formatValue(item)).join(', ')
  }
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function normalizeChartPayload(payload: ChatMessageVM['chartPayload']): { label: string; value: number }[] {
  if (!payload) return []
  const xs = Array.isArray(payload.x) ? payload.x : Array.isArray(payload.labels) ? payload.labels : []
  const ys = Array.isArray(payload.y) ? payload.y : []
  if (!xs.length || !ys.length) return []
  return xs.slice(0, 12).map((x, i) => ({
    label: String(x),
    value: Number(ys[i] ?? 0),
  })).filter((p) => Number.isFinite(p.value))
}

function MiniChart({ points, title }: { points: { label: string; value: number }[]; title: string }) {
  const max = Math.max(...points.map((p) => Math.abs(p.value)), 1)
  return (
    <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
      <div className="mb-2 text-[11px] font-medium text-zinc-400">{title}</div>
      <div className="space-y-2">
        {points.map((p) => (
          <div key={p.label} className="grid grid-cols-[minmax(72px,140px)_1fr_auto] items-center gap-2 text-[10px] text-zinc-500">
            <span className="truncate">{p.label}</span>
            <span className="h-2 overflow-hidden rounded-full bg-zinc-800">
              <span className="block h-full rounded-full bg-emerald-400" style={{ width: `${Math.max(4, (Math.abs(p.value) / max) * 100)}%` }} />
            </span>
            <span className="tabular-nums text-zinc-400">{p.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
