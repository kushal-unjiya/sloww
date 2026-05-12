import { useAuth } from '@clerk/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  apiFetch,
  type DocumentDTO,
  type DocumentListResponse,
  type ProjectListResponse,
  type UploadObjectResponse,
  parseJson,
} from '../../shared/api'
import { formatBytes, formatRelativeShort } from '../../shared/format'
import { deriveRowStatus, needsPolling, type StatusTone } from './documentStatus'
import { useUploadStore, type UploadTask } from './uploadStore'

type SortKey =
  | 'title'
  | 'badge'
  | 'source_type'
  | 'status'
  | 'byte_size'
  | 'chunk_count'
  | 'created_at'
  | 'processed_at'
  | 'storage_key'

type SortDir = 'asc' | 'desc'

type StatusFilter = 'all' | StatusTone

function badgeClass(tone: StatusTone): string {
  if (tone === 'fail') return 'sloww-badge sloww-badge-fail'
  if (tone === 'progress') return 'sloww-badge sloww-badge-progress'
  if (tone === 'done') return 'sloww-badge sloww-badge-done'
  return 'sloww-badge sloww-badge-pending'
}

function extLabel(name: string): string {
  const i = name.lastIndexOf('.')
  if (i < 0 || i === name.length - 1) return 'FILE'
  return name.slice(i + 1).toUpperCase().slice(0, 4)
}

function formatStorageKeyDisplay(key: string): string {
  if (key.length <= 52) return key
  const i = key.indexOf('/')
  if (i > 0 && i < key.length - 1) {
    const prefix = key.slice(0, i)
    const leaf = key.slice(i + 1)
    return `${prefix.slice(0, 8)}…/${leaf.length > 32 ? `${leaf.slice(0, 28)}…` : leaf}`
  }
  return `${key.slice(0, 48)}…`
}

function formatUploadError(step: string, e: unknown): string {
  const base = e instanceof Error ? e.message : String(e)
  const hint =
    base === 'Failed to fetch'
      ? ' (check API is running and VITE_APP_URL matches how you open the app)'
      : ''
  return `${step}: ${base}${hint}`
}

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
      patchTask(localId, { phase: 'hashing', progress: 0.08 })
      patchTask(localId, { phase: 'uploading', progress: 0.25 })
      try {
        const formData = new FormData()
        formData.append('file', file, file.name)
        formData.append('project_id', projectId)
        const upR = await apiFetch('/uploads/object', getToken, {
          method: 'POST',
          body: formData,
        })
        if (!upR.ok) await parseJson(upR)
        await parseJson<UploadObjectResponse>(upR)
      } catch (e) {
        throw new Error(
          formatUploadError('Upload via API (file → GCS + register)', e),
        )
      }
      patchTask(localId, { phase: 'done', progress: 1 })
      onDone()
    } catch (e) {
      patchTask(localId, {
        phase: 'error',
        error: e instanceof Error ? e.message : 'Upload failed',
      })
    }
  })()
}

