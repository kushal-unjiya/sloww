# Sloww UI

**Vite + React + TypeScript + Clerk + TanStack Query.** The browser talks **only** to the **backend** (never to inference or data-loader).

**Onboarding:** **[../SETUP.md](../SETUP.md)** — `VITE_APP_URL`, Vercel, local dev.

---

## Prerequisites

- **Node 20+**
- **pnpm** (`npm i -g pnpm`)

---

## Local development

```bash
cd ui
cp .env.example .env
# VITE_APP_URL = backend URL reachable from the browser (e.g. http://127.0.0.1:8000)
# VITE_CLERK_PUBLISHABLE_KEY = from Clerk dashboard

pnpm install
pnpm dev
```

Default dev server: **http://127.0.0.1:5173** (Vite).

**Docker Compose** serves the UI on **port 3000**; the image is built with `VITE_APP_URL=http://localhost:8000` — change Compose build args if your backend URL differs.

---

## Scripts

| Command | Purpose |
|---------|---------|
| `pnpm dev` | Hot reload |
| `pnpm build` | Production bundle |
| `pnpm exec tsc --noEmit` | Typecheck |

**Logged dev server:** `./run-dev.sh` → `ui/logs/dev-YYYY-MM-DD.log`

---

## Product surface (v1)

- **`/projects`** — list/create notebooks
- **`/projects/:projectUuid`** — **Sources** + **Chat** (citations under assistant messages)

See **[../.cursor/ui.md](../.cursor/ui.md)** for editor-oriented detail (may include historical copy).
