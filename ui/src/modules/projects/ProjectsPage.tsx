import { UserButton, useAuth } from '@clerk/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  apiFetch,
  PROJECT_TITLE_MAX_LENGTH,
  type ProjectDTO,
  type ProjectListResponse,
  parseJson,
} from '../../shared/api'
import { SlowwLogo } from '../../shared/SlowwLogo'

// ── Deterministic helpers ─────────────────────────────────────────────────────

const CARD_THEMES = [
  { border: 'border-pink-900/40',   bg: 'bg-[#2a2123]' },
  { border: 'border-yellow-900/40', bg: 'bg-[#2a2821]' },
  { border: 'border-zinc-700',      bg: 'bg-zinc-800' },
  { border: 'border-blue-900/40',   bg: 'bg-[#21242a]' },
  { border: 'border-indigo-900/40', bg: 'bg-[#22222a]' },
  { border: 'border-orange-900/40', bg: 'bg-[#2a2521]' },
  { border: 'border-teal-900/40',   bg: 'bg-[#212a29]' },
  { border: 'border-red-900/40',    bg: 'bg-[#2a2121]' },
  { border: 'border-green-900/40',  bg: 'bg-[#212a22]' },
]

const EMOJIS = ['🧠', '📒', '💻', '📚', '🔬', '🎯', '💡', '🤖', '🚀', '🧐', '📶', '👨‍🎓', '🌐', '⚗️', '🔭']

function getTheme(index: number) {
  return CARD_THEMES[index % CARD_THEMES.length]
}

function getEmoji(projectId: string): string {
  // Deterministic emoji from project UUID
  let hash = 0
  for (let i = 0; i < projectId.length; i++) {
    hash = (hash * 31 + projectId.charCodeAt(i)) >>> 0
  }
  return EMOJIS[hash % EMOJIS.length]
}

function formatDate(iso: string): string {
  const date = new Date(iso)
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function ChevronDownIcon({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M6 9l6 6 6-6" />
    </svg>
  )
}

// ── Create modal ──────────────────────────────────────────────────────────────

function CreateProjectModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const { getToken } = useAuth()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      const r = await apiFetch('/projects', getToken, {
        method: 'POST',
        body: JSON.stringify({
          title: title.trim().slice(0, PROJECT_TITLE_MAX_LENGTH),
          description: description.trim() || null,
        }),
      })
      return parseJson<ProjectDTO>(r)
    },
    onSuccess: (project) => {
      onCreated()
      onClose()
      window.location.href = `/projects/${project.id}`
    },
  })

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/80 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-md p-6 shadow-2xl">
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">New project</h2>
        <p className="text-sm text-zinc-400 mb-5">Give your project a name to get started.</p>

        <label className="block text-xs font-medium text-zinc-400 mb-1.5">Project name</label>
        <input
          ref={inputRef}
          autoFocus
          type="text"
          value={title}
          maxLength={PROJECT_TITLE_MAX_LENGTH}
          onChange={(e) => setTitle(e.target.value.slice(0, PROJECT_TITLE_MAX_LENGTH))}
          onKeyDown={(e) => e.key === 'Enter' && title.trim() && mutation.mutate()}
          placeholder="e.g. Physics-Informed Neural Networks"
          className="w-full bg-zinc-950 border border-zinc-700 rounded-xl px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500 transition-colors mb-1"
        />
        <p className="text-[11px] text-zinc-600 mb-4 tabular-nums">
          {title.length}/{PROJECT_TITLE_MAX_LENGTH} characters
        </p>

        <label className="block text-xs font-medium text-zinc-400 mb-1.5">Description <span className="text-zinc-600">(optional)</span></label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What is this project about?"
          rows={2}
          className="w-full bg-zinc-950 border border-zinc-700 rounded-xl px-4 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-zinc-500 transition-colors resize-none mb-6"
        />

        <div className="flex gap-3 justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-full text-sm text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={!title.trim() || mutation.isPending}
            className="px-5 py-2 rounded-full bg-white text-zinc-950 text-sm font-medium hover:bg-zinc-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {mutation.isPending ? 'Creating…' : 'Create project'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Project card ──────────────────────────────────────────────────────────────

