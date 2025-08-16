FROM python:3.12-slim

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy poetry lock and pyproject files
COPY poetry.lock pyproject.toml ./

# Install dependencies
RUN rm -rf .venv && poetry install --without dev --no-root

# Copy the rest of the application code
COPY ./src ./src