# Real-Time Agent Event Streaming: Quick Start Guide

A condensed reference for implementing streaming across your LangGraph multi-agent system.

---

## TL;DR: Architecture Overview

```
Browser (EventSource)
  ↓ GET /api/stream/{task_id}
FastAPI Backend (sse-starlette)
  ↓ A2A POST /message/stream
Orchestrator Agent (LangGraph)
  ↓ Routes to specialized agent
Specialized Agent (LangGraph + astream_events)
  ↓ Tool calls with custom events
Tools
```

**Key Technologies**:
- **A2A Protocol**: Streaming between agents via SSE + JSON-RPC
- **LangGraph**: `astream_events()` for internal agent streaming
- **FastAPI**: `sse-starlette` for backend SSE endpoint
- **EventSource**: Native browser API for client-side SSE

---

## Installation

```bash
# Backend dependencies
pip install fastapi>=0.95.0
pip install sse-starlette>=3.0.3
pip install langgraph>=0.1.0
pip install httpx>=0.24.0

# Frontend
# No npm packages needed - use native EventSource API
```

---

## Minimal Working Example

### 1. Tool with Custom Events (LangGraph)

```python
# src/alerts/tools/example_tool.py

class ExampleTool:
    def __call__(self, state, config):
        stream_writer = config.get("stream_writer")

        if stream_writer:
            stream_writer({"type": "tool_start", "message": "Starting..."})

        # Do work...

        if stream_writer:
            stream_writer({"type": "tool_complete", "message": "Done!"})

        return {"result": "..."}
```

### 2. A2A Agent Server (Streaming)

```python
# src/alerts/a2a/agent_server.py

from fastapi import FastAPI, Request
from sse_starlette import EventSourceResponse
import json

app = FastAPI()

@app.post("/message/stream")
async def message_stream(request: Request):
    body = await request.json()
    task_id = body["params"].get("task_id", "unknown")

    async def event_generator():
        async for mode, chunk in agent.astream_events(input):
            if await request.is_disconnected():
                break

            # Convert LangGraph event to A2A format
            yield {
                "data": json.dumps({
                    "jsonrpc": "2.0",
                    "result": {
                        "task": {"id": task_id, "state": "working"},
                        "taskStatusUpdateEvent": {
                            "task": {"id": task_id},
                            "final": False
                        }
                    }
                })
            }

    return EventSourceResponse(event_generator())
```

### 3. FastAPI Backend (Streaming Proxy)

```python
# src/frontend/app.py

from fastapi import FastAPI
from sse_starlette import EventSourceResponse
import httpx
import json

app = FastAPI()

@app.get("/api/stream/{task_id}")
async def stream_task(task_id: str, request):
    async def event_generator():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                "http://localhost:10000/message/stream",
                json={"params": {"task_id": task_id}}
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        yield {"data": line[5:].strip()}

                    if await request.is_disconnected():
                        break

    return EventSourceResponse(event_generator())
```

### 4. Frontend (JavaScript)

```javascript
// frontend/static/js/stream.js

const eventSource = new EventSource(`/api/stream/task-123`);

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log("Progress:", data);
    updateUI(data);
};

eventSource.onerror = (error) => {
    if (eventSource.readyState === EventSource.CLOSED) {
        console.log("Stream closed");
    }
};

// Browser auto-reconnects on error
```

---

## Key Patterns

### Pattern 1: Emit Events from Tool

```python
def my_tool(state, config):
    stream_writer = config.get("stream_writer")

    # Emit progress event
    stream_writer({"type": "progress", "message": "Processing..."})

    # ... do work ...

    return {"result": "..."}
```

### Pattern 2: Stream from Agent

```python
async for mode, chunk in agent.astream_events(input, stream_mode=["custom"]):
    if mode == "custom":
        print(chunk)  # Progress data
```

### Pattern 3: A2A to SSE Conversion

```python
# In A2A server endpoint
async for mode, chunk in agent.astream_events(input):
    # Convert to A2A TaskStatusUpdateEvent
    a2a_event = {
        "jsonrpc": "2.0",
        "result": {
            "taskStatusUpdateEvent": {
                "task": {"id": task_id, "state": "working"},
                "final": False
            }
        }
    }
    yield {"data": json.dumps(a2a_event)}
```

### Pattern 4: Backend Proxy to Frontend

```python
# In FastAPI endpoint
async with httpx.AsyncClient() as client:
    async with client.stream("POST", agent_url) as response:
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                yield {"data": line[5:]}  # Forward SSE event
```

### Pattern 5: Frontend Progress UI

```javascript
const timeline = new ProgressTimeline('container-id');
timeline.connectToTask('task-123');

// Listen for events (optional, if using custom EventSource handler)
eventSource.addEventListener('progress', (e) => {
    const data = JSON.parse(e.data);
    console.log(data.message);
});
```

---

## Common Gotchas & Solutions

### ❌ Client Still Connected?

