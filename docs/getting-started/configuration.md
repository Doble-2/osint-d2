# Configuration

OSINT-D2 is configured via environment variables. Create a `.env` file from the template:

```bash
cp .env.example .env
```

Or use the interactive setup:

```bash
osint-d2 doctor setup-ai
```

## Where Settings Come From

From highest to lowest priority:

1. Environment variables
2. User config: `~/.config/osint-d2/.env` on Linux, `~/Library/Application Support/osint-d2/.env` on macOS, `%APPDATA%\\osint-d2\\.env` on Windows
3. `.env` in the current directory

So the user config overrides a project `.env`. `osint-d2 doctor setup-ai` and `--ai-save` write to the user config, so if a project setting seems to be ignored, check that file.

## Environment Variables

### AI Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_D2_AI_PROVIDER` | `deepseek` | Provider this configuration belongs to: `deepseek`, `openai`, `ollama`. The dashboard sends the API key only to this provider. |
| `OSINT_D2_AI_API_KEY` | — | API key for the AI provider. Required for AI analysis and agent mode. Supports DeepSeek, Groq, OpenRouter, or any OpenAI-compatible API. |
| `OSINT_D2_AI_BASE_URL` | From the provider | Base URL for the AI API. Set it for other OpenAI-compatible services, or Ollama in another container. |
| `OSINT_D2_AI_MODEL` | From the provider | Model name to use for analysis. |
| `OSINT_D2_AI_TIMEOUT_SECONDS` | `45` | Timeout in seconds for AI API calls. |
| `OSINT_D2_AI_MAX_RETRIES` | `3` | Max retries on transient AI failures (rate limits, network errors). |

### Breach Checks

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_D2_HIBP_API_KEY` | — | [Have I Been Pwned API key](https://haveibeenpwned.com/API/Key), a paid service. Required for `--breach-check`. HIBP receives the full email address. |

### Proxy (ScrapingAnt)

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_D2_PROXY_API_KEY` | — | ScrapingAnt API key. Enables proxy routing for all scanner requests. |
| `OSINT_D2_PROXY_USERNAME` | — | ScrapingAnt username for standalone proxy products. |
| `OSINT_D2_PROXY_MODE` | `residential` when a proxy key is set, otherwise none | Proxy type: `residential` or `datacenter`. |
| `OSINT_D2_PROXY_COUNTRY` | — | 2-letter country code for geo-targeting (e.g., `us`, `de`, `br`). |

### HTTP & Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_D2_HTTP_TIMEOUT_SECONDS` | `20` | Timeout per HTTP request in seconds. |
| `OSINT_D2_USER_AGENT` | `osint-d2/3.0` | User-Agent header for OSINT requests. |
| `OSINT_D2_SITES_MAX_CONCURRENCY` | `30` | Max concurrent requests across all site-list scanners. |
| `OSINT_D2_REQUEST_DELAY_MS` | `200` | Minimum delay (ms) between requests to the same domain. |
| `OSINT_D2_REQUEST_JITTER_MS` | `100` | Random jitter ± (ms) added to delay for naturalness. |
| `OSINT_D2_PER_DOMAIN_CONCURRENCY` | `3` | Max simultaneous requests to the same domain. |
| `OSINT_D2_RETRY_MAX_ATTEMPTS` | `3` | Retries on 429/503 responses with exponential backoff. |

### Language & Scanning

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_D2_DEFAULT_LANGUAGE` | `en` | Default language for CLI prompts, AI analysis, and PDF reports. Options: `en`, `es`, `pt`, `ar`, `ru`. |
| `OSINT_D2_SITES_NO_NSFW` | `true` | Exclude NSFW categories from site-list scans. |
| `OSINT_D2_USERNAME_SITES_PATH` | — | Path to custom username sites JSON (WhatsMyName format). |
| `OSINT_D2_EMAIL_SITES_PATH` | — | Path to custom email sites JSON. |

### Web Server

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_D2_CORS_ORIGINS` | `http://localhost:8000,http://127.0.0.1:8000` | Comma-separated list of extra origins. The server answers only to `localhost`, `127.0.0.1`, and the hosts listed here, so set it when you open the dashboard through any other address. |
| `OSINT_BIND` | `127.0.0.1` | Docker Compose only: the host address the port is published on. The dashboard has no authentication, so see [Security](../guides/security.md) before changing it. |
| `OSINT_PORT` | `8000` | Docker Compose only: the host port. |

### Agent Mode

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_D2_AGENT_MAX_STEPS` | `10` | Maximum reasoning steps for autonomous agent investigations. |

## Provider-Specific Setup

### DeepSeek (Default)

```env
OSINT_D2_AI_PROVIDER=deepseek
OSINT_D2_AI_API_KEY=sk-your-key-here
```

### OpenAI

```env
OSINT_D2_AI_PROVIDER=openai
OSINT_D2_AI_API_KEY=sk-your-key-here
```

### Ollama (Local)

```env
OSINT_D2_AI_PROVIDER=ollama
OSINT_D2_AI_MODEL=llama3.1
# No API key needed for local Ollama
```

### Groq

```env
OSINT_D2_AI_PROVIDER=groq
OSINT_D2_AI_API_KEY=gsk_your-key-here
```
