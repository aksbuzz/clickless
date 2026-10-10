# Frontend

The UI for the workflow platform: React 19, TypeScript, Vite and Tailwind. In the stack it is built into a static bundle and served by nginx, which also proxies `/api` to the API service (see `nginx.conf` and [ADR 0016](../docs/adr/0016-react-spa-served-by-nginx-with-polling.md)).

## Sign-in

Every API route needs the shared API key ([ADR 0020](../docs/adr/0020-shared-api-key-authentication-and-private-internal-services.md)). The app shows a key prompt first, checks the key against the API, keeps it in `sessionStorage` for the life of the tab, and returns to the prompt on any 401 or on "Sign out". The key is the `API_KEY` value in the repository's `.env` (`sh scripts/init-env.sh` creates it and prints it).

## Commands

Run from this directory. Node 22.18 or newer is needed for `npm test`, which uses Node's built-in test runner on TypeScript files.

| Command | What it does |
|---|---|
| `npm install` | Install dependencies |
| `npm run dev` | Dev server on http://localhost:5173; `/api` is proxied to http://localhost:8000 (start the API with `docker compose up`, or on its own) |
| `npm run build` | Type-check (`tsc -b`) and build into `dist/` |
| `npm run lint` | ESLint |
| `npm test` | Unit tests in `tests/` (key storage, request wrapper, 401 handling, error messages) |

## Layout

| Path | Contents |
|---|---|
| `src/api.ts`, `src/auth.ts` | Request wrapper that adds the key, reports 401s and turns error bodies into messages; key storage |
| `src/pages/` | Workflows, workflow detail and builder, instances, instance detail, connectors |
| `src/components/` | Shared pieces, including `ApiKeyGate` and `StepTimeline` |
| `src/hooks/`, `src/lib/graph-layout.ts` | Data hooks (polling, connectors, connections); graph layout with dagre |
| `src/types.ts` | Types for the API's JSON |
| `nginx.conf`, `Dockerfile` | Production image: build, then serve with nginx |

Known frontend gaps (polling races, builder validation, accessibility, dependency audit) are listed in [the audit](../docs/audit-2026-10-07.md) as F-27 to F-31.
