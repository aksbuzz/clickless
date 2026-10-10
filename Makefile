.PHONY: up down logs test lint smoke

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

# Needs the dependencies installed (poetry install --no-root).
test:
	python -m pytest -q tests

# Frontend only: the backend has no linter configured yet.
lint:
	cd frontend && npm run lint

# End-to-end check against a running stack (make up first, or see .github/workflows/ci.yml).
smoke:
	sh scripts/smoke.sh
