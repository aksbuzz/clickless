.PHONY: up down logs test lint

up:
    docker-compose up --build -d

down:
    docker-compose down

logs:
    docker-compose logs -f

test:
    pytest

lint:
    ruff check . && black --check .