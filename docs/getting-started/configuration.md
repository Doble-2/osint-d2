# Configuration

OSINT-D2 is configured via environment variables. Create a `.env` file from the template:

```bash
cp .env.example .env
```

Or use the interactive setup:

```bash
osint-d2 doctor setup-ai
```

## Environment Variables

### AI Provider

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_D2_AI_API_KEY` | — | API key for the AI provider. Required for AI analysis and agent mode. Supports DeepSeek, Groq, OpenRouter, or any OpenAI-compatible API. |
| `OSINT_D2_AI_BASE_URL` | `https://api.deepseek.com` | Base URL for the AI API. Change for Ollama (`http://localhost:11434/v1`) or other providers. |
| `OSINT_D2_AI_MODEL` | `deepseek-chat` | Model name to use for analysis. |
| `OSINT_D2_AI_TIMEOUT_SECONDS` | `45` | Timeout in seconds for AI API calls. |
| `OSINT_D2_AI_MAX_RETRIES` | `3` | Max retries on transient AI failures (rate limits, network errors). |

### Proxy (ScrapingAnt)

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_D2_PROXY_API_KEY` | — | ScrapingAnt API key. Enables proxy routing for all scanner requests. |
| `OSINT_D2_PROXY_USERNAME` | — | ScrapingAnt username for standalone proxy products. |
| `OSINT_D2_PROXY_MODE` | `residential` | Proxy type: `residential` (recommended) or `datacenter`. |
| `OSINT_D2_PROXY_COUNTRY` | — | 2-letter country code for geo-targeting (e.g., `us`, `de`, `br`). |

### HTTP & Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_D2_HTTP_TIMEOUT_SECONDS` | `20` | Timeout per HTTP request in seconds. |
| `OSINT_D2_USER_AGENT` | `osint-d2/0.1` | User-Agent header for OSINT requests. |
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

### Agent Mode

| Variable | Default | Description |
|----------|---------|-------------|
| `OSINT_D2_AGENT_MAX_STEPS` | `10` | Maximum reasoning steps for autonomous agent investigations. |

## Provider-Specific Setup

### DeepSeek (Default)

```env
OSINT_D2_AI_API_KEY=sk-your-key-here
OSINT_D2_AI_BASE_URL=https://api.deepseek.com
OSINT_D2_AI_MODEL=deepseek-chat
```

### OpenAI

```env
OSINT_D2_AI_API_KEY=sk-your-key-here
OSINT_D2_AI_BASE_URL=https://api.openai.com/v1
OSINT_D2_AI_MODEL=gpt-4o-mini
```

### Ollama (Local)

```env
OSINT_D2_AI_BASE_URL=http://localhost:11434/v1
OSINT_D2_AI_MODEL=llama3.1
# No API key needed for local Ollama
```

### Groq

```env
OSINT_D2_AI_API_KEY=gsk_your-key-here
OSINT_D2_AI_BASE_URL=https://api.groq.com/openai/v1
OSINT_D2_AI_MODEL=llama-3.1-70b-versatile
```
