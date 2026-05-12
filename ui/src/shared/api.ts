/** Must match backend `PROJECT_TITLE_MAX_LENGTH`. */
export const PROJECT_TITLE_MAX_LENGTH = 256

export type LatestJob = {
  status: number | null
  error_message?: string | null
  updated_at?: string | null
}

export type DocumentDTO = {
  id: string
  title: string
  source_type: string
  storage_key: string
  original_filename: string
  mime_type: string
  byte_size: number
  checksum_sha256: string
  status: number
  chunk_count: number | null
  created_at: string
  updated_at: string
  processed_at: string | null
  latest_job: LatestJob | null
}

export type DocumentListResponse = { items: DocumentDTO[] }

export type UploadObjectResponse = {
  storage_key: string
  filename: string
  mime_type: string
  byte_size: number
  checksum_sha256: string
  document_id: string
  status: number
  job_id: string
}

export type MeResponse = {
  id: string
  clerk_user_id: string
  email: string
  display_name: string | null
  avatar_url: string | null
}

export type ProjectDTO = {
  id: string
  title: string
  description: string | null
  is_default: boolean
  status: number
  num_sources: number
  created_at: string
  updated_at: string
}

export type ProjectListResponse = { projects: ProjectDTO[] }

export type ChatConversationDTO = {
  id: string
  title: string
  created_at: string
  updated_at: string
  last_message_at: string | null
}

export type ChatConversationListResponse = { items: ChatConversationDTO[] }

export type ChatMessageDTO = {
  id: string
  role: number
  content: string
  metadata: Record<string, unknown>
  created_at: string
}

export type ChatMessageListResponse = { items: ChatMessageDTO[] }

export type ChatCitationDTO = {
  ref_num?: number
  chunk_id?: string
  doc_title?: string | null
  page?: number | null
  excerpt_80?: string | null
  document_id?: string | null
  raw_text?: string | null
}

export function appBaseUrl(): string {
  const raw = import.meta.env.VITE_APP_URL ?? 'http://127.0.0.1:8000'
  return raw.replace(/\/$/, '')
}

export async function apiFetch(
  path: string,
  getToken: () => Promise<string | null>,
  init: RequestInit = {},
): Promise<Response> {
  const token = await getToken()
  if (!token) {
    throw new Error('Not signed in')
  }
  const url = `${appBaseUrl()}${path.startsWith('/') ? path : `/${path}`}`
  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${token}`)
  if (!headers.has('Content-Type') && init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  return fetch(url, { ...init, headers })
}

export async function apiStream(
  path: string,
  getToken: () => Promise<string | null>,
  init: RequestInit = {},
): Promise<Response> {
  const token = await getToken()
  if (!token) {
    throw new Error('Not signed in')
  }
  const url = `${appBaseUrl()}${path.startsWith('/') ? path : `/${path}`}`
  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${token}`)
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  // Important for SSE: don't set credentials/caching weirdness; just fetch and read the body stream.
  return fetch(url, { ...init, headers })
}

export async function parseJson<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = r.statusText
    try {
      const j = (await r.json()) as { detail?: unknown }
      if (typeof j.detail === 'string') detail = j.detail
      else if (Array.isArray(j.detail)) detail = JSON.stringify(j.detail)
    } catch {
      /* ignore */
    }
    throw new Error(detail || `HTTP ${r.status}`)
  }
  return r.json() as Promise<T>
}
