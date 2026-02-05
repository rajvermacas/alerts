# Standalone UI (No Backend)

This folder contains a static, backend-free UI that mimics the existing SMARTS Alert Analyzer frontend look & feel (timeline + Cytoscape execution flow + analysis cards), driven entirely by JSON dummy data.

## Run

This UI uses `fetch()` to load JSON, so it must be served over HTTP.

```bash
cd standalone_ui
python -m http.server 8000
```

Open `http://localhost:8000`.

## Configure

- Data source: `data/demo.json`
- To add a new analysis card: add a new property under `cards` in `data/demo.json`.
- To control DAG tool node names: set `toolName` on `tool_started/tool_completed` events in `timeline.events`.
- To control relationship network node names: set `graphs.relationshipNetwork.nodes[].id`.

## Spec (required fields)

- `page.appTitle` (string)
- `page.pageTitle` (string)
- `page.subtitle` (string)
- `executionFlow.nodes` (array)
- `executionFlow.edges` (array)
- `timeline.events` (array)
- `cards` (object map)

Timeline event required fields:

- `delayMs` (number, >= 0)
- `type` (string)
- `timestamp` (ISO string)
- `message` (string)
- `icon` (string; supported icons are defined in `static/js/timeline_renderer.js`)
- `color` (string; supported colors are defined in `static/js/timeline_renderer.js`)

## Execution Flow

The DAG is fully configured by JSON via `executionFlow`:

- `executionFlow.nodes[]`: `{ id, label, kind }` where `kind` is one of `start|step|service|evaluation|complete`
- `executionFlow.edges[]`: `{ id, source, target }` referencing node ids

To update DAG node state during playback, a timeline event can include:

- `dagUpdates`: array of `{ nodeId, state }` where `state` is one of `pending|active|completed|error`

## Typed cards

Cards are auto-generated from `cards`. If a card value is an object with `_type`, it renders a specialized UI.

Supported `_type` values:

- `confidence_scores`: renders bar charts from `{ items: [{ label, value, barColor }] }`
