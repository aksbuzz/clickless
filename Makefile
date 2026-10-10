.PHONY: up down logs test lint smoke

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

# Needs the dependencies installed (poetry install --no-root). The integration tests need a PostgreSQL:
#   docker run -d --name pg -p 5432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-alpine
#   export TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres
# Without TEST_DATABASE_URL they are skipped (and fail in CI).
test:
	python -m pytest -q tests

# Frontend only: the backend has no linter configured yet.
lint:
	cd frontend && npm run lint

# End-to-end check against a running stack (make up first, or see .github/workflows/ci.yml).
smoke:
	sh scripts/smoke.sh
