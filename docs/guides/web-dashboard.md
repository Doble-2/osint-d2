# Web Dashboard

The OSINT-D2 web dashboard provides a real-time investigation interface powered by FastAPI and WebSockets.

## Launching

```bash
# Local
osint-d2 serve --host 127.0.0.1 --port 8000

# Docker
docker compose up -d
# Dashboard at http://localhost:8000
```

## Interface Overview

### Sidebar — Investigation Vectors

The left panel configures your investigation:

- **Primary Identity**: The target's real name (required)
- **Usernames**: Known handles, comma-separated
- **Communication Channels**: Email addresses and phone numbers
- **Trust Anchors**: Verified sources (e.g., `github:username`) that filter false positives
- **Configuration**: Investigation mode, AI provider, language, max steps

### Main Area — Three Views

Switch between views using the tab bar:

#### 📊 Graph View
Real-time entity graph built with Vis.js. Nodes represent discovered entities (profiles, emails, phones, breaches) and edges show relationships. The graph updates live as the agent discovers new connections.

- **Green nodes**: Target and verified identities
- **Cyan nodes**: Confirmed platform profiles
- **Red nodes**: Security exposures and breaches
- **Grey nodes**: Aggregated unconfirmed scans

#### 🕐 Timeline View
Vertical investigation thread showing the sequence of pivots. Each step shows:
- What was discovered
- Which tool produced it
- Correlation confidence
- Concrete evidence chips (phone numbers, emails, follower counts)

#### 💻 Console View
Real-time agent reasoning log. Shows each step's thought process, tool invocations, and results. Color-coded:
- **Teal**: Agent reasoning steps
- **Red**: Errors
- **Grey**: Tool outputs

### Report Drawer

When the investigation completes, the Final Dossier drawer opens with:
- **Confidence score** (0-100%)
- **Key highlights** from the analysis
- **Summary** of findings

### Actions

- **Start Investigation**: Launches the investigation (shows loading state while running)
- **Cancel**: Stops the running investigation
- **Download PDF**: Downloads the classified-style PDF dossier
- **Download Canvas**: Downloads the Obsidian Canvas graph

## Language Selector

Use the `?lang=XX` query parameter or the sidebar dropdown to switch the UI language:

- `http://localhost:8000/?lang=en` — English
- `http://localhost:8000/?lang=es` — Spanish
- `http://localhost:8000/?lang=pt` — Portuguese
- `http://localhost:8000/?lang=ar` — Arabic
- `http://localhost:8000/?lang=ru` — Russian

The language persists across sessions via the URL parameter.
