# ── OSINT-D2 Docker Image ──
# Multi-stage build for a production-ready intelligence platform.
#
# Usage:
#   docker compose up -d
#   docker run -p 8000:8000 --env-file .env ghcr.io/doble-2/osint-d2

FROM python:3.12-slim AS base

# System dependencies for WeasyPrint (Cairo, Pango) and Playwright (Chromium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-noto-color-emoji \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry

WORKDIR /app

# ── Dependencies (cached layer) ──
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main \
    && rm -rf /root/.cache/pip /root/.cache/pypoetry

# ── Install Playwright Chromium for PDF generation ──
RUN playwright install --with-deps chromium \
    && rm -rf /tmp/*

# ── Application code ──
COPY . .

# ── Expose dashboard port ──
EXPOSE 8000

# ── Health check ──
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8000/ || exit 1

# ── Default: launch the web dashboard ──
CMD ["python", "-m", "cli.main", "serve", "--host", "0.0.0.0", "--port", "8000"]
