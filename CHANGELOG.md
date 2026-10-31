# Changelog

All notable changes to OSINT-D2 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- WeasyPrint's missing-library message no longer corrupts JSON output on stdout
- A hostile page can no longer freeze the server through the email search, or fill memory with a huge response
- A scan no longer fails at the end when it discovers many identifiers
- Phone lookups now use the configured proxy
- The project `.env` now takes priority over the user-wide one
- The rate limiter no longer stops every domain while one of them waits
- A failed file export no longer hides a finished report in the dashboard
- A report forced by the step limit now counts as partial
- Saving settings no longer erases a user `.env` it cannot read

### Added
- `osint-d2 doctor install-browser`, and `serve` offers to install Chromium
- The dashboard can save the AI key
- `scripts/install-docker.sh` installs with Docker without cloning the repository
- A workflow to publish to PyPI, and install tests on Linux, macOS, and Windows in CI
- `osint-d2 purge`, and automatic deletion with `OSINT_D2_REPORT_RETENTION_DAYS`
- Threat model, acceptable use policy, data flows, and an impact assessment template (drafts pending legal review)
- CodeQL and gitleaks in CI

### Security
- Tool results reach the agent wrapped as untrusted data and limited in size, and the profiler's prompt treats evidence as untrusted

### Removed
- `serve --reload`, which always exited with an error
- Unused modules `report_theme` and `activity_timeline`

### Changed
- `doctor run` treats Chromium and Pango as optional, and no longer fails without them
- Blank values in a `.env` file no longer hide settings from another file
- **Personality, ideology, and attack-surface sections are now off by default.** Enable them with `--sensitive-inferences`, the dashboard option, or `OSINT_D2_SENSITIVE_INFERENCES=true`
- Scans follow at most 25 discovered usernames and 25 discovered emails, and websites are no longer scanned as usernames
- Dashboard: the report is now a tab that opens when a run finishes, instead of a panel covering the graph
- Dashboard: a bar above the results shows the subject, the current step, and the cancel and download buttons
- Dashboard: simpler form, and the view no longer jumps between tabs while results arrive
- Documentation site: new theme and home page, with a working light mode

### Fixed
- WeasyPrint's missing-library message no longer corrupts JSON output on stdout
- Dashboard: the bundled JetBrains Mono font had almost no ASCII characters, so most text fell back to a system font
- Dashboard: the empty state did not come back after an expired run

### Security
- Selecting another provider no longer sends the configured API key to it
- SSRF guard now validates every redirect hop, covers `compare_avatars`, and blocks IPv4-embedded IPv6, multicast and reserved ranges
- Dossier Markdown no longer passes through raw HTML or unsafe link schemes; PDFs render with JavaScript disabled and internal network requests blocked
- Downloads only serve the session's own files; session IDs use the full UUID; the WebSocket rejects foreign origins
- Docker Compose publishes the dashboard on loopback by default (`OSINT_BIND` to change it)
- The user `.env` file is written with `0600` permissions

### Removed
- `tls-client` extra and browser-impersonating breach requests
- `requirements.txt`, which was out of sync with `poetry.lock`
- `phone --language`, which had no effect
- Screenshots and examples that showed real people's data

### Changed
- CLI split into `cli/commands/`, with one module per command
- Groq and Hugging Face presets updated to current models and endpoints
- GitHub Actions pinned to commit SHAs
- **Breaking:** breach checks use the official Have I Been Pwned API and require `OSINT_D2_HIBP_API_KEY`
- **Breaking:** `hunt` and `scan-email` no longer send evidence to the AI provider unless you pass `--ai` or `--deep-analyze`
- **Breaking:** `--ai-save` is off by default
- `--ai-provider` no longer reuses a key configured for another provider
- `OSINT_D2_AI_PROVIDER` sets the default endpoint and model
- WeasyPrint upgraded from 60.1 to 70; all dependencies updated
- Docker image is multi-stage, without Poetry, and is tested before publishing
- CI installs from the lockfile, tests the built wheel, audits dependencies, and covers Python 3.14

### Added
- Agent prompts and the investigation graph in all 5 languages
- Visible labels for every dashboard field
- CLI: `--version`, `phone --format`, exit codes `0/1/2/130`, one-line errors without tracebacks
- `doctor run`: Chromium and HIBP checks, fixes for each problem, exit code 1 on failure
- Dashboard: graph zoom and pan, recoverable sessions, `partial` status, confidence levels, immediate cancel, ARIA tabs
- Dashboard: breach check option, report button, step counter and progress bar, form validation, missing API key notice
- Dashboard: all 5 report languages, translated server logs, right-to-left layout for Arabic
- Dashboard accessibility: control labels, keyboard focus, AA contrast, reduced-motion support
- WebSocket events `progress` and `artifact`; `summary_html` in `report_done`
- Documentation: Security & Responsible Use guide

### Fixed
- WeasyPrint's missing-library message no longer corrupts JSON output on stdout
- CLI no longer prints API keys in tracebacks, emits JSON twice, or ignores commas in `--emails`
- `pip install` no longer pulls a Click version that breaks `--help`
- Live graph counter, hidden graph clipping, and dates shown as phone numbers in the dashboard
- Oversized AI reports are truncated instead of discarding the investigation
- Dashboard no longer hangs when an investigation fails (e.g. missing API key) or runs in phone mode
- Events emitted before the WebSocket connects are replayed instead of lost
- Agent objective contained a literal `{target}`; graph edges pointed to a nonexistent root node
- The report drawer now opens: the server never sent `report_done`
- Non-numeric LLM confidence no longer aborts a finished investigation; duplicate profiles are merged
- `ai_max_retries` is honored by the agent; the dashboard no longer overrides the configured provider or model
- Report panel no longer covers the sidebar; its placeholder `87%` confidence is gone
- Download buttons only appear for files that exist
- REST and WebSocket documentation described endpoints and events that do not exist

### Changed
- `/api/investigate` validates its input and returns 429 above 5 concurrent investigations; `/api/cancel` returns 404 for unknown sessions
- Added an `openai` provider preset

## [3.0.0] — 2026-10-17

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