function ProjectCard({
  project,
  index,
  onRefresh,
}: {
  project: ProjectDTO
  index: number
  onRefresh: () => void
}) {
  const navigate = useNavigate()
  const { getToken } = useAuth()
  const [showMenu, setShowMenu] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(project.title)
  const [editDescription, setEditDescription] = useState(project.description ?? '')
  const menuRef = useRef<HTMLDivElement>(null)
  const theme = getTheme(index)
  const emoji = getEmoji(project.id)

  const deleteMutation = useMutation({
    mutationFn: async () => {
      await apiFetch(`/projects/${project.id}`, getToken, { method: 'DELETE' })
    },
    onSuccess: onRefresh,
  })

  const updateMutation = useMutation({
    mutationFn: async () => {
      await apiFetch(`/projects/${project.id}`, getToken, {
        method: 'PATCH',
        body: JSON.stringify({
          title: editTitle.trim().slice(0, PROJECT_TITLE_MAX_LENGTH),
          description: editDescription.trim() || null,
        }),
      })
    },
    onSuccess: () => {
      setIsEditing(false)
      onRefresh()
    },
  })

  const handleCardClick = (e: React.MouseEvent) => {
    if (menuRef.current?.contains(e.target as Node)) return
    navigate(`/projects/${project.id}`)
  }

  if (isEditing) {
    return (
      <div className={`flex flex-col gap-3 p-4 h-48 rounded-xl border ${theme.border} ${theme.bg}`}>
        <input
          autoFocus
          type="text"
          value={editTitle}
          maxLength={PROJECT_TITLE_MAX_LENGTH}
          onChange={(e) =>
            setEditTitle(e.target.value.slice(0, PROJECT_TITLE_MAX_LENGTH))
          }
          className="bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:border-zinc-500 transition-colors"
        />
        <textarea
          value={editDescription}
          onChange={(e) => setEditDescription(e.target.value)}
          placeholder="Description (optional)"
          rows={2}
          className="bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500 transition-colors resize-none"
        />
        <div className="flex gap-2 mt-auto">
          <button
            type="button"
            onClick={() => updateMutation.mutate()}
            disabled={updateMutation.isPending}
            className="flex-1 py-1.5 rounded-full bg-white text-zinc-950 text-xs font-medium hover:bg-zinc-200 disabled:opacity-40 transition-colors"
          >
            {updateMutation.isPending ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            onClick={() => { setIsEditing(false); setEditTitle(project.title); setEditDescription(project.description ?? '') }}
            className="flex-1 py-1.5 rounded-full border border-zinc-700 text-zinc-400 text-xs hover:bg-zinc-800 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      onClick={handleCardClick}
      className={`group relative flex flex-col p-5 h-48 rounded-xl border ${theme.border} ${theme.bg} hover:shadow-lg hover:shadow-zinc-950/50 transition-all cursor-pointer overflow-visible`}
    >
      <div className="flex items-start justify-between mb-auto">
        {/* Emoji icon */}
        <div className="w-10 h-10 rounded-lg flex items-center justify-center text-2xl bg-zinc-950/30">
          {emoji}
        </div>

        {/* 3-dot menu */}
        <div ref={menuRef}>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setShowMenu(!showMenu) }}
            className="p-1 text-zinc-600 hover:text-zinc-300 opacity-0 group-hover:opacity-100 transition-opacity rounded-md hover:bg-zinc-800"
          >
            <span className="material-symbols-outlined text-[18px]">more_vert</span>
          </button>

          {showMenu && (
            <div className="absolute top-10 right-4 z-20 bg-zinc-800 border border-zinc-700 rounded-xl min-w-[140px] shadow-xl py-1">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setIsEditing(true); setShowMenu(false) }}
                className="flex items-center gap-2 w-full px-3 py-2 text-sm text-zinc-300 hover:bg-zinc-700 transition-colors"
              >
                <span className="material-symbols-outlined text-[16px]">edit</span>
                Edit
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setShowMenu(false); deleteMutation.mutate() }}
                className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-400 hover:bg-zinc-700 transition-colors"
              >
                <span className="material-symbols-outlined text-[16px]">delete</span>
                Delete
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Project info — pinned to bottom; min-w-0 so long titles truncate inside the grid */}
      <div className="mt-auto min-w-0 w-full space-y-1.5">
        <h3 className="font-semibold text-zinc-100 line-clamp-2 leading-snug text-base min-w-0">
          {project.title}
        </h3>
        <p className="text-md text-zinc-500 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 min-w-0">
          <time dateTime={project.updated_at} className="tabular-nums shrink-0">
            {formatDate(project.updated_at)}
          </time>
          <span className="text-zinc-600 shrink-0" aria-hidden>
            ·
          </span>
          <span className="min-w-0">
            {project.num_sources} {project.num_sources === 1 ? 'source' : 'sources'}
          </span>
        </p>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

