# Agent Event Streaming Architecture

## Executive Summary

This document defines the architecture for real-time event streaming from LangGraph agents to the frontend UI. The goal is to eliminate the 5-10 minute blocked loading screen by streaming progress events as the analysis proceeds.

**Key Decision**: Use Server-Sent Events (SSE) across all layers with A2A protocol compliance.

---

## Problem Statement

**Current State**:
- Alert analysis takes 5-10 minutes
- Frontend polls `/api/status/{task_id}` every 2 seconds
- User sees only a loading spinner with no progress indication
- No visibility into which tools are running or what the agent is "thinking"

**Desired State**:
- Real-time event streaming from agents to UI
- Users see tool execution progress as it happens
- Events include: tool started, tool completed, agent thinking
- Historical events stored for post-analysis review

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           BROWSER                                        │
│  EventSource API (native, no npm packages)                              │
│  GET /api/stream/{task_id}                                              │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ SSE (text/event-stream)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND (Port 8080)                        │
│  Library: sse-starlette >= 3.0.3                                        │
│  Proxies A2A events to frontend                                         │
│  Stores events in task_manager                                          │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ A2A Protocol (POST /message/stream → SSE)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR (Port 10000)                          │
│  Pass-through pattern: forwards specialized agent events                │
│  Emits: routing_started, routing_completed                              │
│  Agent Card: capabilities.streaming = true                              │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ A2A Protocol (POST /message/stream → SSE)
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│             SPECIALIZED AGENT (IT:10001 / WT:10002)                     │
│  LangGraph astream_events(stream_mode=["custom", "updates"])            │
│  Tools emit events via config["stream_writer"]                          │
│  Agent Card: capabilities.streaming = true                              │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ stream_writer callback
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           TOOLS                                          │
│  Emit: tool_started, tool_completed                                     │
│  Summary included in tool_completed event                               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| Browser | EventSource API | Native | SSE client, auto-reconnect |
| Backend | sse-starlette | >= 3.0.3 | FastAPI SSE responses |
| Backend | httpx | >= 0.24.0 | Async HTTP client for A2A |
| Agents | LangGraph | >= 0.1.0 | astream_events() API |
| Protocol | A2A | v0.3.0 | Agent-to-agent streaming |

---

## Event Schema

### Standard Event Structure

```json
{
  "event_id": "uuid-v4",
  "task_id": "task-123",
  "timestamp": "2025-12-03T10:30:00.123Z",
  "agent": "insider_trading | wash_trade | orchestrator",
  "event_type": "tool_started | tool_completed | agent_thinking | routing_started | routing_completed | error | analysis_complete | keep_alive",
  "payload": {
    "tool_name": "trader_history",
    "message": "Analyzing 247 historical trades...",
    "summary": "Found 10x volume anomaly in healthcare sector"
  }
}
```

### Event Types

| Event Type | When Emitted | Payload Fields |
|------------|--------------|----------------|
| `routing_started` | Orchestrator determines alert type | `alert_type`, `target_agent` |
| `routing_completed` | Orchestrator finished routing | `target_agent` |
| `tool_started` | Before tool execution begins | `tool_name`, `message` |
| `tool_completed` | After tool returns with LLM interpretation | `tool_name`, `summary` |
| `agent_thinking` | After agent processes tool results | `message` |
| `error` | On any failure (fail-fast) | `error_message`, `tool_name` (optional) |
| `analysis_complete` | Final determination ready | `determination`, `confidence` |
| `keep_alive` | Every 25 seconds | `timestamp` |

### A2A Protocol Event Wrapper

Events are wrapped in A2A `TaskStatusUpdateEvent` format:

```json
{
  "jsonrpc": "2.0",
  "result": {
    "task": {
      "id": "task-123",
      "state": "working"
    },
    "taskStatusUpdateEvent": {
      "task": {
        "id": "task-123",
        "state": "working",
        "messages": [
          {
            "role": "agent",
            "parts": [
              {
                "type": "textPart",
                "text": "{\"event_type\": \"tool_started\", ...}"
              }
            ]
          }
        ]
      },
      "final": false
    }
  }
}
```

**Terminal States**:
- `final: true` sent with `analysis_complete` or `error` events
- Task states: `submitted` → `working` → `completed` | `failed`

---

## Detailed Design by Layer

### Layer 1: Tool Layer

**File**: `src/alerts/tools/base.py`

