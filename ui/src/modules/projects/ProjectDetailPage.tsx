import { useAuth } from '@clerk/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'

import {
  apiFetch,
  apiStream,
  PROJECT_TITLE_MAX_LENGTH,
  type ChatCitationDTO,
  type ChatConversationDTO,
  type ChatConversationListResponse,
  type ChatMessageDTO,
  type ChatMessageListResponse,
  type DocumentDTO,
  type DocumentListResponse,
  parseJson,
  type ProjectDTO,
  type UploadObjectResponse,
} from '../../shared/api'
import { SlowwLogo } from '../../shared/SlowwLogo'
import { deriveRowStatus, needsPolling } from '../documents/documentStatus'
import { useUploadStore, type UploadTask } from '../documents/uploadStore'
import { ChatComposer } from './chat/ChatComposer'
import { ChatMessages } from './chat/ChatMessages'
import { CitationPanel } from './chat/CitationPanel'
import { CitationPanelProvider } from './chat/citation-panel-context'
import { consumeSSEStream } from './chat/stream'
import type { ChatMessageVM, StreamingStatus } from './chat/types'

function processUpload(
  file: File,
  getToken: () => Promise<string | null>,
  localId: string,
  patchTask: (id: string, p: Partial<UploadTask>) => void,
  projectId: string,
  onDone: () => void,
) {
  void (async () => {
    try {
      patchTask(localId, { phase: 'uploading', progress: 0.25 })
      try {
        const formData = new FormData()
        formData.append('file', file, file.name)
        formData.append('project_id', projectId)
        const r = await apiFetch('/uploads/object', getToken, { method: 'POST', body: formData })
        if (!r.ok) await parseJson(r)
        await parseJson<UploadObjectResponse>(r)
      } catch (e) {
        throw new Error(`Upload: ${e instanceof Error ? e.message : String(e)}`)
      }
      patchTask(localId, { phase: 'done', progress: 1 })
      onDone()
    } catch (e) {
      patchTask(localId, { phase: 'error', error: e instanceof Error ? e.message : 'Upload failed' })
    }
  })()
}

function MimeBadge({ mimeType }: { mimeType: string }) {
  const ext = mimeType.includes('pdf') ? 'PDF'
    : mimeType.includes('word') || mimeType.includes('docx') ? 'DOC'
    : mimeType.includes('text') ? 'TXT'
    : mimeType.includes('markdown') ? 'MD'
    : 'FILE'

  const colors = ext === 'PDF'
    ? 'bg-red-900/20 text-red-400 border-red-900/30'
    : ext === 'DOC'
      ? 'bg-blue-900/20 text-blue-400 border-blue-900/30'
      : 'bg-zinc-800 text-zinc-400 border-zinc-700'

  return <span className={`shrink-0 w-8 h-6 flex items-center justify-center rounded text-[9px] font-bold border ${colors}`}>{ext}</span>
}

