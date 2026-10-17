# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in OSINT-D2, please report it responsibly:

1. **Do NOT** open a public GitHub issue.
2. Use [GitHub Security Advisories](https://github.com/Doble-2/osint-d2/security/advisories) to report privately.
3. You will receive a response within 48 hours.

## Security Considerations

OSINT-D2 is a reconnaissance tool. Please note:

- **API keys** are stored in `.env` files (excluded from git via `.gitignore`).
- **Proxy credentials** are passed via `httpx.Proxy(auth=...)` — never embedded in URL strings or logged.
- **HIBP requests** use k-anonymity (only the first 5 hex chars of the SHA-1 hash are sent).
- **AI analysis** may send profile data to external providers (configurable via `AI_BASE_URL`). Use Ollama for fully local processing.
- **No credentials** are stored or cached by the tool.
- **tls-client** is an optional dependency that provides TLS fingerprint evasion.

## Responsible Use

This tool is intended for **authorized security research and OSINT investigations only**. Users are responsible for ensuring compliance with applicable laws and the terms of service of queried platforms.
