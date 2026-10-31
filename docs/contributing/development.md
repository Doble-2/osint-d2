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

# Install the Playwright browser used for dashboard PDFs and graphs
poetry run playwright install chromium

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
poetry run ruff check .

# Auto-fix
poetry run ruff check . --fix
```

## Running Locally

```bash
# CLI mode
poetry run osint-d2 scan johndoe

# Web dashboard
poetry run osint-d2 serve --port 8000

# Doctor (environment diagnostics)
poetry run osint-d2 doctor run

# Show the full traceback for an unexpected error
OSINT_D2_DEBUG=1 poetry run osint-d2 scan johndoe
```

## Documentation

```bash
pip install mkdocs-material mkdocs-minify-plugin
mkdocs serve                # Preview at http://127.0.0.1:8000
mkdocs build --strict       # What to run before opening a pull request
```

Screenshots and examples must use fictitious data. Never publish real people's data.

## Docker Development

`docker-compose.yml` pulls the published image, so build your own image directly:

```bash
docker build -t osint-d2:dev .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env osint-d2:dev
```

The image doesn't include the tests or development tools, so run the tests with Poetry.

## Project Layout

```
osint-d2/
├── src/
│   ├── core/              # Domain models and services
│   ├── adapters/          # I/O implementations
│   └── cli/               # Typer app; one module per command in cli/commands/
├── tests/                 # pytest test suite
├── docs/                  # MkDocs documentation
├── .github/workflows/     # CI/CD pipelines
├── pyproject.toml         # Poetry config
├── Dockerfile             # Multi-stage Docker build
└── docker-compose.yml     # Compose config
```

## Code Style

- **Language**: English for code, comments, commit messages
- **Architecture**: domain models and orchestration in `core/`, integrations in `adapters/`
- **Commits**: [Conventional Commits](https://www.conventionalcommits.org/)
- **Linter**: Ruff (E, F, W rules)
- **Types**: Pydantic models for all data, Protocol for interfaces
