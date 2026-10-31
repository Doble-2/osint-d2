# Installation

## Requirements

- **Python 3.11+** (tested on 3.11 through 3.14)
- **Poetry** for dependency management
- **Playwright Chromium** — required for dashboard PDFs and graph images (`playwright install chromium`)
- **Pango** — required for CLI PDFs (see [system dependencies](#system-dependencies))

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
    mkdir -p reports   # Otherwise Docker creates it as root, and reports fail to save
    docker compose up -d
    ```

    !!! success "Batteries included"
        The Docker image includes all native dependencies (Cairo, Pango, Chromium). **No additional system setup needed** — PDFs, graph PNGs, and the web dashboard work out of the box.

    See the [Docker Deployment guide](../guides/docker.md) for full configuration.

=== "Standalone Binary"

    Download a build from [GitHub Releases](https://github.com/Doble-2/osint-d2/releases), or build your own:

    ```bash
    git clone https://github.com/Doble-2/osint-d2.git
    cd osint-d2
    poetry install
    poetry run pip install "pyinstaller>=6.6"
    poetry run pyinstaller -y packaging/pyinstaller/osint-d2.spec
    ```

    The binary is output to `dist/osint-d2/`. Then install what it needs:

    ```bash
    # Required for dashboard PDFs and graph images:
    playwright install chromium

    # Required for PDF generation (system packages):
    # Ubuntu: sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
    # macOS:  brew install pango
    ```

    !!! warning "Native dependencies"
        The standalone binary bundles Python code but **not** native system libraries. CLI PDFs require Pango on the host, and dashboard PDFs and graph images require Chromium.

---

## System Dependencies

Playwright and WeasyPrint require native libraries for headless browser rendering and PDF generation.

=== "Ubuntu / Debian"

    ```bash
    sudo apt-get update && sudo apt-get install -y \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz-subset0 \
        shared-mime-info
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install -y pango
    ```

=== "macOS"

    ```bash
    brew install pango
    ```

=== "Windows"

    Follow the [WeasyPrint Windows instructions](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows) for PDF support, then:

    ```bash
    git clone https://github.com/Doble-2/osint-d2.git
    cd osint-d2
    pip install -e .
    playwright install chromium
    ```

    !!! note "PyPI"
        OSINT-D2 isn't on PyPI yet, so install from the repository.

---

## AI Provider Setup

Direct scans work without an LLM. Agent Mode needs one, and AI analysis uses it when available. Choose one:

=== "DeepSeek (default)"

    1. Get an API key at [platform.deepseek.com](https://platform.deepseek.com)
    2. Configure:

    ```env
    OSINT_D2_AI_PROVIDER=deepseek
    OSINT_D2_AI_API_KEY=sk-xxxxxxxxxxxxxxxx
    ```

=== "OpenAI"

    ```env
    OSINT_D2_AI_PROVIDER=openai
    OSINT_D2_AI_API_KEY=sk-xxxxxxxxxxxxxxxx
    ```

=== "Ollama (local)"

    1. Install [Ollama](https://ollama.ai)
    2. Pull a model: `ollama pull llama3.1`
    3. Configure:

    ```env
    OSINT_D2_AI_PROVIDER=ollama
    OSINT_D2_AI_MODEL=llama3.1
    ```

    No API key needed. Inference stays on your machine, although scans still contact the sites being checked.

---

## Verify Installation

Run the built-in diagnostic tool:

```bash
poetry run osint-d2 doctor run
```

This checks:

- AI provider configuration (key, base URL, model)
- HTTP connectivity (outbound request to GitHub)
- WeasyPrint PDF rendering
- Playwright Chromium
- Have I Been Pwned key
- Proxy configuration (ScrapingAnt mode, key, country)

It lists how to fix each problem, and exits with code 1 if a check fails.

---

## Configuration File

OSINT-D2 reads settings from environment variables, the user config, and a `.env` in the current directory. See [where settings come from](configuration.md#where-settings-come-from).

All variables use the `OSINT_D2_` prefix. See the [Configuration reference](configuration.md) for the full list.

---

## Sherlock (About 470 Sites)

OSINT-D2 includes a **built-in async Sherlock engine** — no external packages required.

When you pass `--sherlock` to the `hunt` command, OSINT-D2 automatically downloads the official Sherlock site manifest (`data.json`) from GitHub and runs checks across its sites using its own concurrent runner.

```bash
osint-d2 hunt -u johndoe --sherlock
```

!!! tip "No `pip install sherlock-project` needed"
    Unlike earlier versions, OSINT-D2 v3.0 does not depend on the `sherlock-project` pip package. The manifest is fetched on demand and cached locally in `data/`.
