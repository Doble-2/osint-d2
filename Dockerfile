# ── OSINT-D2 Docker Image ──
# Production-ready intelligence platform.
#
# Usage:
#   docker compose up -d
#   docker run -p 8000:8000 --env-file .env ghcr.io/doble-2/osint-d2

FROM python:3.12-slim AS base

# System dependencies for WeasyPrint (Cairo, Pango, GDK-Pixbuf).
# Playwright's own deps (libatk, libnss3, libx11, etc.) are installed
# later by `playwright install --with-deps chromium`.
# NOTE: libffi-dev and shared-mime-info are needed by WeasyPrint at runtime;
# they are NOT pulled by Playwright, so they must be listed here.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry

WORKDIR /app

# ── Dependencies (cached layer) ──
# --no-root: install ONLY dependencies, not the project itself.
# README.md and source code aren't available yet (COPY . . is below).
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main --no-root \
    && rm -rf /root/.cache/pip /root/.cache/pypoetry

# ── Application code ──
COPY . .

# ── Install the project package (now that source + README exist) ──
RUN poetry install --no-interaction --no-ansi --only main

# ── Install Playwright Chromium for PDF/graph generation ──
# --with-deps installs Chromium's own native dependencies (libatk, libnss3,
# libx11, etc.) which are separate from WeasyPrint's Cairo/Pango deps above.
# After install, purge the download cache and link metadata to save ~400 MB.
RUN playwright install --with-deps chromium \
    && rm -rf /tmp/* \
    && rm -rf /root/.cache/ms-playwright/.links \
    && find /root/.cache/ms-playwright -name "*.zip" -delete 2>/dev/null || true

# ── Non-root user (defense-in-depth: Chromium escape → no root) ──
RUN useradd -m -s /bin/bash osint \
    && mkdir -p /app/reports /home/osint/.cache \
    && cp -r /root/.cache/ms-playwright /home/osint/.cache/ms-playwright \
    && chown -R osint:osint /app /home/osint
USER osint
ENV PLAYWRIGHT_BROWSERS_PATH=/home/osint/.cache/ms-playwright

# ── Expose dashboard port ──
EXPOSE 8000

# ── Health check (no curl dependency needed) ──
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# ── Default: launch the web dashboard ──
CMD ["python", "-m", "cli.main", "serve", "--host", "0.0.0.0", "--port", "8000"]