**Changes**:
1. Modify `BaseTool.__call__()` to accept `config` parameter
2. Extract `stream_writer` callback from config
3. Emit `tool_started` before `_load_data()`
4. Emit `tool_completed` after LLM interpretation with summary

**Algorithm**:
```
FUNCTION __call__(self, config, **kwargs):
    stream_writer = config.get("stream_writer")

    IF stream_writer:
        stream_writer({
            "event_type": "tool_started",
            "tool_name": self.name,
            "message": f"Starting {self.name}..."
        })

    TRY:
        raw_data = self._load_data(**kwargs)
        interpretation = self._interpret_with_llm(raw_data, **kwargs)

        IF stream_writer:
            stream_writer({
                "event_type": "tool_completed",
                "tool_name": self.name,
                "summary": self._extract_summary(interpretation)
            })

        RETURN interpretation

    CATCH Exception as e:
        IF stream_writer:
            stream_writer({
                "event_type": "error",
                "tool_name": self.name,
                "error_message": str(e)
            })
        RAISE  # Fail-fast
```

**Summary Extraction**:
- Extract first 200 characters of interpretation
- Or use a dedicated summary field from LLM response

---

### Layer 2: Agent Layer

**Files**:
- `src/alerts/agents/insider_trading/agent.py`
- `src/alerts/agents/wash_trade/agent.py`

**Changes**:
1. Add `async arun_with_events()` method using `astream_events()`
2. Pass `stream_writer` to tools via config
3. Emit `agent_thinking` events after processing tool results

**Algorithm**:
```
ASYNC FUNCTION arun_with_events(self, alert_data):
    config = {
        "stream_writer": self._create_event_emitter(),
        "recursion_limit": 50
    }

    ASYNC FOR mode, chunk IN self.graph.astream_events(
        input={"alert_data": alert_data},
        config=config,
        stream_mode=["custom", "updates"]
    ):
        IF mode == "custom":
            # Tool events (tool_started, tool_completed)
            YIELD self._wrap_as_a2a_event(chunk)

        ELIF mode == "updates":
            # Check if agent node completed
            IF "agent" IN chunk:
                YIELD self._wrap_as_a2a_event({
                    "event_type": "agent_thinking",
                    "message": "Processing tool results..."
                })

    # Final result
    YIELD self._wrap_as_a2a_event({
        "event_type": "analysis_complete",
        "determination": result.determination,
        "confidence": result.genuine_alert_confidence
    }, final=True)
```

---

### Layer 3: A2A Executor

**Files**:
- `src/alerts/a2a/insider_trading_executor.py`
- `src/alerts/a2a/wash_trade_executor.py`
- `src/alerts/a2a/orchestrator_executor.py`

**Changes**:
1. Add `async execute_stream()` method
2. Map LangGraph events to A2A `TaskStatusUpdateEvent`
3. Handle errors with fail-fast pattern

**Algorithm**:
```
ASYNC FUNCTION execute_stream(self, task_id, alert_content):
    TRY:
        agent = self._create_agent()

        ASYNC FOR event IN agent.arun_with_events(alert_content):
            YIELD {
                "jsonrpc": "2.0",
                "result": {
                    "task": {"id": task_id, "state": self._map_state(event)},
                    "taskStatusUpdateEvent": {
                        "task": {
                            "id": task_id,
                            "state": self._map_state(event),
                            "messages": [self._format_message(event)]
                        },
                        "final": event.get("final", False)
                    }
                }
            }

    CATCH Exception as e:
        YIELD {
            "jsonrpc": "2.0",
            "result": {
                "task": {"id": task_id, "state": "failed"},
                "taskStatusUpdateEvent": {
                    "task": {"id": task_id, "state": "failed"},
                    "final": True
                }
            }
        }
        # Fail-fast: do not continue
```

---

### Layer 4: A2A Server

**Files**:
- `src/alerts/a2a/insider_trading_server.py`
- `src/alerts/a2a/wash_trade_server.py`
- `src/alerts/a2a/orchestrator_server.py`

**Changes**:
1. Add `POST /message/stream` endpoint
2. Return `EventSourceResponse`
3. Implement keep-alive (every 25 seconds)
4. Check client disconnect

