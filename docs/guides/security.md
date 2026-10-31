# Security & Responsible Use

OSINT-D2 collects and infers information about people. Treat its server and its output as sensitive.

## A local tool, not a service

OSINT-D2 is open-source software that you run yourself. For ethical and legal reasons, the project doesn't operate a hosted version, and it never receives your investigations. You decide how to use it, and you are responsible for that use.

The dashboard has **no authentication, by design**, because it's meant for your own machine. Anyone who can reach it can start investigations, spend your AI credits, and download results if they have the investigation ID. Don't expose it to other people or to the internet.

| Setup | Default bind |
|-------|--------------|
| `osint-d2 serve` | `127.0.0.1` |
| `docker compose up` | `127.0.0.1` (change with `OSINT_BIND`) |
| `docker run -p 8000:8000` | **All interfaces.** Use `-p 127.0.0.1:8000:8000` |

To reach your own instance on a remote machine, use an SSH tunnel:

```bash
ssh -L 8000:127.0.0.1:8000 user@server
```

## Protecting results

- `reports/` holds personal data, so restrict access to it. Set `OSINT_D2_REPORT_RETENTION_DAYS` to delete old reports automatically, or use `osint-d2 purge`. Without a retention period, reports stay until you delete them.
- Unless you use Ollama, scan results are sent to your AI provider. Check that provider's data policy. CLI scans send nothing to an AI provider unless you pass `--ai` or `--deep-analyze`.
- Breach checks send the full email address to Have I Been Pwned.
- The dashboard keeps the form in the browser tab until you close it. Close the tab on shared machines.
- API keys saved with `osint-d2 doctor setup-ai` are stored in a file only your user can read.

## Untrusted content

Profiles and web pages are written by third parties, and may try to manipulate the agent. OSINT-D2 applies these protections:

| Risk | Protection |
|------|------------|
| Text that gives the LLM instructions | Tool results are wrapped as untrusted data and limited in size. This reduces the risk but cannot eliminate it, so review the findings |
| Requests to internal services (SSRF) | Agent URLs are checked at every redirect, and private, reserved, and metadata addresses are blocked |
| HTML or scripts in a dossier | Report Markdown escapes raw HTML and removes unsafe links |
| PDF rendering | Image requests cannot reach internal addresses or follow redirects, and only the dossier itself can be read from disk. The dashboard renders without JavaScript |
| Other sites reaching your local server | Unknown hosts are rejected, which blocks DNS rebinding, and so are WebSocket connections from foreign origins |

### Known limits

- **DNS rebinding:** a hostname that changes its answer between the check and the request can bypass the SSRF check.
- **External requests in PDFs:** rendering a dossier fetches its fonts from Google Fonts and the avatars of the profiles found, which reveals your IP address to those servers.

## Responsible use

Use OSINT-D2 only where you have a lawful basis and, where required, authorization. You are responsible for complying with the laws that apply to you.

Before running or sharing an investigation, keep in mind:

- **Privacy law may apply even to public data.** Under the EU's GDPR, for example, collecting and profiling personal data needs a legal basis.
- **Political views and personality are sensitive inferences.** They touch categories that can receive extra protection, so personality, ideology, and attack-surface sections are off by default. Get legal advice before enabling them or using them in decisions about someone.
- **Results can be wrong.** Namesakes and model errors are common, and the personality and ideology sections are speculative. Do not treat them as fact without corroboration.
- **Do not use it to harass, stalk, or expose anyone.**

See also the [threat model](../threat-model.md), [acceptable use policy](../legal/acceptable-use.md), [data flows](../legal/data-flows.md), and [impact assessment template](../legal/dpia-template.md).

To report a vulnerability, see the [security policy](https://github.com/Doble-2/osint-d2/blob/main/SECURITY.md).
