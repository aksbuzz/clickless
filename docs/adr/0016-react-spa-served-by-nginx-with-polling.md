# 0016. React single-page app served by nginx, with polling for live status

- Status: Accepted - under review (known gaps listed below)
- Date: 2026-10-07 (recorded after the fact; updated 2026-10-10)

## Context

Non-developers need to build, run and monitor workflows, manage connections and inspect instance progress. The backend exposes a plain JSON REST API and has no push channel.

## Decision

- Stack: React 19, TypeScript (strict), Vite 7, Tailwind CSS 4, react-router 7 in declarative mode (`BrowserRouter`), `dagre` for graph layout. Source in `frontend/src`.
- State and data: local component state only; a thin `fetch` wrapper in `src/api.ts` with the base path `/api` fixed in code; three small hooks (`usePolling`, `useConnectors`, `useConnections`). No store and no data-fetching library.
- Authentication: `ApiKeyGate` asks for the API key before showing anything, verifies it against the API, keeps it in `sessionStorage` only, and returns to the prompt on any 401 or on "Sign out" (ADR 0020). `api.ts` sends it as a bearer token on every request.
- Live status: the instances list and instance detail poll the API every few seconds (`usePolling`, default 5 s) and stop once an instance is terminal.
- Instance detail shows one row per step attempt (`attempt N` for retries), the error text of a failed attempt, and the data a step changed. There is no input snapshot.
- Workflow builder: a four-step wizard (inputs, trigger, steps, review) that edits a draft and converts it to and from the JSON definition. Action and trigger forms are generated from the connector catalogue returned by `GET /connectors` (`SchemaForm`). Steps are an ordered list linked by "next" selects, with branch targets. `WorkflowGraph` is a read-only SVG preview laid out by `src/lib/graph-layout.ts`.
- Delivery: a multi-stage Docker build (`npm ci`, `npm run build`) served by `nginx:alpine`. nginx serves the bundle with SPA fallback and reverse-proxies `/api/` to the API, resolving it at request time. `/api/metrics`, `/api/triggers` and `/api/webhooks` return 404 through it. It sets `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and a Content-Security-Policy.
- Tests: `npm test` runs Node's built-in runner over `frontend/tests/` (key storage and request handling); `npm run lint` and `npm run build` complete the checks.

## Alternatives considered

- Server-sent events or WebSockets for status, replacing polling.
- A data-fetching library (TanStack Query or SWR) for caching, retries, request deduplication and race-safe polling.
- A canvas library such as React Flow for a true drag-and-drop builder.
- Server-rendered pages (HTMX or similar) to avoid a separate frontend build.

## Consequences

Positive:

- Simple deployment: static files and one proxy rule; same-origin calls avoid CORS in production.
- Connector-driven forms mean new connectors usually need no frontend change.
- Strict TypeScript, no `dangerouslySetInnerHTML`; the API key is not in `localStorage`.

Negative / known gaps:

- Error handling in `api.ts` ignores `validation_errors` and non-string `detail`, so users see generic messages or `[object Object]`. Polling has no stale-response guard and a single failed poll replaces the page with an error.
- The builder has no client-side validation, edits `next` links without keeping them consistent when steps are reordered, and loses focus while renaming steps. Inline credentials remain in definitions when a connection is selected.
- There is no ErrorBoundary and almost no accessibility attributes. Component behaviour is covered only by the lint and build, not by tests. `npm audit` reports vulnerable dependencies.
- nginx runs as root. The API key is held in browser JavaScript for the session, so an XSS bug would expose it.
- The README used to advertise a drag-and-drop builder; none exists, and the README no longer says so.

## References

- `frontend/` (`src/api.ts`, `src/auth.ts`, `src/components/ApiKeyGate.tsx`, `src/hooks/usePolling.ts`, `src/lib/graph-layout.ts`, `src/components/builder/`, `nginx.conf`, `Dockerfile`, `tests/`)
- Related: ADR 0011, ADR 0015, ADR 0020
