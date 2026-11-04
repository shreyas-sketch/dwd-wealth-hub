# One image: React build served by FastAPI (same layout as Bullzeye).
# Build:  docker build -t coinzeye .
# Run:    docker run -p 8001:8001 --env-file backend/.env coinzeye

# ---------- 1. Web build ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/yarn.lock* frontend/package-lock.json* ./
RUN if [ -f yarn.lock ]; then yarn install --frozen-lockfile --network-timeout 300000; \
    elif [ -f package-lock.json ]; then npm ci; else yarn install --network-timeout 300000; fi
COPY frontend/ ./
# CRA inlines REACT_APP_* at build time; pass them as Railway build variables.
ARG REACT_APP_ENV="production"
ENV REACT_APP_ENV=$REACT_APP_ENV \
    GENERATE_SOURCEMAP=false \
    CI=false
RUN if [ -f yarn.lock ]; then yarn build; else npm run build; fi

# ---------- 2. API runtime ----------
FROM python:3.12-slim AS api
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Kolkata \
    FRONTEND_BUILD_DIR=/app/frontend/build
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY --from=web /web/build /app/frontend/build

RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app
WORKDIR /app/backend

EXPOSE 8001
# ONE worker: the in-process scheduler must run once. To scale out, set INPROCESS_SCHEDULER=false on the
# web service and call POST /api/jobs/tick (X-Ingest-Key) from a cron every 5 minutes instead.
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*' --timeout-keep-alive 75"]
