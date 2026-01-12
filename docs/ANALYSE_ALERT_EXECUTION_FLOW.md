# Analyse Alert Button - Complete Execution Flow

This document traces the complete execution flow when a user clicks the "Analyse Alert" button in the SMARTS Alert Analyzer UI.

---

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [API Call Sequence](#api-call-sequence)
3. [API Contracts](#api-contracts)
4. [Detailed Execution Flow](#detailed-execution-flow)
5. [SSE Event Flow](#sse-event-flow)
6. [Class & Method Reference](#class--method-reference)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                   BROWSER                                        │
│                              (upload.html + JS)                                  │
└───────────────────────────────────┬─────────────────────────────────────────────┘
                                    │ 1. POST /api/analyze (XML file)
                                    │ 2. GET /api/stream/{task_id} (SSE)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND SERVER (:8080)                                 │
│                           src/frontend/app.py                                    │
└───────────────────────────────────┬─────────────────────────────────────────────┘
                                    │ 3. POST /api/analyze/stream (JSON)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR A2A SERVER (:10000)                            │
│                   src/alerts/a2a/orchestrator_server.py                         │
└───────────────────────────────────┬─────────────────────────────────────────────┘
                                    │ 4. POST /api/analyze/stream (JSON)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│          AGENT A2A SERVER (:10001 IT | :10002 WT)                               │
│    src/alerts/a2a/insider_trading_server.py | wash_trade_server.py              │
└───────────────────────────────────┬─────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         ANALYZER AGENT (Core Logic)                              │
│           src/alerts/agents/insider_trading/agent.py (or wash_trade)            │
│                                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │               PARALLEL TOOL EXECUTION (asyncio.gather)                   │   │
│   │  ┌─────────┐  ┌─────────┐  ┌─────────────┐  ┌──────────────────┐        │   │
│   │  │ Market  │  │ Market  │  │   Trader    │  │  Trader History  │        │   │
│   │  │  News   │  │  Data   │  │   Profile   │  │   (or WT tools)  │        │   │
│   │  └─────────┘  └─────────┘  └─────────────┘  └──────────────────┘        │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                             │
│                                    ▼                                             │
│                         LLM SYNTHESIS → Decision                                │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## API Call Sequence

The APIs are called in this **strict order**:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           API CALL ORDER                                      │
├──────┬───────────────────────────────────────────────────────────────────────┤
│  #   │  API Call                                                             │
├──────┼───────────────────────────────────────────────────────────────────────┤
│  1   │  Browser → Frontend: POST /api/analyze                                │
│      │  (Upload XML file, get task_id)                                       │
├──────┼───────────────────────────────────────────────────────────────────────┤
│  2   │  Browser → Frontend: GET /api/stream/{task_id}                        │
│      │  (Open SSE connection for real-time updates)                          │
├──────┼───────────────────────────────────────────────────────────────────────┤
│  3   │  Frontend → Orchestrator: POST /api/analyze/stream                    │
│      │  (Send AnalysisRequest JSON, receive SSE stream)                      │
├──────┼───────────────────────────────────────────────────────────────────────┤
│  4   │  Orchestrator → Agent: POST /api/analyze/stream                       │
│      │  (Route to IT/WT agent, receive SSE stream)                           │
└──────┴───────────────────────────────────────────────────────────────────────┘

SSE events flow back: Agent → Orchestrator → Frontend → Browser
```

---

## API Contracts

### API 1: Frontend Upload Endpoint

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  POST /api/analyze                                                           │
│  Server: Frontend (:8080)                                                    │
│  File: src/frontend/app.py:101-184                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│  REQUEST                                                                     │
│  ─────────                                                                   │
│  Content-Type: multipart/form-data                                           │
│                                                                              │
│  Form Fields:                                                                │
│  ┌────────────┬────────────┬───────────────────────────────────────────┐    │
│  │ Field      │ Type       │ Description                               │    │
│  ├────────────┼────────────┼───────────────────────────────────────────┤    │
│  │ file       │ File       │ XML alert file (required, .xml extension) │    │
│  └────────────┴────────────┴───────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────────────┤
│  RESPONSE (200 OK)                                                           │
│  ─────────────────                                                           │
│  Content-Type: application/json                                              │
│                                                                              │
│  {                                                                           │
│    "task_id": "a1b2c3d4e5f6...",     // 32-char hex UUID                    │
│    "agent_type": "insider_trading"    // or "wash_trade"                    │
│  }                                                                           │
├──────────────────────────────────────────────────────────────────────────────┤
│  ERROR RESPONSES                                                             │
│  ───────────────                                                             │
│  400 Bad Request:  {"detail": "Please upload an XML file"}                  │
│  500 Server Error: {"detail": "Failed to read uploaded file"}               │
│                    {"detail": "Failed to prepare analysis request: ..."}    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### API 2: Frontend SSE Stream Endpoint

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  GET /api/stream/{task_id}                                                   │
│  Server: Frontend (:8080)                                                    │
│  File: src/frontend/app.py:226-400                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│  REQUEST                                                                     │
│  ─────────                                                                   │
│  Path Parameters:                                                            │
│  ┌────────────┬────────────┬───────────────────────────────────────────┐    │
│  │ Parameter  │ Type       │ Description                               │    │
│  ├────────────┼────────────┼───────────────────────────────────────────┤    │
│  │ task_id    │ string     │ Task ID from POST /api/analyze response   │    │
│  └────────────┴────────────┴───────────────────────────────────────────┘    │
│                                                                              │
│  Headers:                                                                    │
│  Accept: text/event-stream                                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│  RESPONSE (200 OK)                                                           │
│  ─────────────────                                                           │
│  Content-Type: text/event-stream                                             │
│                                                                              │
│  SSE Event Format:                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ event: {event_type}                                                 │    │
│  │ id: {event_id}                                                      │    │
│  │ retry: 5000                                                         │    │
│  │ data: {JSON payload - see SSE Event Structure below}                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Event Types (in order):                                                     │
│  1. analysis_started    - Analysis begins                                   │
│  2. routing             - Routing to agent                                  │
│  3. context_received    - Alert context loaded                              │
│  4. tool_started        - Tool execution begins (×4 for IT, ×5 for WT)     │
│  5. tool_completed      - Tool execution done (×4 for IT, ×5 for WT)       │
│  6. evaluation_started  - LLM synthesis begins                              │
│  7. analysis_complete   - Final decision (final=true)                       │
│  8. keep_alive          - Heartbeat every 25 seconds                        │
│  9. error               - On failure                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│  ERROR EVENTS                                                                │
│  ────────────                                                                │
│  event: error                                                                │
│  data: {"event_type": "error", "message": "..."}                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### API 3: Orchestrator Streaming Endpoint

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  POST /api/analyze/stream                                                    │
│  Server: Orchestrator (:10000)                                               │
│  File: src/alerts/a2a/orchestrator_server.py:281-436                        │
├──────────────────────────────────────────────────────────────────────────────┤
│  REQUEST                                                                     │
│  ─────────                                                                   │
│  Content-Type: application/json                                              │
│  Accept: text/event-stream                                                   │
│                                                                              │
│  Body: AnalysisRequest (see schema below)                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│  RESPONSE (200 OK)                                                           │
│  ─────────────────                                                           │
│  Content-Type: text/event-stream                                             │
│                                                                              │
│  Emits orchestrator events:                                                  │
│  1. analysis_started  - {"message": "...", "agent_type": "..."}             │
│  2. routing           - {"message": "Routing to {agent} agent"}             │
│                                                                              │
│  Then proxies all events from Agent (API 4)                                 │
│  with metadata.orchestrated = true                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│  ROUTING LOGIC                                                               │
│  ─────────────                                                               │
│  agent_type == "insider_trading" → http://localhost:10001/api/analyze/stream│
│  agent_type == "wash_trade"      → http://localhost:10002/api/analyze/stream│
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### API 4: Agent Streaming Endpoint

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  POST /api/analyze/stream                                                    │
│  Server: IT Agent (:10001) or WT Agent (:10002)                             │
│  File: src/alerts/a2a/insider_trading_server.py:175-287                     │
│        src/alerts/a2a/wash_trade_server.py (similar)                        │
├──────────────────────────────────────────────────────────────────────────────┤
│  REQUEST                                                                     │
│  ─────────                                                                   │
│  Content-Type: application/json                                              │
│  Accept: text/event-stream                                                   │
│                                                                              │
│  Body: AnalysisRequest (same as API 3)                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│  RESPONSE (200 OK)                                                           │
│  ─────────────────                                                           │
│  Content-Type: text/event-stream                                             │
│                                                                              │
│  Emits agent analysis events via astream_analyze_request():                 │
│  1. context_received     - Alert context loaded                             │
│  2. tool_started (×N)    - One per tool (parallel)                         │
│  3. tool_completed (×N)  - One per tool (parallel)                         │
│  4. evaluation_started   - LLM synthesis begins                             │
│  5. analysis_complete    - Final decision (final=true)                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### AnalysisRequest Schema (Request Body for APIs 3 & 4)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  AnalysisRequest                                                             │
│  Model: src/alerts/models/request.py:129-272                                │
├──────────────────────────────────────────────────────────────────────────────┤
│  {                                                                           │
│    "alert_context": {                    // Discriminated Union             │
│      "context_type": "insider_trading",  // or "wash_trade" (discriminator) │
│      "alert_id": "ITA-2024-001847",                                         │
│      "alert_type": "Pre-Announcement Trading",                              │
│      "rule_violated": "MAR-03-001",                                         │
│      "generated_timestamp": "2024-03-16T10:30:00Z",                         │
│      "trader": {                                                             │
│        "trader_id": "T001",                                                  │
│        "name": "John Smith",                                                 │
│        "department": "Operations"                                            │
│      },                                                                      │
│      "trade": {                                                              │
│        "symbol": "ACME",                                                     │
│        "trade_date": "2024-03-15",                                          │
│        "side": "BUY",                                                        │
│        "quantity": 50000,                                                    │
│        "price": "101.50",                                                    │
│        "total_value": "5075000"                                             │
│      }                                                                       │
│    },                                                                        │
│                                                                              │
│    "agent_type": "insider_trading",      // or "wash_trade"                 │
│                                                                              │
│    "tool_data": {                        // Pre-aggregated by BigData Layer │
│      "market_news": {                                                        │
│        "format": "txt",                                                      │
│        "data": "2024-01-15: Company announces Q4 earnings..."               │
│      },                                                                      │
│      "market_data": {                                                        │
│        "format": "csv",                                                      │
│        "data": "timestamp,symbol,price,volume\n..."                         │
│      },                                                                      │
│      "trader_profile": {                                                     │
│        "format": "csv",                                                      │
│        "data": "trader_id,name,role,mnpi_access\n..."                       │
│      },                                                                      │
│      "trader_history": {                                                     │
│        "format": "csv",                                                      │
│        "data": "date,symbol,action,quantity\n..."                           │
│      }                                                                       │
│    }                                                                         │
│  }                                                                           │
├──────────────────────────────────────────────────────────────────────────────┤
│  Required Tools by Agent Type:                                               │
│  ─────────────────────────────                                               │
│  insider_trading: market_news, market_data, trader_profile, trader_history  │
│  wash_trade: market_data, account_relationships, related_accounts_history,  │
│              trade_timing, counterparty_analysis                             │
├──────────────────────────────────────────────────────────────────────────────┤
│  ToolInput Schema:                                                           │
│  ─────────────────                                                           │
│  {                                                                           │
│    "format": "csv" | "txt" | "xml",                                         │
│    "data": "<raw data content as string>"                                   │
│  }                                                                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### SSE Event Structure (A2A Format)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  StreamEvent → A2A TaskStatusUpdateEvent                                     │
│  Model: src/alerts/a2a/event_mapper.py:16-106                               │
├──────────────────────────────────────────────────────────────────────────────┤
│  {                                                                           │
│    "jsonrpc": "2.0",                                                         │
│    "result": {                                                               │
│      "task": {                                                               │
│        "id": "task-uuid-here",                                              │
│        "state": "working" | "completed" | "failed"                          │
│      },                                                                      │
│      "taskStatusUpdateEvent": {                                             │
│        "task": {                                                             │
│          "id": "task-uuid-here",                                            │
│          "state": "working" | "completed",                                  │
│          "messages": [                                                       │
│            {                                                                 │
│              "role": "agent",                                                │
│              "parts": [{"type": "textPart", "text": "..."}]                 │
│            }                                                                 │
│          ]                                                                   │
│        },                                                                    │
│        "final": false | true    // true only on analysis_complete           │
│      },                                                                      │
│      "metadata": {                                                           │
│        "event_id": "uuid",                                                   │
│        "event_type": "tool_started",                                        │
│        "agent": "insider_trading",                                          │
│        "timestamp": "2024-03-16T10:30:00Z",                                 │
│        "payload": { ... event-specific data ... },                          │
│        "orchestrated": true     // added by orchestrator                    │
│      }                                                                       │
│    }                                                                         │
│  }                                                                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Execution Flow

### Step 1: Button Click (Browser)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  File: src/frontend/static/js/upload.js                                      │
│  Function: submitAnalysis() [line ~153]                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User clicks "Analyse Alert" button                                          │
│                     │                                                        │
│                     ▼                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  submitAnalysis()                                                   │    │
│  │  ├─ Create FormData with file                                      │    │
│  │  ├─ POST /api/analyze                                              │    │
│  │  ├─ Receive {task_id, agent_type}                                  │    │
│  │  └─ Call startPolling(task_id)                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                     │                                                        │
│                     ▼                                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  startPolling() → overridden by streaming.js                       │    │
│  │  └─ Calls startStreaming(taskId)                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Step 2: SSE Connection (Browser → Frontend)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  File: src/frontend/static/js/streaming.js                                   │
│  Function: startStreaming() [line ~98]                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  startStreaming(taskId)                                                      │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. Create ProgressTimeline instance                                │    │
│  │  2. Create EventSource to GET /api/stream/{taskId}                 │    │
│  │  3. Register event handlers:                                        │    │
│  │     ├─ onmessage → handleProgressEvent()                           │    │
│  │     ├─ onerror   → handleStreamingError()                          │    │
│  │     └─ on 'analysis_complete' → handleStreamingComplete()          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Key Handlers:                                                               │
│  ─────────────                                                               │
│  handleProgressEvent(event)      [line ~333] - Updates UI with each event   │
│  handleStreamingComplete(result) [line ~222] - Processes final decision     │
│  handleStreamingError(error)     [line ~304] - Fail-fast error handling     │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Step 3: Frontend Processes Upload

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  File: src/frontend/app.py                                                   │
│  Endpoint: POST /api/analyze [lines 101-184]                                │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  @app.post("/api/analyze")                                                   │
│  async def analyze(file: UploadFile):                                        │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. Validate file is XML (.xml extension)           [line 125]     │    │
│  │  2. Generate task_id = uuid4().hex                  [line 133]     │    │
│  │  3. Read file content as UTF-8                      [line 138-139] │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  4. Create AnalysisRequest via BigDataSimulator     [line 150-151] │    │
│  │     └─ simulator.create_request_from_content(xml_content)          │    │
│  │        ├─ Parses XML → AlertContext                                │    │
│  │        ├─ Determines agent_type                                     │    │
│  │        └─ Loads all tool_data from test_data/                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  5. Save AnalysisRequest JSON to temp file          [line 164-167] │    │
│  │     └─ /tmp/alerts_frontend/{task_id}_request.json                 │    │
│  │  6. Create task in task_manager                     [line 178]     │    │
│  │  7. Return {task_id, agent_type}                    [line 181-183] │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Key Class: BigDataSimulator                                                 │
│  File: src/alerts/mock/bigdata_simulator.py                                 │
│  Method: create_request_from_content(xml_content: str) → AnalysisRequest    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Step 4: Frontend Streams to Orchestrator

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  File: src/frontend/app.py                                                   │
│  Endpoint: GET /api/stream/{task_id} [lines 226-400]                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  @app.get("/api/stream/{task_id}")                                           │
│  async def stream_events(task_id, request):                                  │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. Validate task exists                            [line 245-250] │    │
│  │  2. Load AnalysisRequest from temp file             [line 280-281] │    │
│  │     └─ /tmp/alerts_frontend/{task_id}_request.json                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  3. Connect to Orchestrator streaming endpoint      [line 289-298] │    │
│  │     POST {ORCHESTRATOR_URL}/api/analyze/stream                     │    │
│  │     ├─ URL: http://localhost:10000/api/analyze/stream              │    │
│  │     ├─ Body: analysis_request (JSON)                               │    │
│  │     └─ Headers: Accept: text/event-stream                          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  4. event_generator() async loop                    [line 268-395] │    │
│  │     ├─ Parse SSE lines from orchestrator response                  │    │
│  │     ├─ Extract event_type from metadata             [line 339]     │    │
│  │     ├─ Forward events to browser                    [line 343-348] │    │
│  │     ├─ Send keep-alive every 25 seconds             [line 319-327] │    │
│  │     └─ On final event: _handle_streaming_final_event [line 356]    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Returns: EventSourceResponse(event_generator())                             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Step 5: Orchestrator Routes to Agent

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  File: src/alerts/a2a/orchestrator_server.py                                │
│  Endpoint: POST /api/analyze/stream [lines 281-436]                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  async def api_analyze_stream_endpoint(request):                             │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. Parse request body as JSON                      [line 317]     │    │
│  │  2. Validate as AnalysisRequest                     [line 327]     │    │
│  │  3. Generate internal task_id                       [line 335]     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  4. Emit orchestrator events:                                       │    │
│  │     ├─ yield "analysis_started"                     [line 343-346] │    │
│  │     └─ yield "routing"                              [line 348-351] │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  5. Determine target agent URL:                     [line 354-363] │    │
│  │     ├─ insider_trading → http://localhost:10001/api/analyze/stream │    │
│  │     └─ wash_trade      → http://localhost:10002/api/analyze/stream │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  6. Proxy to agent via HTTP POST                    [line 369-375] │    │
│  │     ├─ Send AnalysisRequest JSON                                   │    │
│  │     ├─ Receive SSE stream from agent                               │    │
│  │     ├─ Add metadata.orchestrated = true             [line 399]     │    │
│  │     └─ Forward all events to frontend               [line 406-411] │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Returns: EventSourceResponse(event_generator())                             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Step 6: Agent Processes Request

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  File: src/alerts/a2a/insider_trading_server.py                             │
│  Endpoint: POST /api/analyze/stream [lines 175-287]                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  async def api_analyze_stream_endpoint(request):                             │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. Parse and validate AnalysisRequest              [line 219-226] │    │
│  │  2. Generate internal task_id                       [line 228]     │    │
│  │  3. Get agent instance: _executor._get_agent()      [line 235]     │    │
│  │     └─ Returns InsiderTradingAnalyzerAgent (cached)                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  4. Stream events from agent:                       [line 237]     │    │
│  │     async for event in agent.astream_analyze_request(request, id): │    │
│  │       ├─ Convert to A2A format                      [line 244-246] │    │
│  │       └─ Yield as SSE                               [line 248-253] │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Returns: EventSourceResponse(event_generator())                             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Step 7: Agent Core Analysis

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  File: src/alerts/agents/insider_trading/agent.py                           │
│  Class: InsiderTradingAnalyzerAgent [line 87]                               │
│  Method: astream_analyze_request() [lines 431-578]                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  async def astream_analyze_request(request, task_id):                        │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. Create EventMapper(task_id, "insider_trading")  [line 460]     │    │
│  │  2. Validate alert_context type                     [line 463-467] │    │
│  │  3. yield "context_received" event                  [line 490-494] │    │
│  │  4. Build context_params (date ranges, etc.)        [line 498]     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  5. yield ALL "tool_started" events (non-blocking)  [line 506-507] │    │
│  │     ├─ query_market_news: started                                  │    │
│  │     ├─ query_market_data: started                                  │    │
│  │     ├─ query_trader_profile: started                               │    │
│  │     └─ query_trader_history: started                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  6. PARALLEL TOOL EXECUTION                         [line 517]     │    │
│  │     results = await asyncio.gather(                                │    │
│  │       _aexecute_single_tool("query_market_news", ...),            │    │
│  │       _aexecute_single_tool("query_market_data", ...),            │    │
│  │       _aexecute_single_tool("query_trader_profile", ...),         │    │
│  │       _aexecute_single_tool("query_trader_history", ...),         │    │
│  │       return_exceptions=True                                       │    │
│  │     )                                                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  7. Fail-fast if any tool raised exception          [line 521-529] │    │
│  │  8. Collect insights: {tool_name: insight}          [line 533-542] │    │
│  │  9. yield "tool_completed" events                   (after gather) │    │
│  │ 10. yield "evaluation_started" event                [line 545]     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 11. LLM SYNTHESIS: _synthesize(insights)            [line 548]     │    │
│  │     ├─ Load few-shot examples                                      │    │
│  │     ├─ Build system prompt                                         │    │
│  │     ├─ Call llm.with_structured_output(Decision)                   │    │
│  │     └─ Return InsiderTradingDecision                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 12. Write outputs:                                  [line 553-555] │    │
│  │     ├─ _write_decision() → decision_{id}.json                      │    │
│  │     ├─ _write_audit_log() → audit_log.jsonl                        │    │
│  │     └─ _write_html_report() → decision_{id}.html                   │    │
│  │ 13. yield "analysis_complete" (final=true)          [line 559-564] │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Step 8: Tool Execution Detail

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  File: src/alerts/agents/insider_trading/agent.py                           │
│  Method: _aexecute_single_tool() [lines 243-295]                            │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  async def _aexecute_single_tool(tool_name, request, context_params):        │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. Get tool data key mapping                       [line 269]     │    │
│  │     "query_market_news" → "market_news"                            │    │
│  │  2. Get ToolInput from request.tool_data            [line 274]     │    │
│  │  3. Fail-fast if missing                            [line 276]     │    │
│  │  4. Get tool instance                               [line 279]     │    │
│  │  5. Get context params for tool                     [line 284]     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  6. Execute tool (async, non-blocking LLM)          [line 288-292] │    │
│  │     insight = await tool.aexecute(                                 │    │
│  │       data=tool_input.data,                                        │    │
│  │       format=tool_input.format,                                    │    │
│  │       **context                                                    │    │
│  │     )                                                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  7. Return (tool_name, insight) tuple                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Tool Instances (created in _create_tool_instances()):                       │
│  ─────────────────────────────────────────────────────                       │
│  ├─ TraderProfileTool(llm, data_dir)  [tools/common/trader_profile.py]      │
│  ├─ MarketDataTool(llm, data_dir)     [tools/common/market_data.py]         │
│  ├─ TraderHistoryTool(llm, data_dir)  [agents/insider_trading/tools/]       │
│  └─ MarketNewsTool(llm, data_dir)     [agents/insider_trading/tools/]       │
│                                                                              │
│  BaseTool.aexecute() Flow:                                                   │
│  ─────────────────────────                                                   │
│  1. Validate format matches expected_format                                  │
│  2. Call _build_interpretation_prompt(data, **kwargs)                       │
│  3. Invoke LLM with prompt → get insights                                   │
│  4. Return insights string                                                   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## SSE Event Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         SSE EVENT TIMELINE                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Time    Source        Event Type           Payload                         │
│  ────    ──────        ──────────           ───────                         │
│                                                                              │
│  T+0     Orchestrator  analysis_started     {agent_type, message}           │
│  T+1     Orchestrator  routing              {agent_type, message}           │
│  T+2     Agent         context_received     {alert_id, context_info}        │
│  T+3     Agent         tool_started         {tool_name: "market_news"}      │
│  T+3     Agent         tool_started         {tool_name: "market_data"}      │
│  T+3     Agent         tool_started         {tool_name: "trader_profile"}   │
│  T+3     Agent         tool_started         {tool_name: "trader_history"}   │
│  ...                   (parallel execution)                                  │
│  T+N     Agent         tool_completed       {tool_name, summary}            │
│  T+N     Agent         tool_completed       {tool_name, summary}            │
│  T+N     Agent         tool_completed       {tool_name, summary}            │
│  T+N     Agent         tool_completed       {tool_name, summary}            │
│  T+N+1   Agent         evaluation_started   {message}                       │
│  T+N+X   Agent         analysis_complete    {decision: {...}, final: true}  │
│                                                                              │
│  Note: tool_started events emitted together, tools execute in parallel,     │
│        tool_completed events arrive as each tool finishes (order varies)    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Class & Method Reference

| Layer | File | Class/Function | Lines | Purpose |
|-------|------|----------------|-------|---------|
| **Frontend JS** | static/js/upload.js | `submitAnalysis()` | ~153-189 | Handle button click, POST file |
| **Frontend JS** | static/js/streaming.js | `startStreaming()` | ~98-168 | Open SSE connection |
| **Frontend JS** | static/js/streaming.js | `handleProgressEvent()` | ~333 | Process each SSE event |
| **Frontend JS** | static/js/streaming.js | `handleStreamingComplete()` | ~222 | Handle final decision |
| **Frontend API** | frontend/app.py | `analyze()` | 101-184 | `POST /api/analyze` |
| **Frontend API** | frontend/app.py | `stream_events()` | 226-400 | `GET /api/stream/{id}` |
| **Frontend API** | frontend/app.py | `_handle_streaming_final_event()` | ~619-685 | Process final event |
| **BigData** | mock/bigdata_simulator.py | `BigDataSimulator` | - | Create AnalysisRequest |
| **BigData** | mock/bigdata_simulator.py | `create_request_from_content()` | - | Parse XML → structured request |
| **Orchestrator** | a2a/orchestrator_server.py | `api_analyze_stream_endpoint()` | 281-436 | `POST /api/analyze/stream` |
| **Orchestrator** | a2a/orchestrator.py | `OrchestratorAgent` | 52 | Main orchestrator class |
| **Orchestrator** | a2a/orchestrator.py | `analyze_request()` | 522-565 | Route to agent |
| **IT Server** | a2a/insider_trading_server.py | `api_analyze_stream_endpoint()` | 175-287 | `POST /api/analyze/stream` |
| **IT Agent** | agents/insider_trading/agent.py | `InsiderTradingAnalyzerAgent` | 87 | Main agent class |
| **IT Agent** | agents/insider_trading/agent.py | `astream_analyze_request()` | 431-578 | Core analysis (streaming) |
| **IT Agent** | agents/insider_trading/agent.py | `_aexecute_single_tool()` | 243-295 | Execute one tool |
| **IT Agent** | agents/insider_trading/agent.py | `_synthesize()` | 580-634 | LLM synthesis → Decision |
| **IT Agent** | agents/insider_trading/agent.py | `_create_tool_instances()` | 143-159 | Initialize tools |
| **Events** | a2a/event_mapper.py | `StreamEvent` | 16-139 | Event data structure |
| **Events** | a2a/event_mapper.py | `to_a2a_format()` | 64-106 | Convert to A2A JSON-RPC |
| **Events** | a2a/event_mapper.py | `EventMapper` | 142+ | Create typed events |
| **Models** | models/request.py | `AnalysisRequest` | 129-272 | Main request model |
| **Models** | models/request.py | `ToolInput` | 85-126 | Tool data container |
| **Tools** | tools/common/base.py | `BaseTool` | - | Base class for all tools |
| **Tools** | tools/common/base.py | `aexecute()` | - | Async tool execution |

---

## Quick Debugging Guide

To trace issues, follow this path:

```
1. Browser Console → Check JS errors, network tab for /api/analyze and /api/stream
2. Frontend logs  → logs/frontend.log (or console output)
3. Orchestrator   → logs/orchestrator.log
4. Agent          → logs/insider_trading.log or logs/wash_trade.log
```

Key breakpoints:
- `src/frontend/app.py:151` - AnalysisRequest creation
- `src/alerts/a2a/orchestrator_server.py:365` - Agent URL routing
- `src/alerts/a2a/insider_trading_server.py:237` - Agent streaming start
- `src/alerts/agents/insider_trading/agent.py:517` - Parallel tool execution
- `src/alerts/agents/insider_trading/agent.py:548` - LLM synthesis
