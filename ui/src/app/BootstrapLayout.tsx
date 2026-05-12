import { useAuth } from '@clerk/react'
import { useQuery } from '@tanstack/react-query'
import { Navigate, Outlet } from 'react-router-dom'
import { apiFetch, type MeResponse, parseJson } from '../shared/api'

export function BootstrapLayout() {
  const { isLoaded, isSignedIn, getToken } = useAuth()

  const meQuery = useQuery({
    queryKey: ['me'],
    enabled: Boolean(isLoaded && isSignedIn),
    queryFn: async () => {
      const r = await apiFetch('/me', getToken)
      return parseJson<MeResponse>(r)
    },
  })

  if (!isLoaded) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-300 flex items-center justify-center font-sans">
        <p className="text-sm text-zinc-500">Loading…</p>
      </div>
    )
  }

  if (!isSignedIn) {
    return <Navigate to="/sign-in" replace />
  }

  if (meQuery.isPending) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-300 flex items-center justify-center font-sans">
        <p className="text-sm text-zinc-500">Syncing your account…</p>
      </div>
    )
  }

  if (meQuery.isError) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-200 flex items-center justify-center font-sans px-6">
        <div className="max-w-xl w-full rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6">
          <h2 className="text-lg font-semibold text-zinc-100">Can’t reach the API</h2>
          <p className="mt-2 text-sm text-red-400">{(meQuery.error as Error).message}</p>
          <p className="mt-3 text-sm text-zinc-400 leading-relaxed">
            Confirm <code className="text-zinc-200">VITE_APP_URL</code> points at the FastAPI service and that{' '}
            <code className="text-zinc-200">CLERK_JWKS_URL</code>, <code className="text-zinc-200">CLERK_JWT_ISSUER</code>, and R2 settings are set on the
            backend.
          </p>
        </div>
      </div>
    )
  }

  return <Outlet />
}
