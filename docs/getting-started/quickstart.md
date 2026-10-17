# Quick Start

Get up and running with OSINT-D2 in under 5 minutes.

## Option 1: Docker (Recommended)

```bash
git clone https://github.com/Doble-2/osint-d2.git && cd osint-d2
cp .env.example .env          # Edit with your API keys
docker compose up -d           # Dashboard at http://localhost:8000
```

## Option 2: Poetry

```bash
git clone https://github.com/Doble-2/osint-d2.git && cd osint-d2
poetry install
playwright install chromium    # Required for PDF generation
cp .env.example .env           # Edit with your API keys
poetry run osint-d2 serve      # Dashboard at http://localhost:8000
```

## Your First Investigation

### Via Web Dashboard

1. Open `http://localhost:8000` in your browser
2. Enter a **target name** in the "Primary Identity" field
3. Add known **usernames** (comma-separated)
4. Select **AI Agent** mode
5. Click **Start Investigation**
6. Watch the real-time console, entity graph, and investigation timeline populate
7. Download the **PDF dossier** when complete

### Via CLI

```bash
# Quick username scan
osint-d2 scan -u johndoe

# Full investigation with all scanners
osint-d2 hunt -u johndoe,jdoe123 -e john@example.com --sherlock --lang en

# Autonomous AI agent mode
osint-d2 agent -u johndoe --provider deepseek --max-steps 8

# Interactive wizard (step-by-step)
osint-d2 wizard
```

## Verify Your Setup

```bash
osint-d2 doctor
```

This checks your Python environment, dependencies, API key configuration, and proxy status. Follow the interactive prompts to configure anything that's missing.

## Next Steps

- [Configuration Guide](configuration.md) — All environment variables explained
- [CLI Reference](../guides/cli-reference.md) — Complete command reference
- [Agent Mode](../guides/agent-mode.md) — How the autonomous AI works
- [Docker Guide](../guides/docker.md) — Production deployment with Docker
