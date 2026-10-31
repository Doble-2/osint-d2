# REST API Endpoints

The server exposes a small API for starting investigations and downloading their results. Progress is delivered over the [WebSocket](websocket.md).

```
http://localhost:8000
```

!!! warning "No authentication"
    The API has no login by design, because it is for local use. See [Security & Responsible Use](../guides/security.md).

FastAPI also serves generated schemas at `/docs` and `/openapi.json`.

---

## `GET /` — Dashboard

Returns the dashboard page.

| Query parameter | Type | Description |
|-----------------|------|-------------|
| `lang` | string | `en`, `es`, `pt`, `ar`, or `ru`. Unknown values fall back to `en` |

---

## `POST /api/investigate` — Start an investigation

Starts a background investigation and returns immediately.

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

| Field | Type | Default | Rules |
|-------|------|---------|-------|
| `target` | string | Required | 1–200 characters, not blank |
| `usernames` | string[] | `[]` | Up to 50 |
| `emails` | string[] | `[]` | Up to 50 |
| `phones` | string[] | `[]` | Up to 20 |
| `trust_anchors` | string[] | `[]` | Up to 50 |
| `mode` | string | `agent` | `agent` or `phone` |
| `ai_provider` | string | Configured provider | `deepseek`, `openai`, or `ollama` |
| `language` | string | `es` | `en`, `es`, `pt`, `ar`, or `ru` |
| `max_steps` | integer | `6` | 1–30 |
| `enable_breach_check` | boolean | `false` | Requires `OSINT_D2_HIBP_API_KEY` |

`phone` mode only looks up `phones`, without the AI agent. Choosing a provider other than `OSINT_D2_AI_PROVIDER` runs without `OSINT_D2_AI_API_KEY`, so the key never reaches another service.

**Response `200`:**

```json
{
  "investigation_id": "3f2a9c1e7b6d4e8fa1b2c3d4e5f60718",
  "status": "started",
  "target": "John Doe"
}
```

| Status | Meaning |
|--------|---------|
| `422` | The request failed validation |
| `429` | 5 investigations are already running |

A `200` only means the investigation started. Failures that happen later, such as a missing API key, arrive as WebSocket events.

---

## `POST /api/cancel/{investigation_id}` — Cancel

Stops a running investigation immediately.

```json
{
  "status": "cancelled",
  "investigation_id": "3f2a9c1e7b6d4e8fa1b2c3d4e5f60718"
}
```

If the investigation already ended, `status` holds its final state. An unknown ID returns `404`.

---

## `GET /api/download/{investigation_id}/{file_type}` — Download a file

| `file_type` | Content | Content type |
|-------------|---------|--------------|
| `pdf` | PDF dossier | `application/pdf` |
| `canvas` | Obsidian Canvas graph | `application/json` |

| Status | Meaning |
|--------|---------|
| `400` | Unsupported `file_type` |
| `404` | Unknown investigation, or the file does not exist |

Each file is ready once the WebSocket sends its `artifact` event. Only files from that investigation are served.

!!! note "Sessions live in memory"
    Sessions are lost when the server restarts, and the oldest finished ones are dropped after 100. The files remain in `reports/`, but these endpoints can no longer serve them.

---

## Example

```bash
ID=$(curl -s localhost:8000/api/investigate \
  -H 'Content-Type: application/json' \
  -d '{"target": "John Doe", "usernames": ["johndoe"], "language": "en"}' \
  | jq -r .investigation_id)

# After the "artifact" event for the PDF:
curl -o dossier.pdf "localhost:8000/api/download/$ID/pdf"
```
