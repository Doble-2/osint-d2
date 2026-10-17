# OSINT-D2

<div align="center" markdown>

**Advanced Open-Source Intelligence Platform**

*Transform usernames and emails into structured identity dossiers powered by agentic AI.*

[:material-github: GitHub](https://github.com/Doble-2/osint-d2){ .md-button }
[:material-docker: Docker Hub](https://ghcr.io/doble-2/osint-d2){ .md-button }

</div>

---

## What is OSINT-D2?

OSINT-D2 is an **advanced open-source intelligence platform** that correlates digital identities across 30+ platforms using autonomous AI agents. From a single username or email, it builds comprehensive identity dossiers with cognitive profiling, breach analysis, and stylometric correlation.

## Key Features

| Feature | Description |
|---|---|
| :material-robot: **Agentic AI** | Autonomous investigation — the LLM decides which tools to invoke and pivots across identities |
| :material-link-variant: **Multi-source Correlation** | Links usernames, emails, and aliases across 30+ platforms |
| :material-brain: **Cognitive Profiling** | 6-dimension analysis: Identity, Geo-temporal, OCEAN psychology, Tech, Ideology, OpSec |
| :material-shield-check: **Trust Anchors** | Define verified sources to eliminate false positives |
| :material-file-pdf-box: **PDF Dossiers** | Classified-style reports with identity cards, OCEAN profiles, and risk matrices |
| :material-earth: **5 Languages** | English, Spanish, Portuguese, Arabic, Russian |
| :material-docker: **Docker Ready** | One-command deployment with `docker compose up` |

## Quick Start

=== "Docker (recommended)"

    ```bash
    git clone https://github.com/Doble-2/osint-d2.git
    cd osint-d2
    cp .env.example .env
    # Edit .env with your API keys
    docker compose up -d
    # Open http://localhost:8000
    ```

=== "Poetry"

    ```bash
    git clone https://github.com/Doble-2/osint-d2.git
    cd osint-d2
    poetry install
    playwright install chromium
    cp .env.example .env
    poetry run osint-d2 serve
    ```

=== "pip"

    ```bash
    pip install -e .
    playwright install chromium
    cp .env.example .env
    osint-d2 serve
    ```

## Architecture

```
src/
├── core/           # Domain models, services, business logic
│   ├── domain/     # PersonEntity, Language, GraphModels
│   ├── config.py   # Application settings (Pydantic)
│   └── services/   # AgentEngine, pipelines
├── adapters/       # External integrations
│   ├── ai_analyst.py        # LLM-powered analysis
│   ├── web_server.py        # FastAPI dashboard
│   ├── report_exporter.py   # PDF generation
│   └── osint_sources/       # Platform scanners
└── cli/            # Typer CLI interface
```

## License

OSINT-D2 is released under the [MIT License](https://github.com/Doble-2/osint-d2/blob/main/LICENSE).
