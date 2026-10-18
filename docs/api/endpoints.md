# REST API Endpoints

The OSINT-D2 web server exposes a REST API for programmatic access.

## Base URL

```
http://localhost:8000
```

---

## `GET /` — Dashboard

Returns the HTML dashboard page.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `lang` | string | UI language: `en`, `es`, `pt`, `ar`, `ru` (default: `en`) |

---

## `POST /api/investigate` — Start Investigation

Launches an asynchronous investigation. Results are streamed via WebSocket.

**Request Body (JSON):**

```json
{
  "target": "John Doe",
  "usernames": ["johndoe", "jdoe123"],
  "emails": ["john@example.com"],
  "phones": ["+1 555 123 4567"],
  "trust_anchors": ["github:johndoe"],
  "mode": "agent",
  "ai_provider": "deepseek",
  "language": "en",
  "max_steps": 10,
  "enable_breach_check": false
}
```

**Response:**

```json
{
  "investigation_id": "a1b2c3d4",
  "status": "started",
  "target": "John Doe"
}
```

**Modes:**

| Mode | Description |
|------|-------------|
| `agent` | Autonomous AI investigation with function calling |
| `hunt` | Full OSINT pipeline without AI reasoning |
| `phone` | Telecom-only investigation |

---

## `POST /api/cancel/{inv_id}` — Cancel Investigation

Stops a running investigation.

**Response:**

```json
{
  "status": "cancelled",
  "investigation_id": "a1b2c3d4"
}
```

---

## `GET /api/download/{inv_id}/{file_type}` — Download Artifacts

Downloads generated artifacts from a completed investigation.

**Path Parameters:**

| Parameter | Values | Description |
|-----------|--------|-------------|
| `file_type` | `pdf` | Classified-style PDF dossier |
| `file_type` | `canvas` | Obsidian Canvas file (.canvas) |
| `file_type` | `json` | Raw investigation data (JSON) |
| `file_type` | `graph_html` | Interactive HTML entity graph |

**Response Headers:**

| File Type | Content-Type |
|-----------|-------------|
| `pdf` | `application/pdf` |
| `canvas` | `application/json` |
| `json` | `application/json` |
| `graph_html` | `text/html` |

**Error (404):**

```json
{
  "detail": "PDF not generated yet."
}
```

!!! note "File generation"
    PDF and HTML graph files are generated asynchronously during investigation. They may not be available immediately after the investigation completes — wait a few seconds for the rendering pipeline (WeasyPrint/Playwright) to finish.

---

| `running` | Investigation in progress |
| `completed` | All scanners finished |
| `cancelled` | User-cancelled |
| `error` | Failed with error |

!!! note "No dedicated status endpoint"
    Investigation status is delivered in real-time via [WebSocket](websocket.md) messages (`type: "status"`). There is no `GET /api/status/{inv_id}` endpoint — connect to the WebSocket to receive status updates.