type SortKey = 'recent' | 'name' | 'sources'

export function ProjectsPage() {
  const { getToken, isSignedIn } = useAuth()
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [sortBy, setSortBy] = useState<SortKey>('recent')

  const { data, isLoading, isError } = useQuery({
    queryKey: ['projects'],
    queryFn: async () => {
      const r = await apiFetch('/projects', getToken)
      return parseJson<ProjectListResponse>(r)
    },
    enabled: Boolean(isSignedIn),
  })

  const projects = data?.projects ?? []

  const projectOrderIndex = useMemo(() => {
    const m = new Map<string, number>()
    projects.forEach((p, i) => m.set(p.id, i))
    return m
  }, [projects])

  const sortedProjects = useMemo(() => {
    const list = [...projects]
    if (sortBy === 'recent') {
      list.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
    } else if (sortBy === 'name') {
      list.sort((a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: 'base' }))
    } else {
      list.sort((a, b) => b.num_sources - a.num_sources || a.title.localeCompare(b.title, undefined, { sensitivity: 'base' }))
    }
    return list
  }, [projects, sortBy])

  const refetch = () => queryClient.invalidateQueries({ queryKey: ['projects'] })

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 font-sans antialiased">

      {/* Header */}
      <header className="sticky top-0 z-10 flex items-center justify-between px-8 py-3.5">
        <div className="flex items-center gap-3">
          <SlowwLogo size={30} />
          <span className="text-xl font-semibold tracking-tight text-white">Sloww AI</span>
        </div>

        <div className="flex items-center gap-3">
          <UserButton
            appearance={{ elements: { avatarBox: { width: '2rem', height: '2rem' } } }}
          />
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-[1400px] mx-auto px-8 py-10">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-8">
          <h1 className="text-2xl font-semibold text-white min-w-0">My projects</h1>
          <label className="relative inline-flex items-center shrink-0 sm:ml-4">
            <span className="sr-only">Sort projects</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortKey)}
              className="appearance-none cursor-pointer pl-3 pr-9 py-2 rounded-full border border-zinc-700 bg-zinc-900 hover:bg-zinc-800 transition-colors text-sm font-medium text-zinc-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950"
            >
              <option value="recent">Most recent</option>
              <option value="name">Name (A–Z)</option>
              <option value="sources">Most sources</option>
            </select>
            <ChevronDownIcon className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          </label>
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 text-zinc-500 text-sm">
            <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>
            Loading notebooks…
          </div>
        ) : isError ? (
          <div className="text-sm text-red-400">Failed to load projects. Please reload.</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-5">

            {/* Create card */}
            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="group flex flex-col items-center justify-center h-48 rounded-xl border-2 border-dashed border-zinc-700 bg-zinc-900/30 hover:bg-zinc-800/60 hover:border-zinc-500 transition-all text-center"
            >
              <div className="w-12 h-12 rounded-full bg-zinc-800 group-hover:bg-zinc-700 flex items-center justify-center text-zinc-400 group-hover:text-zinc-200 mb-3 transition-all group-hover:scale-105">
                <span className="material-symbols-outlined text-2xl">add</span>
              </div>
              <span className="text-sm font-medium text-zinc-400 group-hover:text-zinc-200 transition-colors">
                Create new project
              </span>
            </button>

            {/* Real project cards */}
            {sortedProjects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                index={projectOrderIndex.get(project.id) ?? 0}
                onRefresh={refetch}
              />
            ))}
          </div>
        )}
      </main>

      {showCreate && (
        <CreateProjectModal
          onClose={() => setShowCreate(false)}
          onCreated={refetch}
        />
      )}
    </div>
  )
}
