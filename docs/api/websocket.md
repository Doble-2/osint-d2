# WebSocket Protocol

OSINT-D2 streams investigation results in real-time via WebSocket.

## Connection

```
ws://localhost:8000/ws/{investigation_id}
```

Connect after receiving the `investigation_id` from `POST /api/investigate`.

## Message Format

All messages are JSON with a `type` field and a `data` field:

```json
{
  "type": "<message_type>",
  "data": "<payload>"
}
```

## Message Types

### `log` — Agent Console Output

Text log entries from the agent's reasoning process.

```json
{
  "type": "log",
  "data": "[STEP 1/6] Scanning username johndoe across GitHub, X, Instagram..."
}
```

### `node_add` — Graph Node

A new entity discovered. Vis.js-compatible node object.

```json
{
  "type": "node_add",
  "data": {
    "id": "platform:github",
    "label": "GITHUB @johndoe\ncorrelation 85%",
    "group": "platform"
  }
}
```

### `edge_add` — Graph Edge

A new relationship between entities.

```json
{
  "type": "edge_add",
  "data": {
    "from": "target:root",
    "to": "platform:github",
    "label": "HAS_PROFILE"
  }
}
```

### `graph` — Full SVG Graph

The complete investigation graph rendered as SVG.

```json
{
  "type": "graph",
  "data": {
    "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\"...",
    "nodes": 12,
    "edges": 15,
    "vectors": 4
  }
}
```

### `graph_reset` — Clear Graph

Instructs the client to clear and rebuild the graph.

```json
{
  "type": "graph_reset",
  "data": null
}
```

### `timeline` — Investigation Timeline

The complete pivot chain as structured data.

```json
{
  "type": "timeline",
  "data": {
    "html": "<div class=\"step\">..."
  }
}
```

### `phone_data` — Telecom Results

Phone number intelligence results.

```json
{
  "type": "phone_data",
  "data": {
    "carrier": "Verizon",
    "country": "US",
    "whatsapp": true
  }
}
```

### `report_done` — Final Report

The AI analysis is complete.

```json
{
  "type": "report_done",
  "data": {
    "confidence": 0.82,
    "summary": "High-confidence identity correlation...",
    "highlights": [
      "Confirmed identity across 8 platforms",
      "Active developer with 2.3k GitHub followers"
    ]
  }
}
```

### `status` — Investigation Status Change

```json
{
  "type": "status",
  "data": "completed"
}
```

Values: `running`, `completed`, `cancelled`, `error`.

## Example Client

```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/${investigationId}`);

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  switch (msg.type) {
    case 'log':
      console.log(msg.data);
      break;
    case 'node_add':
      graph.addNode(msg.data);
      break;
    case 'report_done':
      showReport(msg.data);
      break;
    case 'status':
      if (msg.data === 'completed') ws.close();
      break;
  }
};
```
