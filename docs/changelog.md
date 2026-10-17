# Changelog

See [CHANGELOG.md](https://github.com/Doble-2/osint-d2/blob/main/CHANGELOG.md) for the full version history.

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
