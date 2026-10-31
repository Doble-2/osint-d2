# Threat Model

OSINT-D2 runs locally on the machine of the person who downloads it. The project operates no server and receives no investigations. This page records what the tool protects, against whom, and which risks are accepted.

## What needs protecting

| Asset | Where it lives |
|-------|----------------|
| Personal data about investigated people | `reports/`, the dashboard's memory, and the AI provider if you use a remote one |
| API keys (AI, HIBP, proxy) | Environment variables, the project `.env`, and the user `.env` (readable only by its owner) |
| The operator's identity and IP address | Visible to scanned sites unless a proxy is configured |
| AI credits | Spent by each investigation |

## Who could cause harm

| Actor | Can do | Main protections |
|-------|--------|------------------|
| An investigated person, or anyone controlling a page or profile | Write text the agent reads, redirect requests, serve huge or slow responses | Tool results are marked as untrusted and limited in size, URLs are checked at every redirect, downloads are capped at 5 MB, and report HTML is sanitized |
| A website open in the operator's browser | Send requests to the local server | Unknown `Host` headers and foreign WebSocket origins are rejected, and CORS is limited to known origins |
| A compromised dependency or release | Run code on the operator's machine | Locked dependencies, pinned CI actions, `pip-audit`, CodeQL, and gitleaks |
| The operator | Misuse the tool against someone | [Acceptable use policy](legal/acceptable-use.md), sensitive inferences off by default. The tool cannot prevent deliberate misuse |

## Accepted risks

The project is a local, single-user tool, so these are deliberate decisions. Revisit them if that changes.

| Risk | Why it is accepted | What remains exposed |
|------|-------------------|----------------------|
| The dashboard has no login | It binds to `127.0.0.1` by default | Other local users and processes can reach it. Binding it to another interface exposes it to that network |
| DNS rebinding can bypass the SSRF check | Each request is checked, and fixing this needs a custom transport | A hostile page could make the agent reach a service on the operator's local network and read its response |
| There is no record of who investigated whom | A local tool has a single operator, and a log would be one more file of personal data | The operator must keep any record their legal basis requires |
| Prompt injection is reduced, not eliminated | No current technique removes it | A hostile page can still distort the report, so its findings need human review |
| Reports are not encrypted by the tool | Disk encryption belongs to the operating system | Anyone who can read `reports/` can read the dossiers |

## Out of scope

- Attackers who already control the operator's account or machine.
- Accuracy guarantees for AI inferences.
- The practices of third-party services. See [Data flows](legal/data-flows.md).

## Reporting a vulnerability

See the [security policy](https://github.com/Doble-2/osint-d2/blob/main/SECURITY.md).
