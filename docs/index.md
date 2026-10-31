---
hide:
  - toc
  - navigation
---

<div class="os-hero" markdown>

<span class="os-hero__badge">Identity Intelligence Platform</span>

# OSINT-D2

<p class="os-hero__subtitle">
Investigate public identity data with an <strong>AI agent</strong> that follows leads and documents its evidence, or run <strong>direct scans</strong> with no AI at all.
</p>

<div class="os-hero__actions" markdown>

[:material-rocket-launch: Quick Start](getting-started/quickstart.md){ .md-button .md-button--primary }
[:material-github: Source Code](https://github.com/Doble-2/osint-d2){ .md-button }

</div>

<div class="os-stats">
<div class="os-stat">
<span class="os-stat__value">24</span>
<span class="os-stat__label">Native Scanners</span>
</div>
<div class="os-stat">
<span class="os-stat__value">9</span>
<span class="os-stat__label">Agent Tools</span>
</div>
<div class="os-stat">
<span class="os-stat__value">6D</span>
<span class="os-stat__label">Report Areas</span>
</div>
<div class="os-stat">
<span class="os-stat__value">5</span>
<span class="os-stat__label">Languages</span>
</div>
</div>

</div>

---

## What it is

OSINT-D2 is a command-line tool and local dashboard for investigating public identity data. Run direct scans without any AI, or let an agent use function calling to choose its next step: it scans what you give it, reads the results, and follows new leads such as emails and websites.

!!! warning "Use it responsibly"
    Use OSINT-D2 only for lawful, authorized investigations. Results can be wrong, and scan results go to your AI provider unless you use Ollama. Read [Security & Responsible Use](guides/security.md).

---

## Core Capabilities

<div class="os-features" markdown>

<div class="os-feature" markdown>
<span class="os-feature__icon">🤖</span>

### Agentic AI

The LLM decides which tools to invoke, interprets results, and pivots to new leads. ReAct reasoning loop with forced-report fallback when steps are exhausted.
</div>

<div class="os-feature" markdown>
<span class="os-feature__icon">🔗</span>

### Identity Triangulation

Cross-correlates usernames, emails, bios, avatars, and writing style across platforms. Perceptual avatar hashing (dHash) detects the same photo even when resized.
</div>

<div class="os-feature" markdown>
<span class="os-feature__icon">🧠</span>

### 6D Cognitive Profiling

Agent reports cover 6 areas: Identity, Geo-temporal, OCEAN Psychology, Tech Stack, Ideology, and OpSec/Attack Surface. The personality and ideology sections are speculative inferences.
</div>

<div class="os-feature" markdown>
<span class="os-feature__icon">🛡️</span>

### Trust Anchor Verification

Declare known-good sources (`--trust github:user`). The system builds a reference identity and uses 4-signal weighted scoring (name, bio, avatar, location) to filter false positives.
</div>

<div class="os-feature" markdown>
<span class="os-feature__icon">📊</span>

### PDF Dossiers

Generate reports with identity cards, profile analysis, risk matrices, and entity graphs. The CLI renders them with WeasyPrint, and the dashboard with Chromium.
</div>

<div class="os-feature" markdown>
<span class="os-feature__icon">🌍</span>

### 5 Languages, Full Stack

English, Spanish, Portuguese, Arabic, Russian in the CLI, web dashboard, profiler, and PDF reports. <a href="guides/languages/">See coverage</a>.
</div>

</div>

---

## See It In Action

<div class="os-screenshot">
<img src="assets/dashboard-report.png" alt="Dashboard showing a finished investigation with demo data">
<div class="os-screenshot__caption">Finished agent investigation in the dashboard (demo data)</div>
</div>

<div class="os-screenshot">
<img src="assets/dashboard-graph.png" alt="Investigation graph with demo data">
<div class="os-screenshot__caption">Investigation graph: each band is a line of inquiry (demo data)</div>
</div>

---

## Quick Start

```bash
git clone https://github.com/Doble-2/osint-d2.git && cd osint-d2
cp .env.example .env          # Add your AI key
mkdir -p reports
docker compose up -d           # Dashboard at http://localhost:8000
```

Or investigate from the command line:

```bash
# Quick scan with 20 native scanners, no AI
osint-d2 scan johndoe

# Autonomous AI agent with 10 reasoning steps
osint-d2 agent johndoe --ai-provider deepseek --max-steps 10

# Several targets with Sherlock (about 470 sites)
osint-d2 hunt -u johndoe,jdoe123 -e john@example.com --sherlock
```

[:material-arrow-right: Full Installation Guide](getting-started/installation.md){ .md-button .md-button--primary }
[:material-arrow-right: Agent Mode Deep Dive](guides/agent-mode.md){ .md-button }

---

## License

OSINT-D2 is released under the [MIT License](https://github.com/Doble-2/osint-d2/blob/main/LICENSE). Designed for **authorized security research**, **journalism**, and **OSINT investigations**. Users are responsible for compliance with applicable laws.
