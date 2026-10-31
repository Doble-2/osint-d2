# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 3.x     | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in OSINT-D2, please report it responsibly:

1. **Do NOT** open a public GitHub issue.
2. Use [GitHub Security Advisories](https://github.com/Doble-2/osint-d2/security/advisories) to report privately.
3. You will receive a response within 48 hours.

## Security Considerations

OSINT-D2 is a reconnaissance tool. Please note:

- **API keys** are stored in `.env` files (excluded from git via `.gitignore`).
- **Proxy credentials** are passed via `httpx.Proxy(auth=...)` — never embedded in URL strings or logged.
- **HIBP requests** send the full email address to Have I Been Pwned, and only run if you enable the breach check.
- **AI analysis** may send profile data to external providers (configurable via `OSINT_D2_AI_BASE_URL`). Use Ollama for fully local processing.
- **No credentials** are stored or cached by the tool.

## Responsible Use

This tool is intended for **authorized security research and OSINT investigations only**. Users are responsible for ensuring compliance with applicable laws and the terms of service of queried platforms.
