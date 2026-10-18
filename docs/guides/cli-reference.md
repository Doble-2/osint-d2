# CLI Reference

All commands use the `osint-d2` entry point. Use `osint-d2 <command> --help` for full details.

---

## Global Options

These options are available across most commands:

| Flag | Short | Description |
|------|-------|-------------|
| `--language` | `-l` | Output language: `en`, `es`, `pt`, `ar`, `ru` |
| `--export-json` | | Export results as JSON to `reports/` |
| `--export-pdf` | | Export a classified-style PDF dossier to `reports/` |
| `--ai-provider` | | AI provider preset: `deepseek`, `groq`, `openai`, `ollama` |
| `--ai-key` | | AI API key (prefer `osint-d2 doctor setup-ai` to avoid shell history leaks) |
| `--proxy` | | Override proxy mode: `residential`, `datacenter` |
| `--no-proxy` | | Disable proxy for this run even if configured in `.env` |
| `--proxy-country` | | 2-letter country code for geo-targeted proxy (e.g. `us`) |
| `--format` | | Terminal output format: `table` (default) or `json` |
| `--trust` | | Trust anchor (repeatable). Format: `network:username` |

---

## `scan`

Quick username sweep across the default intelligence sources.

```
osint-d2 scan <target> [OPTIONS]
```

**`target`** is a **positional argument** (not a flag).

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--deep-analyze` / `--no-deep-analyze` | `--no-deep-analyze` | Run cognitive AI analysis on collected evidence |
| `--language`, `-l` | `en` | Output language |
| `--export-pdf` / `--no-export-pdf` | `--no-export-pdf` | Export PDF dossier |
| `--export-json` / `--no-export-json` | `--no-export-json` | Export JSON to `reports/` |
| `--trust` | — | Trust anchor (repeatable): `--trust github:johndoe` |

### Examples

```bash
# Quick scan
osint-d2 scan johndoe

# Scan with AI analysis and PDF export
osint-d2 scan johndoe --deep-analyze --export-pdf --language es

# Scan with trust anchors to filter false positives
osint-d2 scan johndoe --trust github:johndoe --trust instagram:johndoe
```

---

## `scan-email`

Focused email pivoting across supported sources.

```
osint-d2 scan-email <email> [OPTIONS]
```

**`email`** is a **positional argument** (not a flag).

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--deep-analyze` / `--no-deep-analyze` | `--deep-analyze` | Run cognitive AI analysis (enabled by default for email) |
| `--scan-localpart` / `--no-scan-localpart` | `--no-scan-localpart` | Also try the local part (before `@`) as a username |
| `--language`, `-l` | `en` | Output language |
| `--export-pdf` / `--no-export-pdf` | `--no-export-pdf` | Export PDF dossier |
| `--export-json` / `--no-export-json` | `--no-export-json` | Export JSON to `reports/` |

### Examples

```bash
# Email scan
osint-d2 scan-email john@example.com

# Email scan + pivot on username "john"
osint-d2 scan-email john@example.com --scan-localpart --language es
```

---

## `hunt`

Full OSINT hunt combining usernames, emails, Sherlock, and site-lists.

```
osint-d2 hunt [OPTIONS]
```

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--usernames` | `-u` | — | Target usernames (comma-separated) |
| `--emails` | `-e` | — | Target emails (comma-separated) |
| `--sherlock` / `--no-sherlock` | | `--no-sherlock` | Enable Sherlock manifest (400+ sites) |
| `--breach-check` / `--no-breach-check` | | `--no-breach-check` | Query HaveIBeenPwned for breaches |
| `--ai` / `--noai` | | `--ai` | Run cognitive AI analysis |
| `--strict` / `--no-strict` | | `--no-strict` | Conservative heuristics to trim false positives |
| `--trust` | | — | Trust anchor (repeatable): `--trust github:johndoe` |
| `--scan-localpart` / `--no-scan-localpart` | | `--no-scan-localpart` | Pivot email local part as username |
| `--language`, `-l` | | `en` | Output language |
| `--export-json` / `--no-export-json` | | `--no-export-json` | Export JSON to `reports/` |
| `--export-pdf` / `--no-export-pdf` | | `--no-export-pdf` | Export PDF dossier |
| `--category` | | — | Filter site-lists by category (repeatable) |
| `--nsfw` | | `inherit` | NSFW policy: `inherit`, `exclude`, `allow` |

### Examples

```bash
# Full hunt with multiple usernames
osint-d2 hunt -u johndoe,jdoe123 -e john@example.com