export function DocumentsPage() {
  const { getToken } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const qc = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [sortKey, setSortKey] = useState<SortKey>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [menuOpen, setMenuOpen] = useState<string | null>(null)
  const [renameTarget, setRenameTarget] = useState<DocumentDTO | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  const tasks = useUploadStore((s) => s.tasks)
  const addTask = useUploadStore((s) => s.addTask)
  const patchTask = useUploadStore((s) => s.patchTask)
  const clearCompleted = useUploadStore((s) => s.clearCompleted)

  useEffect(() => {
    if (searchParams.get('upload') === '1') setUploadOpen(true)
  }, [searchParams])

  const closeUploadModal = useCallback(() => {
    setUploadOpen(false)
    if (searchParams.get('upload') === '1') {
      const next = new URLSearchParams(searchParams)
      next.delete('upload')
      setSearchParams(next, { replace: true })
    }
  }, [searchParams, setSearchParams])

  const projectsQuery = useQuery({
    queryKey: ['projects'],
    queryFn: async () => {
      const r = await apiFetch('/projects', getToken)
      return parseJson<ProjectListResponse>(r)
    },
  })

  const scopedProjectId = useMemo(() => {
    const list = projectsQuery.data?.projects ?? []
    const d = list.find((p) => p.is_default)
    return d?.id ?? list[0]?.id
  }, [projectsQuery.data])

  const listQuery = useQuery({
    queryKey: ['documents', scopedProjectId],
    queryFn: async () => {
      if (!scopedProjectId) return { items: [] as DocumentDTO[] }
      const r = await apiFetch(
        `/documents?project_id=${scopedProjectId}`,
        getToken,
      )
      return parseJson<DocumentListResponse>(r)
    },
    enabled: Boolean(scopedProjectId) && projectsQuery.isSuccess,
    refetchInterval: (q) => {
      const list = q.state.data?.items ?? []
      const busy = list.some((d) => needsPolling(d))
      return busy ? 2500 : false
    },
  })

  const items = listQuery.data?.items ?? []

  const stats = useMemo(() => {
    const total = items.length
    let queued = 0
    let processing = 0
    let processed = 0
    let failed = 0
    let bytes = 0
    let chunks = 0
    for (const d of items) {
      bytes += d.byte_size
      chunks += d.chunk_count ?? 0
      const row = deriveRowStatus(d)
      if (row.tone === 'fail') failed += 1
      else if (row.tone === 'done') processed += 1
      else if (row.tone === 'progress') processing += 1
      else queued += 1
    }
    const pct = total ? Math.round((processed / total) * 100) : 0
    return { total, queued, processing, processed, failed, bytes, chunks, pct }
  }, [items])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return items.filter((d) => {
      const row = deriveRowStatus(d)
      if (statusFilter !== 'all' && row.tone !== statusFilter) return false
      if (!q) return true
      return (
        d.title.toLowerCase().includes(q) ||
        d.original_filename.toLowerCase().includes(q) ||
        d.source_type.toLowerCase().includes(q) ||
        d.storage_key.toLowerCase().includes(q)
      )
    })
  }, [items, query, statusFilter])

  useEffect(() => {
    setPage(1)
  }, [query, statusFilter])

  const sorted = useMemo(() => {
    const copy = [...filtered]
    const dir = sortDir === 'asc' ? 1 : -1
    copy.sort((a, b) => {
      let va: string | number | null
      let vb: string | number | null
      if (sortKey === 'title') {
        va = a.title.toLowerCase()
        vb = b.title.toLowerCase()
      } else if (sortKey === 'badge') {
        va = deriveRowStatus(a).badge.toLowerCase()
        vb = deriveRowStatus(b).badge.toLowerCase()
      } else if (sortKey === 'chunk_count') {
        va = a.chunk_count ?? -1
        vb = b.chunk_count ?? -1
      } else if (sortKey === 'processed_at') {
        va = a.processed_at ? new Date(a.processed_at).getTime() : 0
        vb = b.processed_at ? new Date(b.processed_at).getTime() : 0
      } else if (sortKey === 'created_at') {
        va = new Date(a.created_at).getTime()
        vb = new Date(b.created_at).getTime()
      } else if (sortKey === 'byte_size') {
        va = a.byte_size
        vb = b.byte_size
      } else if (sortKey === 'storage_key') {
        va = a.storage_key.toLowerCase()
        vb = b.storage_key.toLowerCase()
      } else if (sortKey === 'status') {
        va = a.status
        vb = b.status
      } else {
        va = String(a[sortKey] ?? '').toLowerCase()
        vb = String(b[sortKey] ?? '').toLowerCase()
      }
      if (va < vb) return -1 * dir
      if (va > vb) return 1 * dir
      return 0
    })
    return copy
  }, [filtered, sortKey, sortDir])

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize))
  const safePage = Math.min(page, pageCount)

  useEffect(() => {
    setPage((p) => Math.min(p, pageCount))
  }, [pageCount])
  const pageSlice = useMemo(() => {
    const start = (safePage - 1) * pageSize
    return sorted.slice(start, start + pageSize)
  }, [sorted, safePage, pageSize])

  const lastSynced =
    listQuery.dataUpdatedAt > 0
      ? formatRelativeShort(new Date(listQuery.dataUpdatedAt).toISOString())
      : '—'

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'created_at' || key === 'processed_at' ? 'desc' : 'asc')
    }
  }

  const invalidateDocs = () => {
    qc.invalidateQueries({ queryKey: ['documents'] })
    qc.invalidateQueries({ queryKey: ['projects'] })
  }

  const deleteMut = useMutation({
    mutationFn: async (id: string) => {
      const r = await apiFetch(`/documents/${id}`, getToken, { method: 'DELETE' })
      if (!r.ok) await parseJson(r)
    },
    onSuccess: invalidateDocs,
  })

  const bulkDeleteMut = useMutation({
    mutationFn: async (ids: string[]) => {
      const r = await apiFetch('/documents/bulk-delete', getToken, {
        method: 'POST',
        body: JSON.stringify({ document_ids: ids }),
      })
      if (!r.ok) await parseJson(r)
    },
    onSuccess: () => {
      setSelected(new Set())
      invalidateDocs()
    },
  })

  const renameMut = useMutation({
    mutationFn: async ({ id, title }: { id: string; title: string }) => {
      const r = await apiFetch(`/documents/${id}`, getToken, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      })
      return parseJson<DocumentDTO>(r)
    },
    onSuccess: () => {
      setRenameTarget(null)
      invalidateDocs()
    },
  })

  const reprocessMut = useMutation({
    mutationFn: async (id: string) => {
      const r = await apiFetch(`/documents/${id}/reprocess`, getToken, {
        method: 'POST',
      })
      if (!r.ok) await parseJson(r)
    },
    onSuccess: invalidateDocs,
  })

  const onPickFiles = useCallback(
    (files: FileList | null) => {
      if (!files?.length) return
      const accepted = Math.min(files.length, 20)
      if (files.length > 20) {
        window.alert('You can upload up to 20 files per selection.')
      }
      if (!scopedProjectId) {
        window.alert('No project found. Create a project first.')
        return
      }
      for (let i = 0; i < accepted; i += 1) {
        const file = files.item(i)
        if (!file) continue
        const localId = addTask(file)
        processUpload(
          file,
          getToken,
          localId,
          patchTask,
          scopedProjectId,
          invalidateDocs,
        )
      }
      if (inputRef.current) inputRef.current.value = ''
    },
    [addTask, getToken, patchTask, scopedProjectId, invalidateDocs],
  )

  const allSelected =
    pageSlice.length > 0 && pageSlice.every((d) => selected.has(d.id))
  const toggleAll = () => {
    if (allSelected) {
      setSelected((prev) => {
        const n = new Set(prev)
        for (const d of pageSlice) n.delete(d.id)
        return n
      })
    } else {
      setSelected((prev) => {
        const n = new Set(prev)
        for (const d of pageSlice) n.add(d.id)
        return n
      })
    }
  }
  const toggleRow = (id: string) => {
    setSelected((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  const filterChips: { id: StatusFilter; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'done', label: 'Processed' },
    { id: 'progress', label: 'In progress' },
    { id: 'pending', label: 'Queued' },
    { id: 'fail', label: 'Failed' },
  ]

  return (
    <div className="sloww-data-page">
      <header className="sloww-data-head">
        <div>
          <h1>Your Data</h1>
          <p className="sloww-data-sub">
            {stats.total} documents · {stats.chunks} indexed chunks · last synced {lastSynced}
          </p>
        </div>
        <button
          type="button"
          className="sloww-btn sloww-btn-primary"
          onClick={() => {
            navigate('/documents?upload=1')
            setUploadOpen(true)
          }}
        >
          Upload files
        </button>
      </header>

      <section className="sloww-stat-grid" aria-label="Library overview">
        <div className="sloww-stat-card">
          <div className="sloww-stat-label">Total documents</div>
          <div className="sloww-stat-value">{stats.total}</div>
          <p className="sloww-stat-hint">Everything in this workspace</p>
        </div>
        <div className="sloww-stat-card sloww-stat-card--ok">
          <div className="sloww-stat-label">Processed</div>
          <div className="sloww-stat-value">{stats.processed}</div>
          <p className="sloww-stat-hint sloww-stat-hint--good">
            {stats.pct}% of library ready to query
          </p>
        </div>
        <div className="sloww-stat-card sloww-stat-card--bad">
          <div className="sloww-stat-label">Failed</div>
          <div className="sloww-stat-value">{stats.failed}</div>
          <p className="sloww-stat-hint sloww-stat-hint--bad">Reprocess or re-upload to retry</p>
        </div>
        <div className="sloww-stat-card sloww-stat-card--warn">
          <div className="sloww-stat-label">In flight</div>
          <div className="sloww-stat-value">{stats.queued + stats.processing}</div>
          <p className="sloww-stat-hint sloww-stat-hint--warn">
            {stats.queued} queued · {stats.processing} processing
          </p>
        </div>
        <div className="sloww-stat-card">
          <div className="sloww-stat-label">Storage used</div>
          <div className="sloww-stat-value" style={{ fontSize: '1.25rem' }}>
            {formatBytes(stats.bytes)}
          </div>
          <p className="sloww-stat-hint">Raw file archive</p>
        </div>
      </section>

      <div className="sloww-toolbar">
        <label className="sloww-search">
          <span className="sloww-search-icon" aria-hidden />
          <input
            type="search"
            placeholder="Search documents…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
          />
        </label>
        <button
          type="button"
          className="sloww-btn"
          disabled={selected.size === 0 || bulkDeleteMut.isPending}
          onClick={() => {
            if (
              !window.confirm(`Delete ${selected.size} document(s)? This cannot be undone.`)
            )
              return
            bulkDeleteMut.mutate([...selected])
          }}
        >
          Bulk delete ({selected.size})
        </button>
        {listQuery.isFetching ? (
          <span style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>Refreshing…</span>
        ) : null}
        {listQuery.isError ? (
          <span style={{ color: 'var(--bad)', fontSize: '0.85rem' }}>
            {(listQuery.error as Error).message}
          </span>
        ) : null}
      </div>

      <div className="sloww-filter-row" role="toolbar" aria-label="Filter by status">
        {filterChips.map((c) => (
          <button
            key={c.id}
            type="button"
            className={`sloww-filter-chip${statusFilter === c.id ? ' sloww-filter-chip--active' : ''}`}
            onClick={() => setStatusFilter(c.id)}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="sloww-table-wrap">
        <table className="sloww-table">
          <thead>
            <tr>
              <th style={{ width: 36 }}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  aria-label="Select all on this page"
                />
              </th>
              <th>
                <button type="button" onClick={() => toggleSort('title')}>
                  Document {sortKey === 'title' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </button>
              </th>
              <th>
                <button type="button" onClick={() => toggleSort('badge')}>
                  Status {sortKey === 'badge' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </button>
              </th>
              <th>
                <button type="button" onClick={() => toggleSort('source_type')}>
                  Source {sortKey === 'source_type' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </button>
              </th>
              <th>
                <button type="button" onClick={() => toggleSort('storage_key')}>
                  GCS path {sortKey === 'storage_key' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </button>
              </th>
              <th>Ver.</th>
              <th>
                <button type="button" onClick={() => toggleSort('byte_size')}>
                  Size {sortKey === 'byte_size' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </button>
              </th>
              <th>
                <button type="button" onClick={() => toggleSort('chunk_count')}>
                  Chunks {sortKey === 'chunk_count' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </button>
              </th>
              <th>
                <button type="button" onClick={() => toggleSort('created_at')}>
                  Uploaded {sortKey === 'created_at' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </button>
              </th>
              <th>
                <button type="button" onClick={() => toggleSort('processed_at')}>
                  Processed {sortKey === 'processed_at' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </button>
              </th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {pageSlice.map((doc) => {
              const row = deriveRowStatus(doc)
              const err = doc.latest_job?.error_message
              return (
                <tr key={doc.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(doc.id)}
                      onChange={() => toggleRow(doc.id)}
                      aria-label={`Select ${doc.original_filename}`}
                    />
                  </td>
                  <td className="sloww-doc-cell">
                    <div className="sloww-doc-row">
                      <span className="sloww-file-badge">{extLabel(doc.original_filename)}</span>
                      <div>
                        <div className="sloww-doc-title">{doc.title || doc.original_filename}</div>
                        <div className="sloww-doc-file">{doc.original_filename}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div className="sloww-status-stack">
                      <span className={badgeClass(row.tone)}>{row.badge}</span>
                      {row.tone === 'fail' && err ? (
                        <span className="sloww-status-err" title={err}>
                          {err.length > 56 ? `${err.slice(0, 56)}…` : err}
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td>{doc.source_type}</td>
                  <td
                    className="font-mono text-[11px] text-zinc-500 max-w-[220px]"
                    title={doc.storage_key}
                  >
                    <span className="block truncate">{formatStorageKeyDisplay(doc.storage_key)}</span>
                  </td>
                  <td style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>v1</td>
                  <td>{formatBytes(doc.byte_size)}</td>
                  <td>{doc.chunk_count ?? '—'}</td>
                  <td>{formatRelativeShort(doc.created_at)}</td>
                  <td>{formatRelativeShort(doc.processed_at)}</td>
                  <td>
                    <div className="sloww-menu">
                      <button
                        type="button"
                        className="sloww-btn sloww-btn-ghost"
                        style={{ padding: '0.25rem 0.5rem' }}
                        aria-expanded={menuOpen === doc.id}
                        onClick={() => setMenuOpen((m) => (m === doc.id ? null : doc.id))}
                      >
                        ⋯
                      </button>
                      {menuOpen === doc.id ? (
                        <div className="sloww-menu-pop" role="menu">
                          <button
                            type="button"
                            onClick={() => {
                              setMenuOpen(null)
                              setRenameTarget(doc)
                              setRenameValue(doc.title)
                            }}
                          >
                            Rename
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setMenuOpen(null)
                              reprocessMut.mutate(doc.id)
                            }}
                          >
                            Reprocess
                          </button>
                          <button
                            type="button"
                            className="danger"
                            onClick={() => {
                              setMenuOpen(null)
                              if (window.confirm(`Delete “${doc.original_filename}”?`)) {
                                deleteMut.mutate(doc.id)
                              }
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </td>
                </tr>
              )
            })}
            {sorted.length === 0 && !listQuery.isPending ? (
              <tr>
                <td colSpan={10} style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)' }}>
                  No documents match.{' '}
                  <button
                    type="button"
                    className="sloww-btn sloww-btn-ghost"
                    style={{ display: 'inline', padding: 0, border: 'none', verticalAlign: 'baseline' }}
                    onClick={() => {
                      setQuery('')
                      setStatusFilter('all')
                    }}
                  >
                    Clear filters
                  </button>{' '}
                  or{' '}
                  <button
                    type="button"
                    className="sloww-btn sloww-btn-ghost"
                    style={{ display: 'inline', padding: 0, border: 'none', verticalAlign: 'baseline' }}
                    onClick={() => {
                      navigate('/documents?upload=1')
                      setUploadOpen(true)
                    }}
                  >
                    upload a file
                  </button>
                  .
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {sorted.length > 0 ? (
        <div className="sloww-pagination">
          <label className="sloww-rows-select">
            Rows per page
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value))
                setPage(1)
              }}
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
            </select>
          </label>
          <span>
            {(safePage - 1) * pageSize + 1}–{Math.min(safePage * pageSize, sorted.length)} of{' '}
            {sorted.length}
          </span>
          <div className="sloww-pagination-controls">
            <button
              type="button"
              disabled={safePage <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              aria-label="Previous page"
            >
              ‹
            </button>
            <button
              type="button"
              disabled={safePage >= pageCount}
              onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
              aria-label="Next page"
            >
              ›
            </button>
          </div>
        </div>
      ) : null}

      {uploadOpen ? (
        <div
          className="sloww-modal-backdrop"
          role="presentation"
          onClick={closeUploadModal}
        >
          <div
            className="sloww-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="upload-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="upload-title">Upload documents</h2>
            <p style={{ color: 'var(--muted)', fontSize: '0.88rem', marginTop: '-0.25rem' }}>
              PDF, Markdown, TXT, HTML — sent to object storage, then queued for ingestion.
            </p>
            <div
              className={`sloww-drop${dragOver ? ' drag' : ''}`}
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                onPickFiles(e.dataTransfer.files)
              }}
            >
              Drop files here or{' '}
              <button
                type="button"
                className="sloww-btn sloww-btn-primary"
                style={{ marginTop: '0.5rem' }}
                onClick={() => inputRef.current?.click()}
              >
                browse
              </button>
              <input
                ref={inputRef}
                type="file"
                multiple
                style={{ display: 'none' }}
                onChange={(e) => onPickFiles(e.target.files)}
              />
            </div>
            {tasks.length > 0 ? (
              <div style={{ marginTop: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <strong style={{ fontSize: '0.85rem' }}>Queue</strong>
                  <button type="button" className="sloww-btn sloww-btn-ghost" onClick={clearCompleted}>
                    Clear finished
                  </button>
                </div>
                <ul style={{ listStyle: 'none', padding: 0, margin: '0.5rem 0 0' }}>
                  {tasks.map((t) => (
                    <li
                      key={t.localId}
                      style={{
                        fontSize: '0.85rem',
                        padding: '0.35rem 0',
                        borderBottom: '1px solid var(--line-soft)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>{t.file.name}</span>
                        <span style={{ color: 'var(--muted)' }}>{t.phase}</span>
                      </div>
                      {t.phase !== 'error' && t.phase !== 'done' ? (
                        <div
                          style={{
                            height: 4,
                            background: 'var(--line-soft)',
                            borderRadius: 4,
                            marginTop: 4,
                            overflow: 'hidden',
                          }}
                        >
                          <div
                            style={{
                              width: `${Math.round(t.progress * 100)}%`,
                              height: '100%',
                              background: 'var(--accent)',
                              transition: 'width 0.2s ease',
                            }}
                          />
                        </div>
                      ) : null}
                      {t.error ? (
                        <div style={{ color: 'var(--bad)', marginTop: 4 }}>{t.error}</div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1.25rem' }}>
              <button type="button" className="sloww-btn" onClick={closeUploadModal}>
                Close
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {renameTarget ? (
        <div
          className="sloww-modal-backdrop"
          role="presentation"
          onClick={() => setRenameTarget(null)}
        >
          <div
            className="sloww-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rename-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="rename-title">Rename</h2>
            <div className="sloww-field">
              <label htmlFor="rename-input">Title</label>
              <input
                id="rename-input"
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1.25rem' }}>
              <button type="button" className="sloww-btn" onClick={() => setRenameTarget(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="sloww-btn sloww-btn-primary"
                disabled={!renameValue.trim() || renameMut.isPending}
                onClick={() =>
                  renameMut.mutate({ id: renameTarget.id, title: renameValue.trim() })
                }
              >
                Save
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
