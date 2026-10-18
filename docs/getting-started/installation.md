# Installation

## Requirements

- **Python 3.11+** (tested on 3.11, 3.12, 3.13)
- **Poetry** for dependency management
- **Playwright Chromium** — required for graph PNG rendering (manual install: `playwright install chromium`)

---

## Install

=== "Poetry (recommended)"

    ```bash
    git clone https://github.com/Doble-2/osint-d2.git
    cd osint-d2
    poetry install
    poetry run playwright install chromium
    ```

=== "pip"

    ```bash
    git clone https://github.com/Doble-2/osint-d2.git
    cd osint-d2
    pip install -e .
    playwright install chromium
    ```

=== "Docker"

    ```bash
    git clone https://github.com/Doble-2/osint-d2.git
    cd osint-d2
    cp .env.example .env
    docker compose up -d
    ```

    !!! success "Batteries included"
        The Docker image includes all native dependencies (Cairo, Pango, Chromium). **No additional system setup needed** — PDFs, graph PNGs, and the web dashboard work out of the box.

    See the [Docker Deployment guide](../guides/docker.md) for full configuration.

=== "Standalone Binary (PyInstaller)"

    ```bash
    git clone https://github.com/Doble-2/osint-d2.git
    cd osint-d2
    poetry install
    pyinstaller -y packaging/pyinstaller/osint-d2.spec
    ```

    The binary is output to `dist/osint-d2/`. After building:

    ```bash
    # Required for graph PNG rendering:
    playwright install chromium

    # Required for PDF generation (system packages):
    # Ubuntu: sudo apt-get install libcairo2 libpango-1.0-0 libgdk-pixbuf-2.0-0
    # macOS:  brew install cairo pango gdk-pixbuf
    ```

    !!! warning "Native dependencies"
        The standalone binary bundles Python code but **not** native system libraries. PDF generation requires Cairo/Pango on the host, and graph PNG rendering requires a Chromium install via Playwright.

---

## System Dependencies

Playwright and WeasyPrint require native libraries for headless browser rendering and PDF generation.

=== "Ubuntu / Debian"

    ```bash
    sudo apt-get update && sudo apt-get install -y \
        libgdk-pixbuf-2.0-0 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libffi-dev \
        shared-mime-info
    ```

    !!! warning "Debian Trixie / bookworm"
        The package is `libgdk-pixbuf-2.0-0` (with hyphens), **not** `libgdk-pixbuf2.0-0` (without hyphens). The latter was deprecated in recent Debian versions.

=== "Fedora / RHEL"

    ```bash
    sudo dnf install -y \
        gdk-pixbuf2 \
        pango \
        cairo
    ```

=== "macOS"

    ```bash
    brew install cairo pango gdk-pixbuf libffi
    ```

=== "Windows"

    Install [GTK3 runtime](https://github.com/nickvdyck/weasyprint-win) for WeasyPrint PDF support, then:

    ```bash
    git clone https://github.com/Doble-2/osint-d2.git
    cd osint-d2
    pip install -e .
    playwright install chromium
    ```

    !!! note "PyPI"
        Once published, you'll also be able to install with `pip install osint-d2`.

---

## AI Provider Setup

OSINT-D2 requires an LLM provider for Agent Mode and AI analysis. Choose one:

=== "DeepSeek (default, cheapest)"

    1. Get an API key at [platform.deepseek.com](https://platform.deepseek.com)
    2. Configure:

    ```env
    OSINT_D2_AI_PROVIDER=deepseek
    OSINT_D2_AI_API_KEY=sk-xxxxxxxxxxxxxxxx
    OSINT_D2_AI_BASE_URL=https://api.deepseek.com
    OSINT_D2_AI_MODEL=deepseek-chat
    ```

=== "OpenAI"

    ```env
    OSINT_D2_AI_PROVIDER=openai
    OSINT_D2_AI_API_KEY=sk-xxxxxxxxxxxxxxxx
    OSINT_D2_AI_BASE_URL=https://api.openai.com/v1
    OSINT_D2_AI_MODEL=gpt-4o-mini
    ```

=== "Ollama (fully offline)"

    1. Install [Ollama](https://ollama.ai)
    2. Pull a model: `ollama pull llama3.1`
    3. Configure:

    ```env
    OSINT_D2_AI_PROVIDER=ollama
    OSINT_D2_AI_BASE_URL=http://localhost:11434/v1
    OSINT_D2_AI_MODEL=llama3.1
    ```

    No API key needed — everything runs locally.

---

## Verify Installation

Run the built-in diagnostic tool:

```bash
poetry run osint-d2 doctor run
```

This checks:

- AI provider configuration (key, base URL, model)
- HTTP connectivity (outbound request to GitHub)
- WeasyPrint PDF rendering capability
- Proxy configuration (ScrapingAnt mode, key, country)

!!! note "What `doctor run` does NOT check"
    It does not verify Python version, installed packages, or Playwright browser availability. To verify Playwright, run `playwright install chromium` and check for errors.

---

## Configuration File

OSINT-D2 reads configuration from two locations (in priority order):

1. **Project `.env`** — in the repository root (development)
2. **User config** — `~/.config/osint-d2/.env` (cross-platform, PyInstaller-compatible)

All variables use the `OSINT_D2_` prefix. See the [Configuration reference](configuration.md) for the full list.

---

## Sherlock (400+ Sites)

OSINT-D2 includes a **built-in async Sherlock engine** — no external packages required.

When you pass `--sherlock` to the `hunt` command, OSINT-D2 automatically downloads the official Sherlock site manifest (`data.json`) from GitHub and runs checks across 400+ sites using its own concurrent runner.

```bash
osint-d2 hunt -u johndoe --sherlock
```

!!! tip "No `pip install sherlock-project` needed"
    Unlike earlier versions, OSINT-D2 v3.0 does not depend on the `sherlock-project` pip package. The manifest is fetched on demand and cached locally in `data/`.