# Hunt with Sherlock + breach check
osint-d2 hunt -u johndoe --sherlock --breach-check --language es

# Hunt with trust anchors
osint-d2 hunt -u johndoe --trust github:johndoe --trust instagram:johndoe
```

---

## `agent`

Autonomous OSINT investigation powered by agentic AI.

```
osint-d2 agent <objective> [OPTIONS]
```

**`objective`** is a **positional argument** — a target name, username, email, or free-form investigation objective.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--ai-provider` | — | AI provider preset: `deepseek`, `groq`, `openai`, `ollama` |
| `--max-steps` | `10` | Maximum reasoning steps before the agent concludes (1–50) |
| `--breach-check` / `--no-breach-check` | `--no-breach-check` | Allow the agent to query HaveIBeenPwned |
| `--trust` | — | Trust anchor (repeatable): `--trust github:johndoe` |
| `--language`, `-l` | `en` | Output language |
| `--export-json` / `--no-export-json` | `--no-export-json` | Export JSON to `reports/` |
| `--export-pdf` / `--no-export-pdf` | `--no-export-pdf` | Export PDF dossier |
| `--export-canvas` / `--no-export-canvas` | `--no-export-canvas` | Export Obsidian Canvas entity graph |
| `--export-html-graph` / `--no-export-html-graph` | `--no-export-html-graph` | Export interactive HTML graph |

!!! note "AI model"
    The model is configured via the `OSINT_D2_AI_MODEL` environment variable or `.env` file, not via a CLI flag. Use `osint-d2 doctor setup-ai` for interactive configuration.

### Examples

```bash
# Autonomous investigation with DeepSeek
osint-d2 agent johndoe --ai-provider deepseek

# Deep investigation with more steps + exports
osint-d2 agent johndoe --max-steps 15 --export-pdf --export-json --language es

# Agent with breach checking and trust anchors
osint-d2 agent johndoe --breach-check --trust github:johndoe
```

---

## `analyze`

Re-run the AI profiler on a previously exported JSON dossier.

```
osint-d2 analyze <input_path> [OPTIONS]
```

**`input_path`** is a **positional argument** — path to an exported JSON file (e.g. `reports/target.json`).

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--ai-provider` | — | AI provider preset |
| `--language`, `-l` | `en` | Output language |
| `--format` | `table` | Terminal output format: `table` or `json` |

### Examples

```bash
osint-d2 analyze reports/johndoe.json --language es --ai-provider deepseek
```

---

## `phone`

Telecom intelligence and reverse footprint lookup on a phone number.

```
osint-d2 phone <phone_number> [OPTIONS]
```

**`phone_number`** is a **positional argument** (e.g. `+12125551234`).

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--region` | `-r` | `US` | Default ISO country code if international prefix is omitted |
| `--language` | `-l` | `en` | Output language |
| `--export-json` | | — | Export phone intelligence report to JSON |

### Examples

```bash
osint-d2 phone +12125551234
osint-d2 phone 04241234567 --region VE --language es
```

---

## `doctor`

Environment diagnostics and configuration checks.

```
osint-d2 doctor <subcommand>
```

!!! warning "Subcommand required"
    Running `osint-d2 doctor` alone shows the help menu. You must specify a subcommand.

### Subcommands

| Subcommand | Description |
|------------|-------------|
| `run` | Run baseline diagnostics and show recommended fixes |
| `setup-ai` | Interactive AI setup (stores config in user `.env`) |

### Examples

```bash
# Run full diagnostics
osint-d2 doctor run

# Interactive AI provider setup
osint-d2 doctor setup-ai
```

---

## `serve`

Launch the real-time web dashboard (FastAPI + WebSockets).

```
osint-d2 serve [OPTIONS]
```

### Options

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--host` | `-h` | `127.0.0.1` | Host interface to bind to |
| `--port` | `-p` | `8000` | Port number |
| `--reload` | | — | Enable auto-reload for development |

### Examples

```bash
# Start dashboard on default port
osint-d2 serve

# Bind to all interfaces (LAN access)
osint-d2 serve --host 0.0.0.0 --port 9000
```

---

## `wizard`

Step-by-step interactive assistant for newcomers. No arguments required.

```bash
osint-d2 wizard
```
