# Contributing to OSINT-D2

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
# Clone and enter the project
git clone https://github.com/Doble-2/osint-d2.git
cd osint-d2

# Install with Poetry (recommended)
poetry install
poetry run osint-d2 doctor install-browser

# Or with pip
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
pip install pytest pytest-asyncio ruff

# Run the test suite
poetry run pytest tests/ -v

# Run the linter
poetry run ruff check .
```

## Docker Development

```bash
# Build and run locally
docker compose up --build

# Run tests inside the container
docker compose exec osint-d2 pytest tests/ -v
```

## Project Structure

```
src/
├── core/                   # Domain logic (no I/O)
│   ├── domain/models.py    # Pydantic models
│   ├── interfaces/         # Protocol-based abstractions
│   └── services/           # Orchestration (identity_pipeline)
├── adapters/               # I/O implementations
│   ├── osint_sources/      # Individual scanners (GitHub, X, etc.)
│   ├── email_sources/      # Email-based scanners (Gravatar, PGP)
│   ├── site_lists/         # Data-driven site lists (Sherlock, WMN)
│   ├── templates/          # Jinja2 templates + i18n JSON
│   ├── ai_analyst.py       # AI profiling + heuristic fallback
│   ├── breach_check.py     # HIBP integration
│   └── report_exporter.py  # HTML/PDF report generation
└── cli/                    # Typer CLI
    └── main.py             # Entry point
```

## Guidelines

1. **Follow Clean Architecture**: domain logic in `core/`, I/O in `adapters/`.
2. **Add tests** for new features in `tests/`.
3. **Run linting** before submitting: `poetry run ruff check src/ tests/`
4. **Use English** for code, comments, and commit messages.
5. **Commit messages**: use [Conventional Commits](https://www.conventionalcommits.org/) (`fix:`, `feat:`, `chore:`, `refactor:`).

## Adding a New Scanner

1. Create `src/adapters/osint_sources/<platform>.py`
2. Implement the `OSINTScanner` protocol from `core/interfaces/scanner.py`
3. Register it in `core/services/identity_pipeline.py`
4. Add a test in `tests/`
5. Update docs if the scanner adds a new capability

See the [Adding Scanners guide](https://osint-d2.angelcalderon.dev/contributing/adding-scanners/) for a detailed walkthrough.

## Adding Translations

Translation files live in `src/adapters/templates/i18n/`. To add a new language:

1. Copy `en.json` to `<code>.json` (e.g., `fr.json`)
2. Translate all values (keys must remain identical)
3. Add the language to the `Language` enum in `src/core/domain/language.py`
4. Add the option to the dashboard language selector

## Reporting Bugs

Open an issue using the [Bug Report template](https://github.com/Doble-2/osint-d2/issues/new?template=bug_report.yml) with:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
- Installation method (Docker / Poetry / pip)

## Publishing to PyPI

`.github/workflows/publish-pypi.yml` publishes every `vX.Y.Z` tag, using trusted publishing, so no password is stored. It stops if the tag doesn't match the version in `pyproject.toml`.

One-time setup:

1. Create an account on [PyPI](https://pypi.org/account/register/).
2. In [your publishing settings](https://pypi.org/manage/account/publishing/), add a pending publisher: project `osint-d2`, owner `Doble-2`, repository `osint-d2`, workflow `publish-pypi.yml`, environment `pypi`.
3. In the GitHub repository, go to **Settings > Environments** and create an environment named `pypi`. Add yourself as a required reviewer, because a published version can't be replaced.

After the first release, replace the `pipx install git+...` commands in the docs with `pipx install osint-d2`.
