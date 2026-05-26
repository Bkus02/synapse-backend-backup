# Synapse backend container — Python 3.12 (matches local dev).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# psycopg2-binary ships wheels, but libpq + build essentials make
# debugging from-source installs easier on slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app
COPY migrations ./migrations

EXPOSE 8000

# Default: uvicorn ASGI server. Compose can override the command to run
# `python -m app.ops apply-migrations` before the API starts.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
