import { SignIn } from '@clerk/react'
import { clerkAppearance } from '../../shared/clerkTheme'

export function SignInPage() {
  return (
    <div className="min-h-screen grid grid-cols-1 lg:grid-cols-2 bg-zinc-950 text-zinc-100 font-sans antialiased">
      {/* Left: story */}
      <section className="relative overflow-hidden px-8 py-12 lg:px-14 lg:py-14">
        <div className="pointer-events-none absolute inset-0 opacity-15">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage:
                'linear-gradient(rgba(255,255,255,.06) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.06) 1px, transparent 1px)',
              backgroundSize: '52px 52px',
              maskImage: 'radial-gradient(ellipse 70% 70% at 50% 35%, black 25%, transparent 70%)',
            }}
          />
        </div>

        <div className="relative max-w-xl">
          <div className="flex items-center gap-3 mb-10">
            <div className="h-9 w-9 rounded-xl bg-violet-500/90 ring-1 ring-violet-300/30" />
            <div className="leading-tight">
              <div className="font-semibold tracking-tight">Sloww AI</div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-zinc-500">Notebook RAG</div>
            </div>
          </div>

          <p className="inline-flex items-center gap-2 rounded-full border border-violet-400/20 bg-violet-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-violet-200 mb-5">
            Personal knowledge intelligence
          </p>
          <h1 className="text-3xl lg:text-4xl font-semibold tracking-tight text-zinc-50 leading-[1.05]">
            Ask anything. Grounded in your sources.
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-zinc-400 max-w-md">
            Upload documents once. Ask questions in plain language. Every answer cites the exact source — no
            guesswork.
          </p>

          <ul className="mt-10 space-y-5 text-sm">
            <li className="flex gap-3">
              <span className="mt-2 h-2 w-2 rounded-full bg-violet-400 ring-4 ring-violet-400/15" aria-hidden />
              <div>
                <div className="font-semibold text-zinc-200">Upload any document</div>
                <div className="text-zinc-500">PDF, Markdown, plain text, HTML — wired to your notebook.</div>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="mt-2 h-2 w-2 rounded-full bg-violet-400 ring-4 ring-violet-400/15" aria-hidden />
              <div>
                <div className="font-semibold text-zinc-200">Citations by default</div>
                <div className="text-zinc-500">See pages, excerpts, and filenames behind each claim.</div>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="mt-2 h-2 w-2 rounded-full bg-violet-400 ring-4 ring-violet-400/15" aria-hidden />
              <div>
                <div className="font-semibold text-zinc-200">Per-user isolation</div>
                <div className="text-zinc-500">Your library is scoped to your account.</div>
              </div>
            </li>
          </ul>

          <blockquote className="mt-10 rounded-2xl border border-zinc-800 bg-zinc-950/40 px-5 py-4">
            <p className="text-sm italic text-zinc-300">
              “Finally a tool that tells me exactly where the answer came from. I can trace every claim back
              to the file.”
            </p>
            <footer className="mt-2 text-xs font-medium text-zinc-500">— Research workflow, early access</footer>
          </blockquote>
        </div>
      </section>

      {/* Right: auth */}
      <section className="border-t border-zinc-900 lg:border-t-0 lg:border-l lg:border-zinc-900 bg-zinc-950 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">
          <h2 className="text-xl font-semibold text-zinc-50">Sign in</h2>
          <p className="mt-1 text-sm text-zinc-400">
            An account is created automatically on first sign-in with email.
          </p>
          <div className="mt-6">
            <SignIn
              routing="path"
              path="/sign-in"
              signUpUrl="/sign-in"
              fallbackRedirectUrl="/projects"
              appearance={clerkAppearance}
              withSignUp
            />
          </div>
          <p className="mt-5 text-xs text-zinc-500 leading-relaxed">
            Email OTP only (V1). By signing in, you agree to our Terms of Service and Privacy Policy.
          </p>
        </div>
      </section>
    </div>
  )
}
