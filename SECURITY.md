# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in OSINT-D2, please report it responsibly:

1. **Do NOT** open a public GitHub issue.
2. Send an email to **angel@angelcalderon.dev** with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
3. You will receive a response within 48 hours.

## Security Considerations

OSINT-D2 is a reconnaissance tool. Please note:

- **API keys** are stored in `.env` files (excluded from git via `.gitignore`).
- **HIBP requests** use randomized headers to avoid fingerprinting.
- **AI analysis** may send profile data to external providers (configurable via `AI_BASE_URL`).
- **No credentials** are stored or cached by the tool.
- **tls-client** is an optional dependency that provides TLS fingerprint evasion.

## Responsible Use

This tool is intended for **authorized security research and OSINT investigations only**. Users are responsible for ensuring compliance with applicable laws and the terms of service of queried platforms.
