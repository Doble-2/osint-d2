# Installation

## Requirements

- **Python 3.11+**
- **API Key** for at least one AI provider (DeepSeek, OpenAI, or Ollama)

## Docker (Recommended)

The fastest way to get started. No system dependencies needed.

```bash
git clone https://github.com/Doble-2/osint-d2.git
cd osint-d2
cp .env.example .env
```

Edit `.env` with your API keys:

```bash
nano .env
```

Launch:

```bash
docker compose up -d
```

The dashboard will be available at **http://localhost:8000**.

!!! tip "Custom Port"
    Set `OSINT_PORT=9090` in your environment to use a different port:
    ```bash
    OSINT_PORT=9090 docker compose up -d
    ```

## Poetry (Development)

```bash
# Clone
git clone https://github.com/Doble-2/osint-d2.git
cd osint-d2

# Install dependencies
poetry install

# Install Playwright browser for PDF generation
playwright install chromium

# Configure
cp .env.example .env
nano .env

# Launch
poetry run osint-d2 serve
```

## pip

```bash
pip install -e .
playwright install chromium
cp .env.example .env
osint-d2 serve
```

## System Dependencies

If not using Docker, you'll need these for PDF generation:

=== "Ubuntu/Debian"

    ```bash
    sudo apt-get install -y \
        libcairo2 libpango-1.0-0 libpangoft2-1.0-0 \
        libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
    ```

=== "macOS"

    ```bash
    brew install cairo pango gdk-pixbuf libffi shared-mime-info
    ```

=== "Windows"

    PDF generation uses Playwright (Chromium), which works out of the box.
    WeasyPrint-based export requires the [GTK3 Runtime](https://github.com/nickvdp/osint-d2/wiki/Windows-GTK).

## Verify Installation

```bash
osint-d2 doctor run
```

This checks: Python version, API key configuration, system dependencies, and browser availability.
