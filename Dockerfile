FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
  gcc g++ libpq-dev curl \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
  && poetry install --without dev --no-interaction --no-ansi

COPY ./src ./src


FROM python:3.12-slim

WORKDIR /app

RUN useradd -m appuser

COPY --from=builder /usr/local /usr/local
COPY --from=builder /app/src ./src

ENV PYTHONPATH=/app

USER appuser

CMD ["python", "-m", "src.api.main"]