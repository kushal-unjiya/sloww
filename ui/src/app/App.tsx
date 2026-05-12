import { ClerkProvider } from '@clerk/react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { SignInPage } from '../modules/auth/SignInPage'
import { ProjectsPage } from '../modules/projects/ProjectsPage'
import { ProjectDetailPage } from '../modules/projects/ProjectDetailPage'
import { BootstrapLayout } from './BootstrapLayout'

const clerkKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

export function App() {
  if (!clerkKey) {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-200 flex items-center justify-center font-sans px-6">
        <div className="max-w-xl w-full rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6">
          <h1 className="text-lg font-semibold text-zinc-100">Configuration</h1>
          <p className="mt-2 text-sm text-red-400">
          Set <code>VITE_CLERK_PUBLISHABLE_KEY</code> in <code>ui/.env</code> or your environment.
          </p>
        </div>
      </div>
    )
  }

  return (
    <ClerkProvider publishableKey={clerkKey}>
      <Routes>
        <Route path="/sign-in/*" element={<SignInPage />} />
        <Route element={<BootstrapLayout />}>
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectUuid" element={<ProjectDetailPage />} />
          <Route path="/" element={<Navigate to="/projects" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ClerkProvider>
  )
}
