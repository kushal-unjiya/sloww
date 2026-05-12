import { create } from 'zustand'

export type UploadPhase =
  | 'queued'
  | 'hashing'
  | 'presign'
  | 'uploading'
  | 'registering'
  | 'done'
  | 'error'

export type UploadTask = {
  localId: string
  file: File
  progress: number
  phase: UploadPhase
  error?: string
}

type UploadState = {
  tasks: UploadTask[]
  addTask: (file: File) => string
  patchTask: (localId: string, patch: Partial<UploadTask>) => void
  removeTask: (localId: string) => void
  clearCompleted: () => void
}

export const useUploadStore = create<UploadState>((set, get) => ({
  tasks: [],
  addTask: (file) => {
    const localId = crypto.randomUUID()
    set((s) => ({
      tasks: [
        ...s.tasks,
        { localId, file, progress: 0, phase: 'queued' as const },
      ],
    }))
    return localId
  },
  patchTask: (localId, patch) =>
    set((s) => ({
      tasks: s.tasks.map((t) =>
        t.localId === localId ? { ...t, ...patch } : t,
      ),
    })),
  removeTask: (localId) =>
    set((s) => ({ tasks: s.tasks.filter((t) => t.localId !== localId) })),
  clearCompleted: () =>
    set((s) => ({
      tasks: s.tasks.filter((t) => t.phase !== 'done' && t.phase !== 'error'),
    })),
}))