**Algorithm**:
```
@app.post("/message/stream")
ASYNC FUNCTION message_stream(request: Request):
    body = AWAIT request.json()
    task_id = body["params"].get("task_id")
    alert_content = body["params"].get("message")

    ASYNC FUNCTION event_generator():
        last_keep_alive = now()

        TRY:
            ASYNC FOR event IN executor.execute_stream(task_id, alert_content):
                IF AWAIT request.is_disconnected():
                    BREAK

                YIELD {"data": json.dumps(event)}

                # Keep-alive every 25 seconds
                IF now() - last_keep_alive > 25:
                    YIELD {
                        "data": json.dumps({
                            "event_type": "keep_alive",
                            "timestamp": now().isoformat()
                        })
                    }
                    last_keep_alive = now()

        FINALLY:
            # Cleanup resources
            PASS

    RETURN EventSourceResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

**Agent Card Update**:
```json
{
  "name": "insider-trading-analyzer",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false
  }
}
```

---

### Layer 5: Orchestrator Streaming

**File**: `src/alerts/a2a/orchestrator_executor.py`

**Pattern**: Pass-through (forward specialized agent events)

**Algorithm**:
```
ASYNC FUNCTION execute_stream(self, task_id, alert_content):
    # Emit routing started
    YIELD self._create_event("routing_started", {
        "alert_type": detected_type,
        "target_agent": target_url
    })

    # Connect to specialized agent with streaming
    ASYNC WITH httpx.AsyncClient() AS client:
        ASYNC WITH client.stream(
            "POST",
            f"{target_url}/message/stream",
            json={"params": {"task_id": task_id, "message": alert_content}}
        ) AS response:

            ASYNC FOR line IN response.aiter_lines():
                IF line.startswith("data:"):
                    event = json.loads(line[5:])
                    # Pass through with orchestrator tag
                    YIELD event

    # Emit routing completed
    YIELD self._create_event("routing_completed", {
        "target_agent": target_url
    }, final=True)
```

---

### Layer 6: FastAPI Backend

**File**: `src/frontend/app.py`

**Changes**:
1. Add `GET /api/stream/{task_id}` SSE endpoint
2. Modify `POST /api/analyze` to return immediately with task_id
3. Store events in task_manager

**Algorithm**:
```
@app.post("/api/analyze")
ASYNC FUNCTION analyze_alert(file: UploadFile):
    task_id = generate_uuid()
    alert_content = AWAIT file.read()

    # Store task as pending
    task_manager.create_task(task_id)

    # Start analysis in background (don't await)
    asyncio.create_task(
        _run_analysis_with_events(task_id, alert_content)
    )

    RETURN {"task_id": task_id, "status": "submitted"}


@app.get("/api/stream/{task_id}")
ASYNC FUNCTION stream_task(task_id: str, request: Request):

    ASYNC FUNCTION event_generator():
        ASYNC WITH httpx.AsyncClient(timeout=600.0) AS client:
            ASYNC WITH client.stream(
                "POST",
                f"{ORCHESTRATOR_URL}/message/stream",
                json={"params": {"task_id": task_id, "message": alert_content}}
            ) AS response:

                ASYNC FOR line IN response.aiter_lines():
                    IF AWAIT request.is_disconnected():
                        BREAK

                    IF line.startswith("data:"):
                        event_data = line[5:].strip()

                        # Store event for history
                        task_manager.add_event(task_id, json.loads(event_data))

                        # Forward to client
                        YIELD {"data": event_data}

    RETURN EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"}  # Disable nginx buffering
    )
