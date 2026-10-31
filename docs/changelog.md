# Changelog

See [CHANGELOG.md](https://github.com/Doble-2/osint-d2/blob/main/CHANGELOG.md) for the full version history.

## Unreleased

### Breaking changes

- Breach checks use the official Have I Been Pwned API and require `OSINT_D2_HIBP_API_KEY`
- `hunt` and `scan-email` send nothing to the AI provider unless you pass `--ai` or `--deep-analyze`
- `--ai-save` is off by default, and `phone --language` is removed

### CLI

- `--version`, one-line errors, exit codes `0/1/2/130`, and comma-separated targets that really split
- Results on stdout and messages on stderr, including `phone --format`
- `doctor run` checks Chromium and explains how to fix each problem

### Dashboard

- Graph zoom and pan, sessions that survive a reload, a `partial` status, and confidence levels
- Breach check option, report button, live step counter, and progress bar
- Status and errors are always shown; the form validates its fields; a notice warns when no API key is available
- All 5 languages in the investigation selector, translated logs, and a right-to-left layout for Arabic
- Accessibility: labels for all controls, keyboard focus, AA contrast, and reduced-motion support

### Security

- See [Security & Responsible Use](guides/security.md). SSRF checks cover redirects and more address ranges, dossiers no longer pass through raw HTML, and Compose publishes on loopback by default
- An API key is no longer sent to a provider other than the configured one

### Documentation

- Rewrote the dashboard guide and the API reference to match the code

## v3.0.0 (2026-10-17)

Major infrastructure hardening release for production deployment.

### Security

- **CORS lockdown** — dashboard no longer uses `allow_origins=["*"]`; restricted to localhost with `OSINT_D2_CORS_ORIGINS` override for LAN access
- **CDN elimination** — all frontend dependencies (vis-network, Font Awesome, DOMPurify) vendorized for offline operation and supply-chain safety
- **XSS defense** — SVG and report highlights sanitized with DOMPurify
- **Non-root Docker** — container runs as unprivileged `osint` user

### Docker

- **Fixed container startup** — removed `--no-root` from Poetry install that prevented the package from loading
- **Playwright cache** — properly copied to non-root user with cleanup (~400 MB savings)
- **Healthcheck** — replaced `curl` dependency with Python `urllib`
- **Smoke test** — CI now verifies container starts before publishing

### Packaging

- **PyInstaller** — `collect_all("weasyprint")` ensures PDF generation works in standalone binaries
- **PyPI metadata** — classifiers, homepage, and documentation URLs added to `pyproject.toml`

### Documentation

- Fixed incorrect `pip install osint-d2` reference in Windows installation guide
- Added `OSINT_D2_CORS_ORIGINS` to configuration reference
- Documented Docker security model (non-root, zero-CDN, batteries-included)

---

## v0.1.0 (2026-10-17)

Initial public release.

### Highlights

- **Agentic AI** — autonomous investigation with function-calling LLMs
- **30+ platform scanners** + Sherlock (400+ sites) + WhatsMyName site-lists
- **6D Cognitive Profiling** — Identity, Geo-temporal, OCEAN, Tech, Ideology, OpSec
- **Real-time web dashboard** with entity graph, investigation timeline, and agent console
- **5 languages** — English, Spanish, Portuguese, Arabic, Russian
- **Docker deployment** — one-command setup with `docker compose up -d`
- **PDF dossiers** — classified-style reports with identity cards and risk matrices
