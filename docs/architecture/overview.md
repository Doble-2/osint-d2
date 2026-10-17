# Architecture Overview

OSINT-D2 follows **Clean Architecture** principles, separating domain logic from external concerns.

## Layers

```
┌─────────────────────────────────────────────────────────┐
│                     CLI (cli/)                          │
│              Typer commands, Rich output                │
├─────────────────────────────────────────────────────────┤
│                  Adapters (adapters/)                   │
│    Scanners, AI, HTTP, Web Server, PDF, Graph Export    │
├─────────────────────────────────────────────────────────┤
│                    Core (core/)                         │
│     Domain Models, Services, Interfaces, Config         │
└─────────────────────────────────────────────────────────┘
```

### Core (`src/core/`)

Pure business logic with **no I/O dependencies**. Contains:

- **`domain/models.py`** — Pydantic models: `PersonEntity`, `SocialProfile`, `Analysis`, `PipelineResult`
- **`domain/graph_models.py`** — `GraphNode`, `GraphEdge`, `GraphExportModel` with serialization
- **`domain/language.py`** — `Language` enum for i18n
- **`interfaces/scanner.py`** — `OSINTScanner` Protocol that all scanners implement
- **`services/identity_pipeline.py`** — Main orchestrator: discovers, correlates, and profiles identities
- **`services/agent_engine.py`** — ReAct agentic loop with function-calling LLMs
- **`services/agent_tools.py`** — Tool definitions for the agent's function-calling API
- **`config.py`** — `AppSettings` (pydantic-settings) centralized configuration

### Adapters (`src/adapters/`)

I/O implementations that fulfill Core interfaces:

- **`osint_sources/`** — Platform-specific scanners (GitHub, X, Instagram, etc.)
- **`email_sources/`** — Email-based scanners (Gravatar, PGP keyservers)
- **`site_lists/`** — Data-driven scanners using Sherlock and WhatsMyName manifests
- **`ai_analyst.py`** — AI profiling with heuristic fallback (no API key = local summary)
- **`http_client.py`** — httpx wrapper with proxy, retry, and timeout policies
- **`rate_limiter.py`** — Per-domain throttling with jitter and exponential backoff
- **`report_exporter.py`** — HTML/PDF dossier generation with WeasyPrint
- **`graph_exporter.py`** — Entity graph in JSON, Canvas, HTML, PNG formats
- **`web_server.py`** — FastAPI + WebSocket real-time dashboard
- **`phone_scanner.py`** — Telecom intelligence (phonenumbers + WhatsApp)
- **`breach_check.py`** — HIBP k-anonymity integration
- **`templates/`** — Jinja2 HTML templates + i18n JSON files

### CLI (`src/cli/`)

Typer-based CLI that wires Core services to user commands. Contains presentation logic only — no business rules.

## Data Flow

```
User Input (CLI or Web)
    │
    ▼
identity_pipeline.hunt()
    │
    ├─► Username Scanners (GitHub, X, IG, ...)
    ├─► Email Scanners (Gravatar, PGP, ...)
    ├─► Sherlock Manifest (400+ sites)
    ├─► WhatsMyName Site-Lists
    ├─► Breach Check (HIBP)
    │
    ▼
PersonEntity (aggregated profiles)
    │
    ▼
AI Analyst (6D Cognitive Profile)
    │
    ▼
Report + Graph + Timeline
```

## Key Design Decisions

### Why Clean Architecture?

- **Testability**: Core services can be tested without HTTP calls or file I/O
- **Extensibility**: Adding a new scanner = 1 file in `adapters/` + 1 line in pipeline
- **Portability**: The same Core powers CLI, Web, and Docker deployments

### Why httpx over requests?

- Native async support for concurrent scanning (30+ sites simultaneously)
- Built-in proxy support with `httpx.Proxy(auth=...)` that never leaks credentials
- Typed API with proper timeout configuration

### Why Jinja2 over a JS framework?

- Zero build step — no Node.js, no webpack, no npm
- Server-side rendering for i18n (language chosen at render time)
- The dashboard is a single HTML file with inline JS for Vis.js graph rendering

### Why WeasyPrint for PDFs?

- CSS-based layout control for classified-style dossier formatting
- No headless browser dependency for basic PDF generation
- Print-quality rendering with custom fonts and gradients
