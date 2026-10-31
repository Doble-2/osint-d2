# WebSocket Protocol

The WebSocket streams an investigation's progress as it runs.

## Connection

```
ws://localhost:8000/ws/{investigation_id}
```

Connect after `POST /api/investigate` returns the ID. You can connect at any time: earlier events are replayed in order, so nothing is lost if the run started or finished first.

Browser connections must come from the same origin or one listed in `OSINT_D2_CORS_ORIGINS`. Others are closed with code `1008`.

An unknown ID receives one event and the connection closes:

```json
{ "type": "error", "data": "Investigation not found." }
```

## Message format

Every message is JSON with a `type` and a `data` field. Graph events can repeat a node ID, so ignore nodes you already have.

| Type | Sent when | Modes |
|------|-----------|-------|
| [`log`](#log) | Human-readable activity | All |
| [`progress`](#progress) | A step finishes | Agent |
| [`node_add`](#node_add) | An entity is found | All |
| [`edge_add`](#edge_add) | A relationship is found | All |
| [`phone_data`](#phone_data) | A phone lookup finishes | All |
| [`report_done`](#report_done) | The AI report is ready | Agent |
| [`graph_svg`](#graph_svg) | The final graph is ready | Agent |
| [`timeline`](#timeline) | The step list is ready | Agent |
| [`artifact`](#artifact) | A file can be downloaded | Agent |
| [`status`](#status) | The investigation ends | All |

## Events

### `log`

Text in the investigation's language, for display only. Don't parse it, because its wording can change.

```json
{ "type": "log", "data": "[STEP 1] scan_username(username=johndoe)" }
```

### `progress`

`step` can stay the same across several events, because one step can call several tools. The run may finish before reaching `max_steps`.

```json
{ "type": "progress", "data": { "step": 2, "max_steps": 6 } }
```

### `node_add`

A [vis-network](https://visjs.github.io/vis-network/docs/network/nodes.html) node. Groups in use: `target`, `email`, `phone`, `identity`, `platform`, and `noise` (a probable false positive).

```json
{
  "type": "node_add",
  "data": { "id": "user:johndoe", "label": "@johndoe", "group": "platform" }
}
```

### `edge_add`

Links a node to the root, whose ID is always `target:root`. Labels in use: `PHONE_NUM`, `USES_EMAIL`, and `TRUST_ANCHOR`.

```json
{
  "type": "edge_add",
  "data": { "from": "target:root", "to": "email:john@example.com", "label": "USES_EMAIL" }
}
```

### `phone_data`

```json
{
  "type": "phone_data",
  "data": {
    "e164": "+15551234567",
    "carrier": "Example Telecom",
    "country": "United States",
    "line_type": "mobile",
    "whatsapp": true,
    "timezones": ["America/New_York"]
  }
}
```

### `report_done`

Not sent if the model produced no report. `summary` is Markdown, and `summary_html` is its server-rendered version.

```json
{
  "type": "report_done",
  "data": {
    "summary": "# Identity\n\nSame handle on **three** platforms.",
    "summary_html": "<h1>Identity</h1>\n<p>Same handle on <strong>three</strong> platforms.</p>",
    "highlights": ["Same handle on 3 platforms"],
    "confidence": 0.82
  }
}
```

!!! warning "Treat this content as untrusted"
    All of it derives from third-party pages. Sanitize `summary_html` before inserting it into a page, as the dashboard does with DOMPurify, and render `highlights` as plain text. The same applies to `svg` in `graph_svg`.

### `graph_svg`

Not sent if the graph could not be built. `confidence` is `null` when there is no report.

```json
{
  "type": "graph_svg",
  "data": {
    "target": "John Doe",
    "confidence": 0.82,
    "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\" ...>",
    "nodes": 12,
    "edges": 15,
    "vectors": 4
  }
}
```

### `timeline`

`kind` is one of `Platform`, `Email`, `Phone`, `Breach`, `Identity`, or `Finding`. `evidence` is cut to 500 characters, and `correlation` is currently always `null`.

```json
{
  "type": "timeline",
  "data": {
    "confidence": 0.82,
    "steps": [
      {
        "kind": "Platform",
        "label": "scan_username(username=johndoe)",
        "evidence": "{\"target\": \"johndoe\", ...}",
        "correlation": null
      }
    ]
  }
}
```

### `artifact`

The named file can now be [downloaded](endpoints.md#get-apidownloadinvestigation_idfile_type-download-a-file). Values: `canvas`, `pdf`.

```json
{ "type": "artifact", "data": "pdf" }
```

### `status`

Marks the end of the investigation. Values: `completed`, `partial` (finished, but a tool or file failed), `cancelled`, `failed`. With `failed`, the preceding `log` event starting with `[ERROR]` holds the reason.

```json
{ "type": "status", "data": "completed" }
```

## Example client

```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/${investigationId}`);

ws.onmessage = (event) => {
  const { type, data } = JSON.parse(event.data);

  switch (type) {
    case 'log':
      console.log(data);
      break;
    case 'artifact':
      console.log(`Ready: /api/download/${investigationId}/${data}`);
      break;
    case 'status':
      console.log(`Finished: ${data}`);
      ws.close();
      break;
  }
};
```
