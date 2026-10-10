# 0016. React single-page app served by nginx, with polling for live status

- Status: Accepted - under review (known gaps: F-24 to F-31)
- Date: 2026-10-07 (recorded retrospectively)

## Context

Non-developers need to build, run and monitor workflows, manage connections and inspect instance progress. The backend exposes a plain JSON REST API and has no push channel.

## Decision

- Stack: React 19, TypeScript (strict), Vite 7, Tailwind CSS 4, react-router 7 in declarative mode (`BrowserRouter`), `dagre` for graph layout. Source in `frontend/src`.
- State and data: local component state only; a thin `fetch` wrapper in `src/api.ts` with the base path `/api` fixed in code; three small hooks (`usePolling`, `useConnectors`, `useConnections`). No store and no data-fetching library.
- Live status: the instances list and instance detail poll the API every few seconds (`usePolling`, default 5 s) and stop once an instance is terminal.
- Workflow builder: a four-step wizard (inputs, trigger, steps, review) that edits a draft and converts it to and from the JSON definition. Action and trigger forms are generated from the connector catalogue returned by `GET /connectors` (`SchemaForm`). Steps are an ordered list linked by "next" selects, with branch targets. `WorkflowGraph` is a read-only SVG preview.
- Delivery: a multi-stage Docker build (`npm ci`, `npm run build`) served by `nginx:alpine`. nginx serves the static bundle with SPA fallback and reverse-proxies `/api/` to `http://api:8000/`, so the browser talks to one origin.

## Alternatives considered

- Server-sent events or WebSockets for status, replacing polling.
- A data-fetching library (TanStack Query or SWR) for caching, retries, request deduplication and race-safe polling.
- A canvas library such as React Flow for a true drag-and-drop builder.
- Server-rendered pages (HTMX or similar) to avoid a separate frontend build.

## Consequences

Positive:

- Simple deployment: static files and one proxy rule; same-origin calls avoid CORS in production.
- Connector-driven forms mean new connectors usually need no frontend change.
- Strict TypeScript, no `dangerouslySetInnerHTML`, no browser storage of secrets.

Negative / known gaps (details in the audit):

- A clean clone could not build: `WorkflowGraph.tsx` imports `../lib/graph-layout`, which was never committed because the root `.gitignore` rule `lib/` also matched `frontend/src/lib/` (F-24). Fixed on 2026-10-10: the module was rewritten and the ignore rule anchored.
- The proxy forwards every `/api/*` path, exposing `/admin/recover`, `/metrics` and `/connections/*` on the UI port, and there is no authentication layer (F-03, F-25).
- Error handling in `api.ts` ignores `validation_errors` and non-string `detail`, so users see generic messages or `[object Object]` (F-26). Polling has no stale-response guard and a single failed poll replaces the page with an error (F-27).
- The builder has no client-side validation, edits `next` links without keeping them consistent when steps are reordered, and loses focus while renaming steps (F-28). Inline credentials remain in definitions when a connection is selected (F-19).
- There are no frontend tests, no ErrorBoundary and almost no accessibility attributes (F-29). `npm audit` reports vulnerable dependencies (F-30). nginx sends no security headers (F-25).
- The README advertises a drag-and-drop builder; none exists (F-22).

## References

- `frontend/` (`src/api.ts`, `src/hooks/usePolling.ts`, `src/components/builder/`, `nginx.conf`, `Dockerfile`)
- `docs/image.png`
- Related: ADR 0011, ADR 0015
