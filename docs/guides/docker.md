# Docker Deployment

## Quick Start

```bash
git clone https://github.com/Doble-2/osint-d2.git
cd osint-d2
cp .env.example .env
docker compose up -d
```

Open **http://localhost:8000** in your browser.

## Configuration

### Environment Variables

All configuration is done via `.env` file. Copy the example and edit:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `DEEPSEEK_API_KEY` | Yes* | DeepSeek API key for AI analysis |
| `OPENAI_API_KEY` | Yes* | OpenAI API key (alternative provider) |
| `OLLAMA_BASE_URL` | Yes* | Ollama endpoint (alternative provider) |
| `SCRAPINGANT_TOKEN` | No | ScrapingAnt proxy token for anti-bot bypass |
| `HIBP_API_KEY` | No | HaveIBeenPwned API key for breach checking |
| `OSINT_PORT` | No | Dashboard port (default: 8000) |

*At least one AI provider key is required.

### Passing Variables

=== "`.env` file (recommended)"

    ```bash
    # .env
    DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
    SCRAPINGANT_TOKEN=xxxxxxxxxxxxxxxx
    ```

    ```bash
    docker compose up -d
    ```

=== "Inline"

    ```bash
    docker run -p 8000:8000 \
      -e DEEPSEEK_API_KEY=sk-xxx \
      -e SCRAPINGANT_TOKEN=xxx \
      ghcr.io/doble-2/osint-d2
    ```

=== "Docker Compose override"

    ```yaml
    # docker-compose.override.yml
    services:
      osint-d2:
        environment:
          - DEEPSEEK_API_KEY=sk-xxx
    ```

## Volumes

Reports are stored in `/app/reports` inside the container. Mount a local directory to persist them:

```yaml
volumes:
  - ./reports:/app/reports
```

## Pre-built Image

Pull the latest image from GitHub Container Registry:

```bash
docker pull ghcr.io/doble-2/osint-d2:latest
docker run -p 8000:8000 --env-file .env ghcr.io/doble-2/osint-d2
```

## Health Check

The container includes a built-in health check. Verify status:

```bash
docker inspect --format='{{.State.Health.Status}}' osint-d2
```

## Updating

```bash
docker compose pull
docker compose up -d
```
