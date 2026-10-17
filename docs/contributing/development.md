# Development Setup

Complete guide for setting up an OSINT-D2 development environment.

## Prerequisites

- **Python 3.11+** (3.12 recommended)
- **Poetry** (dependency management)
- **Git**

## Setup

```bash
# Clone the repository
git clone https://github.com/Doble-2/osint-d2.git
cd osint-d2

# Install all dependencies (including dev extras)
poetry install

# Install Playwright browser for PDF generation
playwright install chromium

# Copy environment template
cp .env.example .env
# Edit .env with your API keys (optional for development)
```

## Running Tests

```bash
# Full test suite
poetry run pytest tests/ -v

# Specific test file
poetry run pytest tests/test_http_client.py -v

# With coverage
poetry run pytest tests/ --cov=src --cov-report=html
```

## Linting

```bash
# Check for issues
poetry run ruff check src/ tests/ --select=E,F,W --ignore=E501,E402

# Auto-fix
poetry run ruff check src/ tests/ --select=E,F,W --ignore=E501,E402 --fix
```

## Running Locally

```bash
# CLI mode
poetry run python -m cli.main scan -u johndoe

# Web dashboard
poetry run python -m cli.main serve --port 8000

# Doctor (environment diagnostics)
poetry run python -m cli.main doctor
```

## Docker Development

```bash
# Build and run
docker compose up --build

# Run tests in container
docker compose exec osint-d2 pytest tests/ -v

# Rebuild after code changes
docker compose up --build --force-recreate
```

## Project Layout

```
osint-d2/
├── src/
│   ├── core/              # Domain logic (no I/O)
│   ├── adapters/          # I/O implementations
│   └── cli/               # CLI entry point
├── tests/                 # pytest test suite
├── docs/                  # MkDocs documentation
├── assets/                # README screenshots
├── .github/workflows/     # CI/CD pipelines
├── pyproject.toml         # Poetry config
├── Dockerfile             # Multi-stage Docker build
└── docker-compose.yml     # Compose config
```

## Code Style

- **Language**: English for code, comments, commit messages
- **Architecture**: Clean Architecture — domain in `core/`, I/O in `adapters/`
- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/)
- **Linter**: Ruff (E, F, W rules)
- **Types**: Pydantic models for all data, Protocol for interfaces
