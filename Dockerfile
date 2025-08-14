FROM python:3.12-slim

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy poetry lock and pyproject files
COPY poetry.lock pyproject.toml ./

# Install dependencies
RUN poetry install --no-dev --no-root

# Copy the rest of the application code
COPY . .

# Re-run poetry install to ensure the app is installed correctly
RUN poetry install --no-dev