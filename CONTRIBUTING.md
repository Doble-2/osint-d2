# Contributing to OSINT-D2

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
# Clone and enter the project
git clone https://github.com/Doble-2/osint-d2.git
cd osint-d2

# Create a virtual environment with Python 3.11+
python3.13 -m venv .venv
source .venv/bin/activate

# Install in editable mode with all extras
pip install -e ".[tls]"
pip install pytest pytest-asyncio ruff

# Run the test suite
pytest tests/ -v

# Run the linter
ruff check src/ tests/
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
│   ├── ai_analyst.py       # AI profiling + heuristic fallback
│   ├── breach_check.py     # HIBP integration
│   └── report_exporter.py  # HTML/PDF report generation
└── cli/                    # Typer CLI
    └── main.py             # Entry point
```

## Guidelines

1. **Follow Clean Architecture**: domain logic in `core/`, I/O in `adapters/`.
2. **Add tests** for new features in `tests/`.
3. **Run `ruff check`** before submitting a PR.
4. **Use English** for code, comments, and commit messages.
5. **Commit messages**: use [Conventional Commits](https://www.conventionalcommits.org/) (`fix:`, `feat:`, `chore:`, `refactor:`).

## Adding a New Scanner

1. Create `src/adapters/osint_sources/<platform>.py`
2. Implement the `OSINTScanner` protocol from `core/interfaces/scanner.py`
3. Register it in `core/services/identity_pipeline.py`
4. Add a test in `tests/`

## Reporting Bugs

Open an issue with:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
