# Agent Mode

OSINT-D2's Agent Mode uses **agentic AI with function calling** to autonomously investigate identities. Instead of running a fixed sequence of scanners, the AI decides which tools to invoke, interprets results, and pivots to new leads — just like a human analyst would.

## How It Works

```
┌─────────────────────────────────────────┐
│              LLM (ReAct Loop)           │
│                                         │
│  1. Observe → current evidence          │
│  2. Think  → what should I look for?    │
│  3. Act    → call a tool                │
│  4. Repeat → until confident or limit   │
└─────────────┬───────────────────────────┘
              │ function calls
              ▼
┌─────────────────────────────────────────┐
│           Available Tools               │
│                                         │
│  • scan_username    • scan_email        │
│  • search_breaches  • scan_phone        │
│  • scrape_url       • scan_sherlock     │
│  • scan_site_lists  • generate_report   │
└─────────────────────────────────────────┘
```

### Step-by-step

1. **You provide** a target name + initial usernames/emails
2. **The AI receives** the target context and available tools
3. **Each step**, the AI decides which tool to call and with what arguments
4. **Tool results** are fed back to the AI as observations
5. **The AI pivots** — e.g., finds an email in a GitHub profile → scans that email → finds linked accounts
6. **After N steps** (configurable), the AI generates a 6D cognitive profile

## Available Tools

| Tool | Description |
|------|-------------|
| `scan_username` | Scan a username across default OSINT sources (GitHub, X, Instagram, etc.) |
| `scan_email` | Pivot from an email address (Gravatar, PGP keyservers, HIBP) |
| `scan_sherlock` | Deep scan across 400+ platforms via the Sherlock manifest |
| `scan_site_lists` | WhatsMyName-style data-driven site checks |
| `scan_phone` | Telecom intelligence: carrier, country, WhatsApp status |
| `scrape_url` | Extract metadata from any URL (emails, social links, OG data) |
| `search_breaches` | Check credentials against HIBP using k-anonymity |
| `generate_report` | Finalize the investigation with a 6D cognitive profile |

## Configuration

### CLI

```bash
osint-d2 agent -u johndoe --provider deepseek --max-steps 10
```

### Web Dashboard

Select **AI Agent** mode in the sidebar, configure the provider and max steps, then click **Start Investigation**.

### Environment

```env
OSINT_D2_AGENT_MAX_STEPS=10       # Default max reasoning steps
OSINT_D2_AI_PROVIDER=deepseek     # deepseek, openai, ollama
OSINT_D2_AI_MODEL=deepseek-chat   # Model to use
```

## 6D Cognitive Profile

When the agent finishes, it generates a structured analysis across 6 dimensions:

| Dimension | What it analyzes |
|-----------|-----------------|
| **Identity** | Real name, aliases, handle patterns, profile consistency |
| **Geo-temporal** | Timezone, language, location signals, activity patterns |
| **OCEAN Psychology** | Big Five personality traits inferred from writing style and content |
| **Tech Stack** | Programming languages, frameworks, tools, platforms |
| **Ideology** | Interests, causes, political signals, community affiliations |
| **OpSec** | Privacy hygiene, data exposure, handle reuse, email patterns |

## Tips

- **More steps = deeper investigation** — 6 steps is good for quick scans, 10-15 for thorough investigations
- **Trust anchors** help the AI filter false positives (e.g., `github:johndoe` confirms that GitHub profile is the real target)
- **Ollama** works fully offline — no data leaves your machine
- The agent **never fabricates data** — every claim traces back to a tool observation
