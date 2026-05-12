import type { DocumentDTO } from '../../shared/api'

export type StatusTone = 'pending' | 'progress' | 'done' | 'fail'

const STATUS_UPLOADING = 1000
const STATUS_QUEUED = 1003
const STATUS_PROCESSING = 1101
const STATUS_PROCESSED = 1200
const STATUS_FAILED = 1301

export function deriveRowStatus(doc: DocumentDTO): {
  badge: string
  raw: number
  tone: StatusTone
} {
  const job = doc.latest_job?.status
  if (doc.status === STATUS_FAILED || job === STATUS_FAILED) {
    return { badge: 'Failed', raw: doc.status, tone: 'fail' }
  }
  if (job === STATUS_PROCESSING || doc.status === STATUS_PROCESSING) {
    return { badge: 'Processing', raw: doc.status, tone: 'progress' }
  }
  if (job === STATUS_QUEUED || doc.status === STATUS_QUEUED) {
    return { badge: 'Queued', raw: doc.status, tone: 'pending' }
  }
  if (doc.status === STATUS_PROCESSED || job === STATUS_PROCESSED) {
    return { badge: 'Processed', raw: doc.status, tone: 'done' }
  }
  if (doc.status === STATUS_UPLOADING) {
    return { badge: 'Uploading', raw: doc.status, tone: 'progress' }
  }
  return { badge: String(doc.status), raw: doc.status, tone: 'pending' }
}

export function needsPolling(doc: DocumentDTO): boolean {
  const { tone } = deriveRowStatus(doc)
  return tone === 'pending' || tone === 'progress'
}