```

---

### Layer 7: Frontend

**Files**:
- `src/frontend/static/js/stream.js` (new)
- `src/frontend/static/js/upload.js` (modify)
- `src/frontend/templates/upload.html` (modify)

**Algorithm**:
```javascript
// stream.js
CLASS ProgressTimeline {
    constructor(containerId) {
        this.container = document.getElementById(containerId)
        this.events = []
        this.eventSource = null
    }

    connectToTask(taskId) {
        this.eventSource = new EventSource(`/api/stream/${taskId}`)

        this.eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data)
            this.handleEvent(data)
        }

        this.eventSource.onerror = (error) => {
            IF (this.eventSource.readyState === EventSource.CLOSED) {
                this.showCompleted()
            } ELSE {
                this.showReconnecting()
                // Browser auto-reconnects after ~3 seconds
            }
        }
    }

    handleEvent(event) {
        this.events.push(event)

        SWITCH (event.event_type) {
            CASE "tool_started":
                this.addTimelineEntry(event, "in-progress")
                BREAK
            CASE "tool_completed":
                this.updateTimelineEntry(event.tool_name, "completed", event.summary)
                BREAK
            CASE "agent_thinking":
                this.addThinkingIndicator(event.message)
                BREAK
            CASE "analysis_complete":
                this.eventSource.close()
                this.showResults(event)
                BREAK
            CASE "error":
                this.eventSource.close()
                this.showError(event.error_message)
                BREAK
            CASE "keep_alive":
                // Ignore, just keeps connection alive
                BREAK
        }
    }

    disconnect() {
        IF (this.eventSource) {
            this.eventSource.close()
        }
    }
}
```

**UI Pattern**: Progress Timeline (inspired by GitHub Actions)

```html
<div id="progress-timeline" class="space-y-2">
    <!-- Dynamically populated -->
    <div class="timeline-entry completed">
        <span class="icon">✓</span>
        <span class="tool-name">trader_history</span>
        <span class="summary">Found 10x volume anomaly</span>
    </div>
    <div class="timeline-entry in-progress">
        <span class="icon spinning">⟳</span>
        <span class="tool-name">market_news</span>
        <span class="summary">Analyzing news timeline...</span>
    </div>
    <div class="timeline-entry pending">
        <span class="icon">○</span>
        <span class="tool-name">peer_trades</span>
    </div>
</div>
```

---

## Event Flow Sequence Diagram

```
Browser          FastAPI         Orchestrator      IT Agent         Tool
   │                │                 │               │               │
   │ POST /analyze  │                 │               │               │
   │───────────────▶│                 │               │               │
   │ {task_id}      │                 │               │               │
   │◀───────────────│                 │               │               │
   │                │                 │               │               │
   │ GET /stream/id │                 │               │               │
   │───────────────▶│                 │               │               │
   │                │ POST /message/stream            │               │
   │                │────────────────▶│               │               │
   │                │                 │ routing_started               │
   │                │◀────────────────│               │               │
   │ SSE: routing   │                 │               │               │
   │◀───────────────│                 │               │               │
   │                │                 │ POST /message/stream          │
   │                │                 │──────────────▶│               │
   │                │                 │               │ tool_started  │
   │                │                 │               │──────────────▶│
   │                │                 │◀──────────────│               │
   │                │◀────────────────│               │               │
   │ SSE: tool_start│                 │               │               │
   │◀───────────────│                 │               │               │
   │                │                 │               │               │
   │                │                 │               │ tool_completed│
   │                │                 │               │◀──────────────│
   │                │                 │◀──────────────│               │
   │                │◀────────────────│               │               │
   │ SSE: tool_done │                 │               │               │
   │◀───────────────│                 │               │               │
   │                │                 │               │               │
   │     ...        │      ...        │     ...       │     ...       │
   │                │                 │               │               │
   │                │                 │               │ analysis_complete
   │                │                 │               │ (final: true) │
   │                │                 │◀──────────────│               │
   │                │◀────────────────│               │               │
   │ SSE: complete  │                 │               │               │
   │◀───────────────│                 │               │               │
   │                │                 │               │               │
   │ [close stream] │                 │               │               │
   │                │                 │               │               │
```

---

## Error Handling

**Philosophy**: Fail-fast with explicit error events.

### Error Event Structure
```json
{
  "event_type": "error",
  "tool_name": "trader_history",
  "error_message": "Failed to load trader_history.csv: File not found",
  "timestamp": "2025-12-03T10:30:00Z"
}
```

### Error Propagation
1. Tool throws exception → caught by agent
2. Agent emits error event with `final: true`
3. Error propagates through orchestrator to frontend
4. Frontend closes EventSource and displays error UI

### No Fallback
- Do NOT attempt recovery
- Do NOT use default values
- Do NOT continue with partial results
- Crash loudly so issues are immediately visible

---

## Reconnection Strategy

**Browser Behavior**: EventSource auto-reconnects on error (~3 seconds default).

**Server Behavior**:
- Check `request.is_disconnected()` before each yield
- Clean up resources when client disconnects

**Resume Strategy**: Resume from current state (no replay).
- New connection gets events from current point forward
- Historical events available via `task_manager.get_events(task_id)`

---

## Historical Event Storage

**Location**: `task_manager.py` (in-memory, existing POC pattern)

**Structure**:
```python
class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, Task] = {}

    def add_event(self, task_id: str, event: dict):
        """Store event for post-analysis review"""
        if task_id in self.tasks:
            self.tasks[task_id].events.append(event)

    def get_events(self, task_id: str) -> List[dict]:
        """Retrieve all events for a task"""
        if task_id in self.tasks:
            return self.tasks[task_id].events
        return []
