# UI Architecture for SMARTS Alert Analyzer

This document describes the architecture for the web-based user interface that allows users to upload XML alerts and view analysis results.

## Overview

The UI provides a web interface for uploading SMARTS surveillance alerts (XML files) to the orchestrator agent and displaying the analysis results dynamically rendered from JSON.

## Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Frontend | HTMX + Vanilla JS + Tailwind CSS | Minimal complexity, leverages existing Tailwind styling |
| Graph Visualization | Cytoscape.js | Already used in wash trade reports |
| Backend | FastAPI | Lightweight, async-native, Python ecosystem |
| Template Engine | Jinja2 | Standard for FastAPI, simple syntax |
| Communication | A2A Protocol | Reuses existing orchestrator infrastructure |

## Configuration

| Setting | Value |
|---------|-------|
| UI Service Port | 8080 |
| Orchestrator Port | 10000 |
| Insider Trading Agent Port | 10001 |
| Wash Trade Agent Port | 10002 |
| Project Location | `src/frontend/` |
| Authentication | None (POC) |

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Browser (http://localhost:8080)                    │
│                                                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐ │
│  │   Upload Page   │ →  │  Loading State  │ →  │   Results Page      │ │
│  │                 │    │                 │    │                     │ │
│  │ • Drag & drop   │    │ • Spinner       │    │ • Determination     │ │
│  │ • XML preview   │    │ • Status text   │    │ • Confidence bars   │ │
│  │ • Analyze btn   │    │ • Poll /status  │    │ • Key findings      │ │
│  │                 │    │                 │    │ • Reasoning         │ │
│  │                 │    │                 │    │ • Cytoscape graph   │ │
│  │                 │    │                 │    │   (wash trade)      │ │
│  │                 │    │                 │    │ • Download links    │ │
│  └─────────────────┘    └─────────────────┘    └─────────────────────┘ │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
            POST /api/analyze    │    GET /api/status/{task_id}
            (multipart XML)      │    (polling)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   FastAPI Frontend Service (Port 8080)                  │
│                                                                         │
│  Endpoints:                                                             │
│  • GET  /                      → Serve upload page                      │
│  • POST /api/analyze           → Accept XML, start async task           │
│  • GET  /api/status/{task_id}  → Return task status + result JSON       │
│  • GET  /api/download/{id}/json → Download decision JSON                │
│  • GET  /api/download/{id}/html → Download generated HTML report        │
│                                                                         │
│  Internal Flow:                                                         │
│  1. Save uploaded XML to temp file                                      │
│  2. Create A2A client, send to orchestrator                             │
│  3. Track task in memory (dict with task_id → status/result)            │
│  4. On complete: save to resources/reports/, return JSON                │
│  5. Cleanup temp file                                                   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                    A2A Protocol │ (JSON-RPC over HTTP)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   Orchestrator Agent (Port 10000)                       │
│                   (Must be started separately)                          │
│                                                                         │
│                    Routes based on alert type:                          │
│                           │                                             │
│              ┌────────────┴────────────┐                                │
│              ▼                         ▼                                │
│   Insider Trading Agent         Wash Trade Agent                        │
│      (Port 10001)                 (Port 10002)                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
src/frontend/
├── __init__.py
├── app.py                 # FastAPI app, routes, A2A client calls
├── task_manager.py        # In-memory task tracking
├── static/
│   ├── css/
│   │   └── styles.css     # Custom styles (Tailwind via CDN)
│   └── js/
│       ├── upload.js      # File upload, preview, form submission
│       ├── polling.js     # Status polling logic
│       └── results.js     # Render results, Cytoscape graph init
└── templates/
    ├── base.html          # Base template (Tailwind CDN, common layout)
    ├── upload.html        # Upload page with drag-drop zone
    └── results.html       # Results page (HTMX partial or full page)
```

## API Endpoints

### GET /
Serves the main upload page.

### POST /api/analyze
Accepts XML file upload and initiates analysis.

**Request:**
- Content-Type: `multipart/form-data`
- Body: XML file

**Response:**
```json
{
  "task_id": "uuid-string"
}
```

### GET /api/status/{task_id}
Returns current status of analysis task.

**Response (processing):**
```json
{
  "status": "processing"
}
```

**Response (complete):**
```json
{
  "status": "complete",
  "alert_type": "insider_trading" | "wash_trade",
  "decision": { ... full decision JSON ... }
}
```

**Response (error):**
```json
{
  "status": "error",
  "message": "Error description"
}
```

### GET /api/download/{task_id}/json
Downloads the decision JSON file.

### GET /api/download/{task_id}/html
Downloads the generated HTML report.

## Implementation Algorithms

### FastAPI Application (app.py)

```
ALGORITHM: Initialize FastAPI App

1. Create FastAPI instance with static files mount
2. Configure Jinja2 templates
3. Initialize task_manager (in-memory dict)
4. Define routes:

   GET / :
     → Render upload.html template

   POST /api/analyze :
     → Validate file is XML (check content-type, extension)
     → Generate task_id (UUID)
     → Save file to temp directory as {task_id}.xml
     → Create background task:
         a. Initialize A2A client for orchestrator (localhost:10000)
         b. Send alert file path via A2A
         c. On success: store result in task_manager
         d. On error: store error in task_manager
         e. Cleanup temp file
     → Return {"task_id": task_id}

   GET /api/status/{task_id} :
     → Lookup task in task_manager
     → If not found → 404
     → If processing → {"status": "processing"}
     → If error → {"status": "error", "message": "..."}
     → If complete → {"status": "complete", "alert_type": "...", "decision": {...}}

   GET /api/download/{task_id}/json :
     → Serve resources/reports/decision_{alert_id}.json

   GET /api/download/{task_id}/html :
     → Serve resources/reports/decision_{alert_id}.html
```

### Task Manager (task_manager.py)

```
ALGORITHM: In-Memory Task Tracking

Data Structure:
  tasks = {
    task_id: {
      "status": "processing" | "complete" | "error",
      "alert_id": str | None,
      "alert_type": "insider_trading" | "wash_trade" | None,
      "decision": dict | None,
      "error": str | None,
      "created_at": datetime
    }
  }

Methods:
  create_task(task_id) → Initialize with status="processing"
  update_task(task_id, status, decision=None, error=None)
  get_task(task_id) → Return task dict or None
  cleanup_old_tasks() → Remove tasks older than 1 hour (optional)
```

### Frontend Upload Flow (upload.js)

```
ALGORITHM: File Upload Handler

1. Setup drag-drop zone event listeners
2. On file drop/select:
   a. Validate file extension (.xml)
   b. Read file content
   c. Display collapsible preview (syntax highlighted XML)
   d. Enable "Analyze" button

3. On "Analyze" click:
   a. Create FormData with file
   b. POST to /api/analyze
   c. On success:
      - Store task_id
      - Hide upload section
      - Show loading spinner
      - Start polling
   d. On error: Show toast notification
```

### Polling Flow (polling.js)

```
ALGORITHM: Status Polling

1. Poll /api/status/{task_id} every 2 seconds
2. On response:
   - If "processing":
       Update status message ("Analyzing alert...", "Running tools...")
       Continue polling
   - If "complete":
       Stop polling
       Call renderResults(decision, alert_type)
   - If "error":
       Stop polling
       Show error toast with message
       Show "Try Again" button
```

### Results Rendering (results.js)

```
ALGORITHM: Render Decision Results

INPUT: decision JSON, alert_type

1. Hide loading spinner
2. Show results container

3. Render common sections:
   a. Determination badge (color-coded: ESCALATE=red, CLOSE=green, REVIEW=yellow)
   b. Confidence scores (progress bars: genuine_alert_confidence, false_positive_confidence)
   c. Key findings (bullet list)
   d. Favorable indicators (list)
   e. Risk mitigating factors (list)
   f. Reasoning narrative (formatted paragraphs)
   g. Similar precedent reference
   h. Download buttons (JSON, HTML)

4. If alert_type == "insider_trading":
   a. Render trader baseline analysis section
   b. Render market context section with news timeline

5. If alert_type == "wash_trade":
   a. Initialize Cytoscape.js container
   b. Parse relationship_network (nodes, edges)
   c. Render interactive graph
   d. Render timing patterns table
   e. Render trade flows section
   f. Render counterparty patterns
   g. Render historical pattern summary
   h. Render regulatory framework references
```

### Cytoscape.js Graph Initialization

```
ALGORITHM: Render Relationship Network

INPUT: relationship_network from decision JSON

1. Create Cytoscape container div
2. Parse nodes:
   - Extract account IDs, labels, types
   - Map to Cytoscape node format
3. Parse edges:
   - Extract source, target, relationship type
   - Map to Cytoscape edge format
4. Initialize Cytoscape with:
   - Layout: 'cose' (force-directed) or 'dagre' (hierarchical)
   - Style: Node colors by type, edge labels
   - Interaction: Zoom, pan, node selection
5. Fit graph to container
```

## UI Features

### Upload Page
- Drag-and-drop zone for XML files
- Click-to-browse file selection
- Collapsible XML preview panel
- File validation (XML only)
- "Analyze" button (enabled after file selection)

### Loading State
- Spinner animation
- Status messages ("Analyzing alert...", "Running tools...")
- Polls backend every 2 seconds

### Results Page

#### Common Sections (All Alert Types)
- **Determination Badge**: Color-coded (ESCALATE=red, CLOSE=green, NEEDS_HUMAN_REVIEW=yellow)
- **Confidence Scores**: Progress bars for genuine_alert_confidence and false_positive_confidence
- **Key Findings**: Bullet list
- **Favorable Indicators**: Evidence suggesting genuine violation
- **Risk Mitigating Factors**: Evidence suggesting false positive
- **Reasoning Narrative**: Formatted paragraphs
- **Similar Precedent**: Reference to matching few-shot example
- **Download Buttons**: JSON and HTML report downloads

#### Insider Trading Specific
- Trader baseline analysis section
- Market context with news timeline

#### Wash Trade Specific
- Interactive Cytoscape.js relationship network graph
- Timing patterns table (sub-second analysis)
- Trade flows section (circular flow detection)
- Counterparty patterns
- Historical pattern summary
- Regulatory framework references (MAS SFA, SFC SFO, etc.)

## Error Handling

| Error Type | User Experience |
|------------|-----------------|
| Invalid file type | Toast: "Please upload an XML file" |
| Orchestrator unreachable | Toast: "Analysis service unavailable. Please ensure servers are running." |
| A2A timeout | Toast: "Analysis timed out. Please try again." |
| LLM failure | Toast: "Analysis failed: {error message}". Show retry button. |
| Unknown alert type | Toast: "Unsupported alert type detected." |

## Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "fastapi>=0.100.0",
    "uvicorn>=0.23.0",
    "python-multipart>=0.0.6",  # For file uploads
    "jinja2>=3.1.0",
    "aiofiles>=23.0.0",  # Async file operations
]
```

## Startup Sequence

```bash
# Terminal 1: Start Insider Trading Agent
source venv/bin/activate
python -m alerts.a2a.insider_trading_server --port 10001

# Terminal 2: Start Wash Trade Agent
source venv/bin/activate
python -m alerts.a2a.wash_trade_server --port 10002

# Terminal 3: Start Orchestrator
source venv/bin/activate
python -m alerts.a2a.orchestrator_server --port 10000 \
    --insider-trading-url http://localhost:10001 \
    --wash-trade-url http://localhost:10002

# Terminal 4: Start Frontend UI
source venv/bin/activate
python -m frontend.app --port 8080

# Browser: Open http://localhost:8080
```

## Design Decisions

### Why HTMX + Vanilla JS?
- Minimal complexity for POC
- Leverages existing Tailwind CSS styling
- No build step required
- Easy to understand and maintain

### Why Separate FastAPI Service?
- Clean separation from orchestrator (A2A is for agent-to-agent communication)
- Allows independent scaling and deployment
- Simpler error handling and user feedback

### Why Polling Instead of WebSockets?
- Simpler implementation for POC
- Analysis typically completes in 30-60 seconds
- No persistent connection management needed

### Why Render from JSON (Not Iframe)?
- Better integration with UI
- Consistent styling
- Interactive elements (Cytoscape graph)
- No cross-origin issues

### Why No Session History?
- Keeps POC lean
- Single analysis at a time
- Reports are saved to disk for later access