```python
# Bad - might crash if client disconnects
async for event in stream:
    yield {"data": event}

# Good
async for event in stream:
    if await request.is_disconnected():
        break
    yield {"data": event}
```

### ❌ JSON Data Not Parseable

```python
# Bad
yield {"data": str(some_dict)}

# Good
yield {"data": json.dumps(some_dict)}
```

### ❌ Sync Blocking Async Loop

```python
# Bad
async def event_gen():
    data = load_data()  # BLOCKS!

# Good
async def event_gen():
    data = await load_data()  # Async
```

### ❌ No Resource Cleanup

```python
# Bad
async def event_gen():
    conn = db.connect()
    async for event in conn.stream():
        yield {"data": event}
    # conn never closed!

# Good
async def event_gen():
    conn = db.connect()
    try:
        async for event in conn.stream():
            yield {"data": event}
    finally:
        await conn.close()
```

### ❌ Forgetting Retry Header

```python
# Without retry header, client won't reconnect properly
yield {
    "data": json.dumps(data),
    "retry": 5000  # Tell client to wait 5s before retry
}
```

---

## Deployment Checklist

- [ ] Set `capabilities.streaming: true` in Agent Card
- [ ] Add `X-Accel-Buffering: no` header (disable nginx buffering)
- [ ] Configure load balancer timeout ≥ 15 minutes for 5-10 min tasks
- [ ] Set `recursion_limit=50` in LangGraph to allow multiple tool calls
- [ ] Use `disable_streaming=True` for non-streaming LLMs (e.g., O1)
- [ ] Implement keep-alive: send dummy event every 20-30s
- [ ] Log every stream open, close, error, reconnection
- [ ] Test with 100+ concurrent connections
- [ ] Implement `tasks/resubscribe` for SSE connection recovery

---

## Testing

### Unit Test: Tool Events

```python
@pytest.mark.asyncio
async def test_tool_events():
    events = []

    async def capture_event(event):
        events.append(event)

    config = {"stream_writer": capture_event}
    result = await my_tool(state, config)

    assert events[0]["type"] == "tool_start"
    assert events[-1]["type"] == "tool_complete"
```

### Integration Test: SSE Endpoint

```python
@pytest.mark.asyncio
async def test_sse_stream():
    async with httpx.AsyncClient(app=app) as client:
        async with client.stream("GET", "/api/stream/task-1") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[5:])
                    assert "result" in data
```

### E2E Test: Full Stack

```javascript
describe('End-to-End Streaming', () => {
    it('should stream events from agent to UI', (done) => {
        const es = new EventSource('/api/stream/task-1');
        let eventCount = 0;

        es.onmessage = () => {
            eventCount++;
            if (eventCount >= 3) {
                es.close();
                done();
            }
        };
    });
});
```

---

## Performance Tuning

| Setting | Value | Reason |
|---------|-------|--------|
| Event emit interval | 10-100ms | Balance responsiveness vs overhead |
| Keep-alive interval | 20-30s | Prevent proxy timeouts |
| Load balancer timeout | 15+ minutes | 5-10 min tasks + buffer |
| Max concurrent SSE | Per-agent limit | Prevent resource exhaustion |
| Event buffer size | 100+ events | Handle slow clients |

---

## Debugging

### See Server-Side Events

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Now you'll see all event emissions logged
```

### Monitor Client Connections

```python
import signal

active_streams = []

async def event_generator():
    active_streams.append(task_id)
    try:
        async for event in stream:
            yield {"data": event}
    finally:
        active_streams.remove(task_id)

print(f"Active streams: {len(active_streams)}")
```

### Browser DevTools

```javascript
// In console
const es = new EventSource('/api/stream/task-1');
es.onmessage = (e) => console.log(JSON.parse(e.data));
es.onerror = (e) => console.error('Stream error', e);
```

---

## When to Use Each Technology

| Technology | When | Why |
|-----------|------|-----|
| **SSE** | Server → Client streaming | Simple, HTTP, native browser support |
| **WebSocket** | Bi-directional messaging | Not needed for your use case |
| **A2A Protocol** | Agent → Agent streaming | Standard, interoperable, flexible |
| **LangGraph astream_events** | Internal agent event emission | Composable, multiple stream modes |
| **Custom events** | Progress tracking from tools | Lightweight, low latency |

---

## References

- **A2A Spec**: https://a2a-protocol.org/latest/specification/
- **LangGraph Streaming**: https://docs.langchain.com/oss/python/langgraph/streaming
- **sse-starlette**: https://github.com/sysid/sse-starlette
- **EventSource API**: https://developer.mozilla.org/en-US/docs/Web/API/EventSource

---

## Next Steps

1. **Start simple**: Emit events from one tool using `stream_writer`
2. **Add A2A**: Wrap agent in A2A server with `message/stream` RPC
3. **Connect backend**: Proxy A2A events to frontend via FastAPI SSE
4. **Build UI**: Create progress timeline with EventSource
5. **Test & iterate**: Load test and refine event frequency

Good luck! 🚀