```

**Access**: Events available via `GET /api/status/{task_id}` after completion.

---

## Keep-Alive Mechanism

**Interval**: Every 25 seconds

**Format**: Full event (visible for debugging)
```json
{
  "event_type": "keep_alive",
  "timestamp": "2025-12-03T10:30:25Z"
}
```

**Purpose**:
- Prevent proxy/load balancer timeouts (typically 30-60 seconds)
- Keep SSE connection alive during slow LLM operations
- Provide heartbeat for connection health monitoring

---

## Configuration Requirements

### Load Balancer / Nginx
```nginx
# Disable buffering for SSE
proxy_buffering off;
proxy_cache off;

# Increase timeouts for 5-10 minute tasks
proxy_read_timeout 900s;  # 15 minutes
proxy_send_timeout 900s;
```

### FastAPI
```python
# Disable response buffering
headers = {"X-Accel-Buffering": "no"}
```

### httpx Client
```python
# Long timeout for A2A streaming
async with httpx.AsyncClient(timeout=600.0) as client:
    ...
```

---

## Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `src/frontend/static/js/stream.js` | EventSource client + timeline UI |

### Modified Files
| File | Changes |
|------|---------|
| `src/alerts/tools/base.py` | Add stream_writer support |
| `src/alerts/agents/insider_trading/agent.py` | Add arun_with_events() |
| `src/alerts/agents/wash_trade/agent.py` | Add arun_with_events() |
| `src/alerts/a2a/insider_trading_executor.py` | Add execute_stream() |
| `src/alerts/a2a/wash_trade_executor.py` | Add execute_stream() |
| `src/alerts/a2a/orchestrator_executor.py` | Add execute_stream() with pass-through |
| `src/alerts/a2a/insider_trading_server.py` | Add /message/stream endpoint |
| `src/alerts/a2a/wash_trade_server.py` | Add /message/stream endpoint |
| `src/alerts/a2a/orchestrator_server.py` | Add /message/stream endpoint |
| `src/frontend/app.py` | Add /api/stream/{task_id} endpoint |
| `src/frontend/task_manager.py` | Add event storage |
| `src/frontend/static/js/upload.js` | Replace polling with EventSource |
| `src/frontend/templates/upload.html` | Add timeline UI container |

---

## Testing Strategy

### Unit Tests
- Tool event emission with mock stream_writer
- Event schema validation
- A2A event wrapper formatting

### Integration Tests
- SSE endpoint returns correct content-type
- Events arrive in order
- Client disconnect handled gracefully
- Keep-alive events sent at correct interval

### E2E Tests
- Full flow: upload → stream → complete
- Error propagation through all layers
- Browser reconnection behavior

---

## Implementation Phases

### Phase 1: Tool Layer (2-3 days)
- Modify BaseTool to accept stream_writer
- Add event emission to all tools
- Unit tests

### Phase 2: Agent Layer (2-3 days)
- Add arun_with_events() to both agents
- Emit agent_thinking events
- Integration tests

### Phase 3: A2A Layer (3-4 days)
- Add execute_stream() to executors
- Add /message/stream endpoints to servers
- Update Agent Cards
- Integration tests

### Phase 4: Backend Layer (2-3 days)
- Add /api/stream/{task_id} endpoint
- Modify /api/analyze for immediate return
- Add event storage to task_manager
- Integration tests

### Phase 5: Frontend Layer (3-4 days)
- Create stream.js with ProgressTimeline
- Build timeline UI component
- Replace polling with EventSource
- E2E tests

### Phase 6: Polish (2-3 days)
- Keep-alive implementation
- Error handling refinement
- Load testing
- Documentation

---

## Dependencies to Add

```toml
# pyproject.toml
[project.dependencies]
sse-starlette = ">=3.0.3"
httpx = ">=0.24.0"
```

---

## References

- [A2A Protocol Specification v0.3.0](https://a2a-protocol.org/latest/specification/)
- [LangGraph Streaming Documentation](https://docs.langchain.com/oss/python/langgraph/streaming)
- [sse-starlette GitHub](https://github.com/sysid/sse-starlette)
- [MDN EventSource API](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- Research documents: `resources/research/real-time-agent-streaming/`
