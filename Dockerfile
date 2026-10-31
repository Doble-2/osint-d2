# ── OSINT-D2 Docker Image ──
#
# Usage:
#   docker compose up -d
#   docker run -p 127.0.0.1:8000:8000 --env-file .env ghcr.io/doble-2/osint-d2

# ── Build stage: Poetry stays here, out of the final image ──
FROM python:3.15-slim AS builder

RUN pip install --no-cache-dir poetry poetry-plugin-export

WORKDIR /app
COPY pyproject.toml poetry.lock README.md ./
COPY src ./src

# Install the exact locked versions into a virtualenv that gets copied below.
RUN python -m venv /opt/venv \
    && poetry export --only main --format requirements.txt --output /tmp/requirements.txt \
    && /opt/venv/bin/pip install --no-cache-dir --no-deps -r /tmp/requirements.txt \
    && /opt/venv/bin/pip install --no-cache-dir --no-deps .

# ── Runtime stage ──
FROM python:3.15-slim AS runtime

# Libraries WeasyPrint loads at runtime. Playwright's own are installed below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    shared-mime-info \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# ── Non-root user (created BEFORE Playwright browser download) ──
RUN useradd -m -s /bin/bash osint \
    && mkdir -p /app/reports \
    && chown -R osint:osint /app

# ── Playwright: system deps as root, browser as osint ──
RUN playwright install-deps chromium
USER osint
ENV PLAYWRIGHT_BROWSERS_PATH=/home/osint/.cache/ms-playwright
RUN playwright install chromium \
    && rm -rf /home/osint/.cache/ms-playwright/.links

# ── Expose dashboard port ──
EXPOSE 8000

# ── Health check (no curl dependency needed) ──
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# ── Default: launch the web dashboard ──
CMD ["osint-d2", "serve", "--host", "0.0.0.0", "--port", "8000"]
