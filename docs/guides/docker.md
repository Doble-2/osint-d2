# Docker Deployment

## Quick Start

```bash
git clone https://github.com/Doble-2/osint-d2.git
cd osint-d2
cp .env.example .env          # Add your AI key
mkdir -p reports              # Otherwise Docker creates it as root, and reports fail to save
docker compose up -d
```

Open **http://localhost:8000** to access the web dashboard.

!!! success "Batteries Included"
    The Docker image includes **all native dependencies** for full functionality:

    - **PDF generation** — WeasyPrint with Pango, plus Chromium
    - **Graph images** — Playwright + Chromium pre-installed
    - **Web dashboard** — all assets vendorized (no external CDN calls)
    - **Non-root execution** — runs as unprivileged `osint` user

    No additional setup steps required beyond configuring your AI provider.

---

## Configuration

All OSINT-D2 configuration uses the `OSINT_D2_` prefix. Edit your `.env` file:

### AI Provider (required — pick one)

| Variable | Description | Example |
|----------|-------------|---------|
| `OSINT_D2_AI_PROVIDER` | Provider name | `deepseek`, `openai`, `ollama` |
| `OSINT_D2_AI_API_KEY` | API key (not needed for Ollama) | `sk-xxxxxxxx` |
| `OSINT_D2_AI_BASE_URL` | Provider endpoint (optional) | `http://ollama:11434/v1` |
| `OSINT_D2_AI_MODEL` | Model to use (optional) | `deepseek-chat` |

### Optional Services

| Variable | Description |
|----------|-------------|
| `OSINT_D2_PROXY_API_KEY` | ScrapingAnt proxy key for anti-bot bypass |
| `OSINT_D2_PROXY_USERNAME` | ScrapingAnt proxy username |
| `OSINT_D2_PROXY_MODE` | `residential` or `datacenter` |
| `OSINT_D2_PROXY_COUNTRY` | 2-letter country code (e.g. `us`) |

!!! warning "Wrong variable names"
    Previous versions of the documentation used `DEEPSEEK_API_KEY` and `OPENAI_API_KEY` — those are **wrong**. All variables use the `OSINT_D2_` prefix.

### Passing Variables

=== "`.env` file (recommended)"

    ```env
    OSINT_D2_AI_PROVIDER=deepseek
    OSINT_D2_AI_API_KEY=sk-xxxxxxxxxxxxxxxx
    ```

    ```bash
    docker compose up -d
    ```

=== "Inline"

    ```bash
    docker run -p 127.0.0.1:8000:8000 \
      -e OSINT_D2_AI_PROVIDER=deepseek \
      -e OSINT_D2_AI_API_KEY=sk-xxx \
      ghcr.io/doble-2/osint-d2
    ```

=== "Docker Compose override"

    ```yaml
    # docker-compose.override.yml
    services:
      osint-d2:
        environment:
          - OSINT_D2_AI_PROVIDER=deepseek
          - OSINT_D2_AI_API_KEY=sk-xxx
    ```

---

## LAN / Network Access

By default, Compose publishes the dashboard on `127.0.0.1` only. The dashboard has **no authentication**: anyone who can reach the port can start investigations (spending your AI credits) and download dossiers. To expose it on a trusted network, set `OSINT_BIND`. Read [Security & Responsible Use](security.md) first. The server only answers to `localhost` and `127.0.0.1`, to block DNS rebinding, so also list every other address you use in `OSINT_D2_CORS_ORIGINS`:

```env
OSINT_BIND=0.0.0.0
OSINT_D2_CORS_ORIGINS=http://192.168.1.100:8000,http://my-server.local:8000
```

---

## Ollama (Fully Offline)

Run LLM inference locally, so scan results don't go to an AI provider. Scans still contact the sites being checked.

```yaml
# docker-compose.override.yml
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  osint-d2:
    environment:
      - OSINT_D2_AI_PROVIDER=ollama
      - OSINT_D2_AI_BASE_URL=http://ollama:11434/v1
      - OSINT_D2_AI_MODEL=llama3.1
    depends_on:
      - ollama

volumes:
  ollama_data:
```

After starting, pull the model:

```bash
docker compose exec ollama ollama pull llama3.1
```

!!! tip "GPU passthrough"
    For Nvidia GPUs, add `deploy.resources.reservations.devices` to the Ollama service. See the [Ollama Docker docs](https://github.com/ollama/ollama/blob/main/docs/docker.md).

---

## Volumes

Reports are stored in `/app/reports` inside the container. Mount a local directory to persist them:

```yaml
volumes:
  - ./reports:/app/reports
```

!!! warning "Volume permissions"
    The container runs as user `osint` (UID 1000). Ensure the mounted directory is writable by UID 1000:

    ```bash
    mkdir -p ./reports && chmod 777 ./reports
    # or, for tighter permissions:
    chown 1000:1000 ./reports
    ```

---

## Pre-built Image

Pull the latest image from GitHub Container Registry:

```bash
docker pull ghcr.io/doble-2/osint-d2:latest
docker run --name osint-d2 -p 127.0.0.1:8000:8000 --env-file .env ghcr.io/doble-2/osint-d2
```

The image is built for `linux/amd64` and `linux/arm64` by GitHub Actions. It is for running on your own machine: the project does not operate a hosted version.

---

## Security

The container runs as a non-root user (`osint`) by default. This provides defense-in-depth: even if Chromium has a sandbox escape vulnerability, the attacker lands in an unprivileged context.

The dashboard page loads all its JavaScript, CSS, and fonts from the image. Investigations still contact the scanned sites and, unless you use Ollama, your AI provider.

The dashboard has no authentication. See [Security & Responsible Use](security.md).

---

## Health Check

The container includes a built-in health check:

```bash
docker inspect --format='{{.State.Health.Status}}' osint-d2
```

---

## Updating

```bash
docker compose pull
docker compose up -d
```

---

## Resource Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 512 MB | 1 GB |
| CPU | 1 core | 2 cores |
| Disk | 2 GB (image) | 4 GB (image + reports) |
| Ollama (optional) | 4 GB RAM | 8+ GB RAM, GPU |

The main memory consumer is Chromium, used for dashboard PDFs and graphs.
