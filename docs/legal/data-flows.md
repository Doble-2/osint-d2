# Data Flows

!!! warning "Draft"
    This is a draft for legal review, not legal advice. Check each provider's current terms yourself.

The project receives nothing. Data leaves your machine only through the services below, using your own accounts where they need one.

| Recipient | What it receives | When |
|-----------|------------------|------|
| Your AI provider | Target, usernames, emails, phone numbers, and collected evidence | Agent mode, `--ai`, and `--deep-analyze`. With Ollama, this stays on your machine |
| Scanned platforms (GitHub, GitLab, Reddit, X, and others) | The username, plus your IP address or your proxy's | Username scans |
| Sites in site lists and the Sherlock manifest | The username or email | Only with those options in `hunt` |
| Gravatar | A hash of the email | Email scans |
| OpenPGP and Ubuntu keyservers | The email | Email scans |
| Have I Been Pwned | The full email | Only if you enable the breach check |
| DuckDuckGo and wa.me | The phone number | Phone lookups |
| Sites the agent chooses | Your IP address or your proxy's, and the requested URL | `fetch_url` and `compare_avatars` |
| ScrapingAnt | All traffic it carries, including targets in URLs | Only if you configure the proxy |
| Google Fonts and profile image hosts | Your IP address | When rendering a dossier as a PDF |

## What stays on your machine

| Data | Location | How long |
|------|----------|----------|
| Dossiers and graphs | `reports/` | Until you delete them, or for `OSINT_D2_REPORT_RETENTION_DAYS` days |
| Running and recent investigations | The dashboard's memory | Until the server restarts, or until 100 newer sessions replace them. A purge doesn't clear this memory |
| Dashboard form | Browser tab | Until you close the tab |
| API keys | `.env` files | Until you delete them |

## Deleting data

```bash
osint-d2 purge --target johndoe --dry-run   # List the files
osint-d2 purge --target johndoe             # Delete them
osint-d2 purge --older-than 30              # Delete by age
```

`--target` needs the exact target. A `hunt` with several identifiers saves its files under a combined name, so use `--dry-run` with that name, or `--older-than`. Copies held by third parties, such as your AI provider, must be requested from them.
