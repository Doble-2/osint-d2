<p align="center">
  <img src="assets/demo.png" alt="OSINT-D2 Demo" width="700" />
</p>

<h1 align="center">OSINT-D2</h1>

<p align="center">
  <strong>Agentic OSINT • Identity Intelligence • Cognitive Profiling</strong>
</p>

<p align="center">
  <a href="https://osint-d2.angelcalderon.dev"><img src="https://img.shields.io/badge/Docs-osint--d2.angelcalderon.dev-2dd4bf?logo=readthedocs&logoColor=white" alt="Docs" /></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python" /></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker" /></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/AI-DeepSeek%20%7C%20OpenAI%20%7C%20Ollama-111827?logo=openai&logoColor=white" alt="AI" /></a>
  <a href="https://scrapingant.com/?ref=odeymdu"><img src="https://img.shields.io/badge/Proxies-ScrapingAnt-FF6B35" alt="ScrapingAnt" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-success" alt="License" /></a>
</p>

---

OSINT-D2 is an **advanced open-source intelligence platform** that transforms usernames and emails into structured identity dossiers. Powered by **agentic AI** with autonomous function calling, it delivers identity correlation, cognitive profiling, and breach analysis — all from a single command.

## Key Features

| | Feature | Description |
|---|---|---|
| 🤖 | **Agentic AI** | Autonomous investigation — the LLM decides which tools to invoke and pivots across identities |
| 🔍 | **Multi-source Correlation** | Links usernames, emails, and aliases across 30+ platforms |
| 🧠 | **6D Cognitive Profiling** | Identity, Geo-temporal, OCEAN psychology, Tech, Ideology, OpSec |
| 🛡️ | **Trust Anchors** | Verified identity sources to filter false positives |
| 📊 | **PDF Dossiers** | Classified-style reports with identity cards, OCEAN profiles, and risk matrices |
| 🌍 | **5 Languages** | English, Spanish, Portuguese, Arabic, Russian — UI, AI, and reports |
| 🐳 | **Docker Ready** | One-command deployment: `docker compose up -d` |

## Quick Start

```bash
# Docker (recommended)
git clone https://github.com/Doble-2/osint-d2.git && cd osint-d2
cp .env.example .env          # Add your API keys
docker compose up -d           # http://localhost:8000

# Or with Poetry
poetry install && playwright install chromium
poetry run osint-d2 serve
```

## Documentation

📖 **Full documentation** → **[osint-d2.angelcalderon.dev](https://osint-d2.angelcalderon.dev)**

- [Installation Guide](https://osint-d2.angelcalderon.dev/getting-started/installation/)
- [Docker Deployment](https://osint-d2.angelcalderon.dev/guides/docker/)
- [CLI Reference](https://osint-d2.angelcalderon.dev/guides/cli-reference/)
- [Agent Mode](https://osint-d2.angelcalderon.dev/guides/agent-mode/)
- [API Reference](https://osint-d2.angelcalderon.dev/api/endpoints/)
- [Architecture](https://osint-d2.angelcalderon.dev/architecture/overview/)

## Architecture

```
src/
├── core/         # Domain models, services, business logic
├── adapters/     # Scanners, AI, exporters, web server
└── cli/          # Typer CLI interface
```

Clean Architecture with clear separation between domain logic and external adapters. See the [full architecture docs](https://osint-d2.angelcalderon.dev/architecture/overview/).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. Development setup:

```bash
poetry install --with dev
poetry run pytest
poetry run ruff check .
```

## Disclaimer

This tool is designed for **authorized security research**, **journalism**, and **OSINT investigations** only. Users are responsible for complying with all applicable laws and regulations. The authors assume no liability for misuse.

## License

[MIT](LICENSE) © Doble-2
