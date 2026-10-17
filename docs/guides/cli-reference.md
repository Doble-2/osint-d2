# CLI Reference

Complete command reference for the OSINT-D2 CLI toolkit.

## Global Usage

```bash
osint-d2 [COMMAND] [OPTIONS]
```

---

## `scan` — Quick Username Sweep

Scans a username across the default intelligence sources (GitHub, X/Twitter, Instagram, etc.).

```bash
osint-d2 scan -u <username> [OPTIONS]
```

| Flag | Description | Default |
|------|-------------|---------|
| `-u, --username` | Username to scan (required) | — |
| `--lang` | Language for AI analysis (`en`, `es`, `pt`, `ar`, `ru`) | `en` |
| `--json` | Output path for JSON export | — |

**Example:**
```bash
osint-d2 scan -u johndoe --lang en
```

---

## `scan-email` — Email Pivoting

Focused email-based investigation across Gravatar, PGP keyservers, and breach databases.

```bash
osint-d2 scan-email -e <email> [OPTIONS]
```

| Flag | Description | Default |
|------|-------------|---------|
| `-e, --email` | Email address to investigate (required) | — |
| `--lang` | Language for AI analysis | `en` |
| `--json` | Output path for JSON export | — |

---

## `hunt` — Full OSINT Pipeline

Combines all scanners: usernames, emails, Sherlock (400+ sites), WhatsMyName site-lists, and AI profiling.

```bash
osint-d2 hunt -u <usernames> [OPTIONS]
```

| Flag | Description | Default |
|------|-------------|---------|
| `-u, --username` | Comma-separated usernames | — |
| `-e, --email` | Comma-separated emails | — |
| `--sherlock / --no-sherlock` | Enable Sherlock manifest scan | `--sherlock` |
| `--sites / --no-sites` | Enable WhatsMyName site-lists | `--sites` |
| `--breach / --no-breach` | Enable HIBP breach check | `--no-breach` |
| `--lang` | Language for analysis | `en` |
| `--json` | JSON output path | — |
| `--trust-anchors` | Comma-separated verified sources | — |

**Example:**
```bash
osint-d2 hunt -u johndoe,jdoe123 -e john@example.com --sherlock --lang en
```

---

## `agent` — Autonomous AI Investigation

Launches the agentic AI that autonomously decides which tools to invoke, pivots across identities, and generates a cognitive profile.

```bash
osint-d2 agent -u <usernames> [OPTIONS]
```

| Flag | Description | Default |
|------|-------------|---------|
| `-u, --username` | Starting usernames | — |
| `-e, --email` | Starting emails | — |
| `--provider` | AI provider (`deepseek`, `openai`, `ollama`) | `deepseek` |
| `--model` | Model override | — |
| `--max-steps` | Maximum reasoning steps | `6` |
| `--lang` | Language | `en` |
| `--trust-anchors` | Verified sources | — |

**Example:**
```bash
osint-d2 agent -u johndoe --provider deepseek --max-steps 10
```

---

## `phone` — Telecom Intelligence

Reverse phone number lookup with carrier identification, country detection, and WhatsApp validation.

```bash
osint-d2 phone <phone_number> [OPTIONS]
```

| Flag | Description | Default |
|------|-------------|---------|
| `--region` | Default region for parsing (2-letter code) | `US` |
| `--lang` | Language | `en` |

**Example:**
```bash
osint-d2 phone "+1 555 123 4567" --region US
```

---

## `serve` — Web Dashboard

Launches the real-time web dashboard with WebSocket streaming.

```bash
osint-d2 serve [OPTIONS]
```

| Flag | Description | Default |
|------|-------------|---------|
| `--host` | Bind address | `127.0.0.1` |
| `--port` | Port | `8000` |

---

## `wizard` — Interactive Assistant

Step-by-step guided investigation for newcomers. Walks through target configuration, scanner selection, and output preferences.

```bash
osint-d2 wizard
```

---

## `doctor` — Environment Diagnostics

Checks your environment: Python version, dependencies, API keys, proxy configuration, and disk space.

```bash
osint-d2 doctor [SUBCOMMAND]
```

| Subcommand | Description |
|------------|-------------|
| *(none)* | Full diagnostic check |
| `setup-ai` | Interactive AI provider configuration |

---

## `analyze` — Re-run AI Analysis

Reprocesses a previously exported JSON dossier with the AI profiler. Useful for re-analyzing with a different model or language.

```bash
osint-d2 analyze <json_path> [OPTIONS]
```

| Flag | Description | Default |
|------|-------------|---------|
| `--lang` | Language for analysis | `en` |
| `--provider` | AI provider | `deepseek` |
