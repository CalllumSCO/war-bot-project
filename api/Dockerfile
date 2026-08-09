# War Bot companion API image.
#
# Build context MUST be the monorepo root (so domain/, utils/, classes/, and
# sql/ are all available to COPY), e.g. from the repo root:
#
#   docker build -f api/Dockerfile -t war-bot-api .
#   docker run -p 8080:8080 --env-file .env.local war-bot-api

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# Monorepo modules shared with the Discord bot.
COPY domain ./domain
COPY utils ./utils
COPY classes ./classes
COPY sql ./sql

# The API service itself.
COPY api ./api

EXPOSE 8080

# Cloud Run sets $PORT (usually 8080). Default to 8080 for local docker runs too.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
