# Changelog

All notable changes to OSINT-D2 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-10-17

### Added
- **Agentic AI mode** — autonomous investigation with function-calling LLMs (DeepSeek, OpenAI, Ollama)
- **Identity pipeline** — multi-source correlation across 30+ platforms via Sherlock + WhatsMyName datasets
- **6D Cognitive Profiling** — OCEAN psychology, Geo-temporal, Tech stack, Ideology, OpSec analysis
- **Trust Anchors** — verified identity sources to filter false positives
- **PDF dossier generation** — classified-style reports with identity cards, OCEAN profiles, risk matrices
- **Web dashboard** — real-time investigation UI with entity graph (Vis.js), investigation timeline, agent console
- **Internationalization (i18n)** — full support for English, Spanish, Portuguese, Arabic, Russian (UI, AI, reports)
- **Telecom scanner** — phone number intelligence via phonenumbers + WhatsApp validation
- **Breach check** — Have I Been Pwned integration with anonymized k-anonymity queries
- **Docker deployment** — multi-stage Dockerfile with docker-compose, health checks, and environment configuration
- **CLI toolkit** — Typer-based CLI with `investigate`, `serve`, `phone`, `doctor` commands
- **Rate limiting** — per-domain throttling with jitter and exponential backoff to prevent IP bans
- **ScrapingAnt proxy** — enterprise proxy integration for bypassing anti-bot blocks
- **Graph export** — JSON, Obsidian Canvas, interactive HTML, and PNG formats
- **SVG pivot chain** — forensic flow diagram of the investigation thread
- **Vector store** — TF-IDF based stylometric correlation with accent folding and stemming
- **CI/CD** — GitHub Actions for tests (Python 3.11-3.13), Docker publish, MkDocs, PyInstaller releases

### Security
- Removed all hardcoded PII (personal phone numbers, URLs, handles) from source code and tests
- Proxy credentials passed via `httpx.Proxy(auth=...)` — never embedded in URL strings
- API keys stored in `.env` files, excluded from version control