function StatusDot({ doc }: { doc: DocumentDTO }) {
  const { tone } = deriveRowStatus(doc)
  const color = tone === 'done' ? 'bg-green-500' : tone === 'progress' ? 'bg-yellow-500 animate-pulse' : tone === 'fail' ? 'bg-red-500' : 'bg-zinc-500'
  return <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${color}`} />
}

function SourceItem({ doc, onDelete }: { doc: DocumentDTO; onDelete: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} className="group flex items-center justify-between px-2 py-2 rounded-lg hover:bg-zinc-800 cursor-pointer transition-colors">
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <MimeBadge mimeType={doc.mime_type} />
        <span className="text-sm text-zinc-300 truncate">{doc.title}</span>
        <StatusDot doc={doc} />
      </div>
      {hovered ? (
        <button type="button" onClick={(e) => { e.stopPropagation(); onDelete() }} className="shrink-0 w-6 h-6 rounded flex items-center justify-center text-zinc-500 hover:text-red-400 hover:bg-zinc-700 transition-colors ml-2">
          <span className="material-symbols-outlined text-[14px]">close</span>
        </button>
      ) : null}
    </div>
  )
}

function UploadTaskItem({ task }: { task: UploadTask }) {
  const color = task.phase === 'done' ? 'text-green-400' : task.phase === 'error' ? 'text-red-400' : 'text-yellow-400'
  const label = task.phase === 'uploading' ? 'Uploading…' : task.phase === 'registering' ? 'Registering…' : task.phase === 'done' ? 'Done' : task.phase === 'error' ? (task.error ?? 'Error') : 'Queued'
  return (
    <div className="flex items-center gap-3 px-2 py-2 rounded-lg">
      <span className="shrink-0 w-8 h-6 flex items-center justify-center rounded text-[9px] font-bold bg-zinc-800 text-zinc-500 border border-zinc-700">NEW</span>
      <span className="text-sm text-zinc-400 truncate flex-1">{task.file.name}</span>
      <span className={`text-xs shrink-0 ${color}`}>{label}</span>
    </div>
  )
}

function NotFoundFallback({ navigate }: { navigate: (path: string) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => navigate('/projects'), 3000)
    return () => clearTimeout(timer)
  }, [navigate])

  return (
    <div className="flex flex-col items-center justify-center h-screen bg-zinc-950 text-zinc-400 gap-4">
      <span className="material-symbols-outlined text-5xl text-zinc-700">folder_off</span>
      <p className="text-sm font-medium text-zinc-300">Notebook not found or has been deleted</p>
      <p className="text-xs text-zinc-600">Redirecting in 3 seconds…</p>
      <button type="button" onClick={() => navigate('/projects')} className="mt-2 px-5 py-2 rounded-full bg-white text-zinc-950 text-sm font-medium hover:bg-zinc-200 transition-colors">Go home</button>
    </div>
  )
}

export function ProjectDetailPage() {
  const { projectUuid } = useParams<{ projectUuid: string }>()
  const { getToken, isSignedIn } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const { tasks, addTask, patchTask, clearCompleted } = useUploadStore()

  const MIN_SOURCES_W = 220
  const MAX_SOURCES_W = 560
  const SOURCES_COLLAPSED_W = 52

  const [sourcesWidth, setSourcesWidth] = useState(340)
  const [sourcesCollapsed, setSourcesCollapsed] = useState(false)
  const savedSourcesWidth = useRef(340)
  const titleInputRef = useRef<HTMLInputElement>(null)
  const [titleEditing, setTitleEditing] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const resizeDrag = useRef<{ edge: 'sources'; startX: number; startSources: number } | null>(null)

  const [chatInput, setChatInput] = useState('')
  const [messages, setMessages] = useState<ChatMessageVM[]>([])
  const [streamingStatus, setStreamingStatus] = useState<StreamingStatus>('idle')
  const [isRegenerating] = useState(false)
  const assistantIdRef = useRef<string | null>(null)
  const streamAbortRef = useRef<AbortController | null>(null)

  const mapApiMessage = useCallback((m: ChatMessageDTO): ChatMessageVM => {
    const rawCites = m.metadata?.citations
    const citations = Array.isArray(rawCites) ? (rawCites as ChatCitationDTO[]) : undefined
    const rawLlm = m.metadata?.llm_calls
    const llm_calls = Array.isArray(rawLlm) ? (rawLlm as { provider: string; model: string }[]) : undefined
    return {
      id: m.id,
      role: m.role === 1 ? 'user' : 'assistant',
      text: m.content,
      citations,
      llm_calls,
      latencySeconds: typeof m.metadata?.latency_seconds === 'number' ? m.metadata.latency_seconds : undefined,
      canRetry: true,
    }
  }, [])

  const appendAssistant = useCallback((delta: string) => {
    const id = assistantIdRef.current
    if (!id) return
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, text: m.text + delta } : m)))
  }, [])

  const startAssistant = useCallback(() => {
    const id = crypto.randomUUID()
    assistantIdRef.current = id
    setMessages((prev) => [...prev, { id, role: 'assistant', text: '', activity: [], canRetry: true }])
  }, [])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const d = resizeDrag.current
      if (!d) return
      const next = Math.min(MAX_SOURCES_W, Math.max(MIN_SOURCES_W, d.startSources + e.clientX - d.startX))
      setSourcesWidth(next)
    }
    const onUp = () => {
      resizeDrag.current = null
      document.body.style.removeProperty('cursor')
      document.body.style.removeProperty('user-select')
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  const beginResize = useCallback((edge: 'sources', e: React.MouseEvent) => {
    e.preventDefault()
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    resizeDrag.current = { edge, startX: e.clientX, startSources: sourcesWidth }
  }, [sourcesWidth])

  const collapseSources = useCallback(() => {
    savedSourcesWidth.current = sourcesWidth
    setSourcesCollapsed(true)
  }, [sourcesWidth])

  const expandSources = useCallback(() => {
    setSourcesCollapsed(false)
    setSourcesWidth(savedSourcesWidth.current)
  }, [])

  const { data: project, isError: projectError, error: projectErrorObj } = useQuery({
    queryKey: ['project', projectUuid],
    queryFn: async () => parseJson<ProjectDTO>(await apiFetch(`/projects/${projectUuid}`, getToken)),
    enabled: Boolean(projectUuid) && Boolean(isSignedIn),
    retry: 1,
  })

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ['project-docs', projectUuid],
    queryFn: async () => parseJson<DocumentListResponse>(await apiFetch(`/documents?project_id=${projectUuid}`, getToken)),
    enabled: Boolean(projectUuid) && Boolean(isSignedIn) && !projectError,
    refetchInterval: (query) => {
      const items = (query.state.data as DocumentListResponse | undefined)?.items ?? []
      return items.some(needsPolling) ? 3000 : false
    },
  })

  const docs = docsData?.items ?? []
  const pendingTasks = tasks.filter((t) => t.phase !== 'done')

  const { data: activeConversation } = useQuery({
    queryKey: ['chat-active-conversation', projectUuid],
    queryFn: async () => {
      const list = await parseJson<ChatConversationListResponse>(await apiFetch(`/chat/projects/${projectUuid}/conversations`, getToken))
      if (list.items.length > 0) return list.items[0]
      return parseJson<ChatConversationDTO>(await apiFetch(`/chat/projects/${projectUuid}/conversations`, getToken, { method: 'POST', body: JSON.stringify({ title: 'Chat' }) }))
    },
    enabled: Boolean(projectUuid) && Boolean(isSignedIn) && !projectError,
  })

  const activeConversationId = activeConversation?.id

  const { data: messagesData } = useQuery({
    queryKey: ['chat-messages', projectUuid, activeConversationId],
    queryFn: async () => parseJson<ChatMessageListResponse>(await apiFetch(`/chat/projects/${projectUuid}/conversations/${activeConversationId}/messages`, getToken)),
    enabled: Boolean(projectUuid && activeConversationId && isSignedIn && !projectError),
  })

  useEffect(() => {
    if (!messagesData) return
    const fresh = messagesData.items.map(mapApiMessage)
    setMessages((prev) => {
      const prevById = new Map(prev.map((msg) => [msg.id, msg]))
      return fresh.map((msg) => {
        const existing = prevById.get(msg.id)
        if (!existing) return msg
        return {
          ...msg,
          activity: existing.activity?.length ? existing.activity : msg.activity,
          citations: existing.citations ?? msg.citations,
          llm_calls: existing.llm_calls ?? msg.llm_calls,
          latencySeconds: existing.latencySeconds ?? msg.latencySeconds,
          isError: existing.isError ?? msg.isError,
          errorType: existing.errorType ?? msg.errorType,
          partialContent: existing.partialContent ?? msg.partialContent,
          canRetry: existing.canRetry ?? msg.canRetry,
          chartPayload: existing.chartPayload ?? msg.chartPayload,
        }
      })
    })
  }, [messagesData, mapApiMessage, activeConversationId])

  const handleSend = useCallback(async () => {
    const q = chatInput.trim()
    if (!q || !projectUuid || !activeConversationId) return
    if (docs.length === 0) return
    if (streamingStatus === 'connecting' || streamingStatus === 'streaming') return

    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', text: q }])
    setChatInput('')
    setStreamingStatus('connecting')
    startAssistant()

    try {
      const abortController = new AbortController()
      streamAbortRef.current = abortController
      const r = await apiStream('/chat/stream', getToken, {
        method: 'POST',
        signal: abortController.signal,
        body: JSON.stringify({ query: q, conversation_id: activeConversationId, notebook_id: projectUuid }),
      })
      if (!r.ok || !r.body) throw new Error(`Chat failed: ${r.status} ${r.statusText}`)

      await consumeSSEStream(r.body, (evt) => {
        if (evt.type === 'status' && evt.phase === 'start' && typeof evt.message === 'string' && typeof evt.node === 'string') {
          if (evt.node !== 'chat') return
          const cid = assistantIdRef.current
          if (!cid) return
          setMessages((prev) => prev.map((m) => m.id === cid ? { ...m, activity: [...(m.activity ?? []), { node: evt.node as string, message: evt.message as string, phase: 'running' }] } : m))
          return
        }

        if (evt.type === 'status' && evt.phase === 'progress' && typeof evt.message === 'string') {
          const cid = assistantIdRef.current
          if (!cid) return
          setMessages((prev) => prev.map((m) => {
            if (m.id !== cid) return m
            const activity = m.activity ?? []
            const idx = activity.findIndex((a) => a.node === 'chat' && a.phase === 'running')
            if (idx === -1) {
              return { ...m, activity: [...activity, { node: 'chat', message: evt.message as string, phase: 'running' }] }
            }
            const next = [...activity]
            next[idx] = { ...next[idx], message: evt.message as string }
            return { ...m, activity: next }
          }))
          return
        }

        if (evt.type === 'status' && evt.phase === 'end' && typeof evt.node === 'string') {
          if (evt.node !== 'chat') return
          const cid = assistantIdRef.current
          if (!cid) return
          setMessages((prev) => prev.map((m) => {
            if (m.id !== cid) return m
            const act = m.activity ?? []
            const idx = [...act].reverse().findIndex((a) => a.node === evt.node && a.phase === 'running')
            if (idx === -1) return m
            const real = act.length - 1 - idx
            const next = [...act]
            next[real] = { ...next[real], phase: 'done', llm_calls: Array.isArray((evt as any).llm_calls) ? (evt as any).llm_calls : next[real].llm_calls }
            return { ...m, activity: next }
          }))
          return
        }

        if (evt.type === 'trace' && typeof evt.action === 'string') {
          const cid = assistantIdRef.current
          if (!cid) return
          const phase = evt.phase === 'end' ? 'done' : 'running'
          const message = typeof evt.message === 'string' ? evt.message : evt.action
          setMessages((prev) => prev.map((m) => {
            if (m.id !== cid) return m
            const activity = m.activity ?? []
            const idx = [...activity].reverse().findIndex((a) => a.node === evt.action && a.phase === 'running')
            if (idx === -1 || evt.phase === 'start') {
              return {
                ...m,
                activity: [
                  ...activity,
                  {
                    node: evt.action as string,
                    message,
                    phase,
                    reason: typeof evt.reason === 'string' ? evt.reason : null,
                    role: typeof evt.role === 'string' ? evt.role : undefined,
                    inputPreview: typeof evt.input_preview === 'string' ? evt.input_preview : null,
                    outputPreview: typeof evt.output_preview === 'string' ? evt.output_preview : null,
                    metadata: isRecord(evt.metadata) ? evt.metadata : undefined,
                    ts: typeof evt.ts === 'number' ? evt.ts : undefined,
                    llm_calls: Array.isArray(evt.llm_calls) ? evt.llm_calls : undefined,
                  },
                ],
              }
            }
            const real = activity.length - 1 - idx
            const next = [...activity]
            next[real] = {
              ...next[real],
              message,
              phase,
              reason: typeof evt.reason === 'string' ? evt.reason : next[real].reason,
              llm_calls: Array.isArray(evt.llm_calls) ? evt.llm_calls : next[real].llm_calls,
            }
            return { ...m, activity: next }
          }))
          return
        }

        if (evt.type === 'token' && typeof (evt as any).content === 'string') {
          setStreamingStatus((prev) => (prev === 'streaming' ? prev : 'streaming'))
          appendAssistant((evt as any).content)
          return
        }

        if (evt.type === 'error') {
          const cid = assistantIdRef.current
          if (!cid) return
          const message = typeof evt.message === 'string'
            ? evt.message
            : 'The agent hit a temporary issue while generating the answer. Please try again.'
          setMessages((prev) => prev.map((m) => {
            if (m.id !== cid) return m
            const alreadyHasText = m.text.trim().length > 0
            return {
              ...m,
              isError: true,
              errorType: 'stream_interrupted',
              canRetry: true,
              text: alreadyHasText ? m.text : message,
              activity: [
                ...(m.activity ?? []).map((a) => a.phase === 'running' ? { ...a, phase: 'done' as const } : a),
                {
                  node: 'fallback',
                  message: 'Recovered with a fallback response',
                  phase: 'done' as const,
                  reason: message,
                },
              ],
            }
          }))
          setStreamingStatus('error')
          return
        }

        if (evt.type === 'done') {
          const cid = assistantIdRef.current
          if (!cid) return
          const cites = Array.isArray((evt as any).citations) ? ((evt as any).citations as ChatCitationDTO[]) : undefined
          const llm = Array.isArray((evt as any).llm_calls) ? ((evt as any).llm_calls as { provider: string; model: string }[]) : undefined
          const latency = typeof (evt as any).latency_seconds === 'number' ? (evt as any).latency_seconds : undefined
          setMessages((prev) => prev.map((m) => {
            if (m.id !== cid) return m
            return {
              ...m,
              citations: cites,
              llm_calls: llm ?? m.llm_calls,
              latencySeconds: latency ?? m.latencySeconds,
              activity: (m.activity ?? []).map((a) => a.phase === 'running' ? { ...a, phase: 'done' } : a),
            }
          }))
          setStreamingStatus('complete')
        }
      })
    } catch (e) {
      const cid = assistantIdRef.current
      const msg = e instanceof Error ? e.message : String(e)
      if (cid) {
        setMessages((prev) => prev.map((m) => m.id === cid ? { ...m, isError: true, errorType: 'stream_interrupted', partialContent: m.text, canRetry: true, text: m.text || `[Error] ${msg}` } : m))
      }
      setStreamingStatus('error')
    } finally {
      streamAbortRef.current = null
      assistantIdRef.current = null
      void queryClient.invalidateQueries({ queryKey: ['chat-messages', projectUuid, activeConversationId] })
    }
  }, [chatInput, projectUuid, activeConversationId, docs.length, streamingStatus, startAssistant, getToken, appendAssistant, queryClient])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

  const handleStopStreaming = useCallback(() => {
    if (streamAbortRef.current) {
      streamAbortRef.current.abort()
      streamAbortRef.current = null
    }
    setStreamingStatus('idle')
  }, [])

  const deleteMutation = useMutation({
    mutationFn: async (documentId: string) => {
      const res = await apiFetch(`/documents/${documentId}`, getToken, { method: 'DELETE' })
      if (!res.ok) throw new Error(`Delete failed: ${res.statusText}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-docs', projectUuid] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  const renameProjectMutation = useMutation({
    mutationFn: async (nextTitle: string) => {
      if (!projectUuid) throw new Error('Missing project')
      const p = queryClient.getQueryData<ProjectDTO>(['project', projectUuid])
      const r = await apiFetch(`/projects/${projectUuid}`, getToken, { method: 'PATCH', body: JSON.stringify({ title: nextTitle, description: p?.description ?? null }) })
      return parseJson<ProjectDTO>(r)
    },
    onSuccess: () => {
      setTitleEditing(false)
      queryClient.invalidateQueries({ queryKey: ['project', projectUuid] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  useEffect(() => {
    if (project && !titleEditing) setEditTitle(project.title.slice(0, PROJECT_TITLE_MAX_LENGTH))
  }, [project, titleEditing])

  useEffect(() => {
    if (titleEditing && titleInputRef.current) {
      titleInputRef.current.focus()
      titleInputRef.current.select()
    }
  }, [titleEditing])

  const commitTitle = useCallback(() => {
    if (!project) return
    const t = editTitle.trim().slice(0, PROJECT_TITLE_MAX_LENGTH)
    if (!t) {
      setEditTitle(project.title.slice(0, PROJECT_TITLE_MAX_LENGTH))
      setTitleEditing(false)
      return
    }
    if (t === project.title) {
      setTitleEditing(false)
      return
    }
    renameProjectMutation.mutate(t)
  }, [editTitle, project, renameProjectMutation])

  const cancelTitle = useCallback(() => {
    if (project) setEditTitle(project.title)
    setTitleEditing(false)
  }, [project])

  const startUpload = useCallback((file: File) => {
    if (!projectUuid) return
    const localId = addTask(file)
    processUpload(file, getToken, localId, patchTask, projectUuid, () => {
      queryClient.invalidateQueries({ queryKey: ['project-docs', projectUuid] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    })
  }, [addTask, getToken, patchTask, projectUuid, queryClient])

  const handleFiles = useCallback((files: FileList | File[]) => {
    Array.from(files).forEach(startUpload)
  }, [startUpload])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])
  const handleDragLeave = useCallback(() => setIsDragging(false), [])
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files)
  }, [handleFiles])

  useEffect(() => {
    const t = setInterval(() => {
      const hasDone = useUploadStore.getState().tasks.some((task) => task.phase === 'done' || task.phase === 'error')
      if (hasDone) clearCompleted()
    }, 8000)
    return () => clearInterval(t)
  }, [clearCompleted])

  if (!projectUuid) return <NotFoundFallback navigate={navigate} />
  if (!isSignedIn) return <Navigate to="/sign-in" replace />
  if (projectError) {
    const msg = projectErrorObj instanceof Error ? projectErrorObj.message : 'Failed to load project'
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-zinc-950 text-zinc-400 gap-3 px-6">
        <p className="text-sm font-medium text-zinc-200">Couldn’t load this project</p>
        <p className="text-xs text-zinc-500 text-center max-w-md">{msg}</p>
        <button type="button" onClick={() => navigate('/projects')} className="mt-2 px-5 py-2 rounded-full bg-white text-zinc-950 text-sm font-medium hover:bg-zinc-200 transition-colors">Back to projects</button>
      </div>
    )
  }

  const sourceCount = project?.num_sources ?? docs.length

  return (
    <div className="bg-zinc-950 text-zinc-200 h-screen flex flex-col overflow-hidden font-sans antialiased">
      <header className="flex items-center justify-between px-6 py-3.5 shrink-0">
        <div className="flex items-center gap-6 min-w-0 flex-1">
          <button type="button" onClick={() => navigate('/projects')} className="shrink-0 hover:opacity-70 transition-opacity" title="Back to notebooks">
            <SlowwLogo size={30} />
          </button>
          {titleEditing ? (
            <input
              ref={titleInputRef}
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value.slice(0, PROJECT_TITLE_MAX_LENGTH))}
              maxLength={PROJECT_TITLE_MAX_LENGTH}
              onBlur={commitTitle}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); commitTitle() }
                if (e.key === 'Escape') { e.preventDefault(); cancelTitle() }
              }}
              disabled={renameProjectMutation.isPending}
              className="min-w-0 flex-1 max-w-xl text-2xl font-semibold text-zinc-100 bg-zinc-900 border border-white rounded-lg px-2.5 py-1 focus:outline-none focus:ring-2 focus:ring-white/30 disabled:opacity-50"
              aria-label="Project name"
            />
          ) : (
            <button type="button" onClick={() => { setEditTitle((project?.title ?? '').slice(0, PROJECT_TITLE_MAX_LENGTH)); setTitleEditing(true) }} className="min-w-0 flex-1 max-w-xl text-left text-2xl font-semibold text-zinc-300 whitespace-normal wrap-break-word rounded-lg px-2.5 py-1 -mx-0.5 border border-transparent hover:border-white transition-colors cursor-text" title="Click to rename">{project?.title ?? '…'}</button>
          )}
        </div>
        <button type="button" onClick={() => navigate('/projects')} className="flex items-center gap-2 bg-zinc-200 text-zinc-950 px-4 py-1.5 rounded-full text-sm font-medium hover:bg-white transition-colors shrink-0">
          <span className="material-symbols-outlined text-[18px]">add</span>
          New project
        </button>
      </header>

      <main className="flex flex-1 overflow-hidden p-3 gap-0 min-h-0">
        <aside
          style={{ width: sourcesCollapsed ? SOURCES_COLLAPSED_W : sourcesWidth }}
          className={`flex flex-col shrink-0 bg-zinc-900 rounded-xl border transition-colors overflow-hidden ${isDragging ? 'border-blue-500/60 bg-blue-950/10' : 'border-zinc-800'} ${sourcesCollapsed ? 'mr-2' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {sourcesCollapsed ? (
            <div className="flex flex-col flex-1 min-h-0">
              <button type="button" onClick={expandSources} className="flex-1 flex items-center justify-center hover:bg-zinc-800/80 transition-colors min-h-[120px]" aria-label="Expand sources panel">
                <span className="material-symbols-outlined text-zinc-400 text-[22px]">chevron_right</span>
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between gap-2 px-4 py-2 border-b border-zinc-800 shrink-0 min-h-[50px]">
                <h2 className="text-lg font-semibold text-zinc-200 truncate min-w-0">Sources</h2>
                <button type="button" onClick={collapseSources} className="shrink-0 p-1 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors" aria-label="Collapse sources panel">
                  <span className="material-symbols-outlined text-[20px]">chevron_left</span>
                </button>
              </div>

              <div className="p-3 shrink-0">
                <button type="button" onClick={() => fileInputRef.current?.click()} className="w-full flex items-center justify-center gap-2 py-2 rounded-full border border-zinc-700 hover:bg-zinc-800 transition-colors text-sm font-medium text-zinc-300">
                  <span className="material-symbols-outlined text-[18px]">add</span>
                  Add sources
                </button>
                <input ref={fileInputRef} type="file" multiple className="hidden" onChange={(e) => e.target.files && handleFiles(e.target.files)} />
              </div>

              {isDragging ? (
                <div className="mx-3 mb-3 shrink-0 rounded-xl border-2 border-dashed border-blue-500/60 bg-blue-950/20 py-4 flex flex-col items-center gap-1">
                  <span className="material-symbols-outlined text-blue-400 text-2xl">upload_file</span>
                  <span className="text-xs text-blue-400">Drop files here</span>
                </div>
              ) : null}

              <div className="flex-1 overflow-y-auto px-2 pb-3 min-h-0">
                {pendingTasks.map((task) => <UploadTaskItem key={task.localId} task={task} />)}
                {docsLoading ? (
                  <div className="flex items-center gap-2 px-3 py-4 text-zinc-600 text-xs">
                    <span className="material-symbols-outlined text-[16px] animate-spin">progress_activity</span>
                    Loading sources…
                  </div>
                ) : docs.length === 0 && pendingTasks.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-10 gap-2 text-zinc-600">
                    <span className="material-symbols-outlined text-3xl">upload_file</span>
                    <p className="text-xs text-center">Drag & drop files here<br />or click <span className="text-zinc-400">Add sources</span></p>
                  </div>
                ) : docs.map((doc) => <SourceItem key={doc.id} doc={doc} onDelete={() => deleteMutation.mutate(doc.id)} />)}
              </div>
            </>
          )}
        </aside>

        {!sourcesCollapsed ? (
          <div role="separator" aria-orientation="vertical" aria-label="Resize sources panel" onMouseDown={(e) => beginResize('sources', e)} className="w-2 shrink-0 flex justify-center cursor-col-resize group select-none touch-none">
            <div className="w-px h-full min-h-[100px] my-auto rounded-full bg-zinc-800/40 group-hover:bg-zinc-600 group-active:bg-zinc-500" />
          </div>
        ) : null}

        <section className="flex-1 min-w-0 flex flex-col bg-zinc-900 rounded-xl border border-zinc-800 relative overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 shrink-0 min-h-[50px]">
            <h2 className="text-lg font-semibold text-zinc-200">Chat</h2>
          </div>

          <CitationPanelProvider>
            <div className="px-8 py-8 shrink-0">
              <div className="max-w-2xl mx-auto">
                <h1 className="text-2xl font-semibold text-zinc-100 mb-2 min-w-0 whitespace-normal wrap-break-word">{project?.title ?? '…'}</h1>
                <p className="text-sm text-zinc-500">
                  {sourceCount} {sourceCount === 1 ? 'source' : 'sources'}
                  {project?.updated_at ? ` · ${new Date(project.updated_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}` : ''}
                </p>
              </div>
            </div>

            {docs.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center py-16 gap-3 text-zinc-600">
                <span className="material-symbols-outlined text-4xl">chat</span>
                <p className="text-sm text-zinc-500 text-center">Add sources to start chatting with your documents.</p>
              </div>
            ) : messages.length === 0 ? (
              <div className="flex-1 overflow-y-auto px-8 pb-8">
                <div className="max-w-2xl mx-auto space-y-3">
                  <p className="text-sm text-zinc-500 mb-2">Suggested questions:</p>
                  <button type="button" onClick={() => setChatInput('What are the main topics covered in these sources?')} className="w-full text-left px-5 py-3 rounded-xl bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 transition-colors text-sm text-zinc-300">What are the main topics covered in these sources?</button>
                  <button type="button" onClick={() => setChatInput('Summarize the key findings across all documents.')} className="w-full text-left px-5 py-3 rounded-xl bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 transition-colors text-sm text-zinc-300">Summarize the key findings across all documents.</button>
                </div>
              </div>
            ) : (
              <ChatMessages messages={messages} status={streamingStatus} currentAssistantMessageId={assistantIdRef.current} />
            )}

            <CitationPanel />

            <div className="px-6 pb-4 pt-0 shrink-0 bg-zinc-900">
              <ChatComposer
                chatInput={chatInput}
                setChatInput={setChatInput}
                onSend={() => void handleSend()}
                onStop={handleStopStreaming}
                sourceCount={sourceCount}
                status={streamingStatus}
                disabled={docs.length === 0 || !chatInput.trim() || !activeConversationId || isRegenerating}
              />
              <p className="text-center mt-2 text-xs text-zinc-600">Sloww AI may make mistakes. Always verify important information.</p>
            </div>
          </CitationPanelProvider>
        </section>
      </main>
    </div>
  )
}
