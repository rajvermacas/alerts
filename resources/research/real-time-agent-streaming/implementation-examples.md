# Real-Time Agent Event Streaming: Complete Code Examples

This document provides production-ready code examples for implementing real-time streaming across your 4-layer architecture.

---

## 1. LangGraph Custom Events Emission

### 1.1 Base Tool with Event Streaming

```python
# src/alerts/tools/base.py

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable
import logging

logger = logging.getLogger(__name__)

class BaseTool(ABC):
    """
    Base tool class with built-in event streaming support.
    Emit custom events via stream_writer for progress tracking.
    """

    def __init__(self, name: str):
        self.name = name
        self.stream_writer: Optional[Callable[[Dict[str, Any]], None]] = None

    @abstractmethod
    def _load_data(self, **kwargs) -> str:
        """Load raw data from source"""
        pass

    @abstractmethod
    def _build_interpretation_prompt(self, raw_data: str, **kwargs) -> str:
        """Build LLM prompt to interpret data"""
        pass

    def emit_event(self, event: Dict[str, Any]) -> None:
        """Emit custom event for streaming"""
        if self.stream_writer:
            # Add tool metadata to event
            event["tool_name"] = self.name
            event["timestamp"] = datetime.utcnow().isoformat()
            logger.info(f"Tool event: {event}")
            self.stream_writer(event)
        else:
            logger.debug(f"No stream writer configured for event: {event}")

    async def __call__(self, state: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute tool with event streaming support.

        Args:
            state: Current graph state
            config: RunConfig with optional 'stream_writer' callback

        Returns:
            Updated state
        """
        # Extract stream writer from config
        self.stream_writer = config.get("stream_writer") if config else None

        try:
            # Emit start event
            self.emit_event({
                "type": "tool_start",
                "description": f"Starting {self.name}..."
            })

            # Load data
            self.emit_event({
                "type": "tool_progress",
                "step": 1,
                "total": 3,
                "message": "Loading data from source..."
            })

            raw_data = await self._load_data(**state)

            # Interpret with LLM
            self.emit_event({
                "type": "tool_progress",
                "step": 2,
                "total": 3,
                "message": "Interpreting data with LLM..."
            })

            prompt = self._build_interpretation_prompt(raw_data, **state)
            insights = await self._interpret_with_llm(prompt)

            # Complete
            self.emit_event({
                "type": "tool_progress",
                "step": 3,
                "total": 3,
                "message": "Processing complete..."
            })

            self.emit_event({
                "type": "tool_complete",
                "result_summary": self._summarize_insights(insights)
            })

            return {"tool_insights": insights}

        except Exception as e:
            logger.exception(f"Tool {self.name} failed")
            self.emit_event({
                "type": "tool_error",
                "error": str(e)
            })
            raise

    async def _interpret_with_llm(self, prompt: str) -> str:
        """Interpret raw data using LLM"""
        # Implement LLM call here
        pass

    def _summarize_insights(self, insights: str) -> str:
        """Create brief summary of insights"""
        return insights[:200] + "..." if len(insights) > 200 else insights
```

### 1.2 Concrete Tool Example: Trader History

```python
# src/alerts/tools/trader_history.py

import csv
from datetime import datetime
from typing import Dict, Any

class TraderHistoryTool(BaseTool):
    """Tool for analyzing trader's historical trading patterns"""

    def __init__(self, data_dir: str):
        super().__init__(name="trader_history_analyzer")
        self.data_file = f"{data_dir}/trader_history.csv"

    async def _load_data(self, **kwargs) -> str:
        """Load trader history CSV"""
        trader_id = kwargs.get("trader_id")

        # Emit fine-grained progress
        self.emit_event({
            "type": "data_loading",
            "message": f"Searching for trader {trader_id}..."
        })

        trades = []
        with open(self.data_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["trader_id"] == trader_id:
                    trades.append(row)

        self.emit_event({
            "type": "data_loaded",
            "record_count": len(trades),
            "date_range": f"{trades[0]['date']} to {trades[-1]['date']}" if trades else "N/A"
        })

        # Format for LLM
        return self._format_trades_for_llm(trades)

    async def _build_interpretation_prompt(self, raw_data: str, **kwargs) -> str:
        """Build prompt for LLM analysis"""
        return f"""
Analyze the following trader's historical trading patterns.
Look for baseline trading volume, typical sectors, and anomalies.

Trade History:
{raw_data}

Provide a structured analysis of:
1. Average daily trading volume
2. Typical trading sectors
3. Time of day patterns
4. Any notable anomalies or changes in behavior
"""

    def _format_trades_for_llm(self, trades: list) -> str:
        """Format CSV data for LLM consumption"""
        lines = []
        for trade in trades[-50:]:  # Last 50 trades
            lines.append(
                f"Date: {trade['date']}, Volume: {trade['volume']}, "
                f"Sector: {trade['sector']}, Time: {trade['time']}"
            )
        return "\n".join(lines)
```

### 1.3 Agent Integration: Using Custom Events in Graph

```python
# src/alerts/agents/insider_trading/agent.py

from langgraph.graph import StateGraph, START, END
from langgraph.types import StreamWriter
from typing import Any, Dict, cast

class InsiderTradingAgent:
    """Agent for insider trading analysis with streaming support"""

    def __init__(self, llm, tools):
        self.llm = llm
        self.tools = {tool.name: tool for tool in tools}
        self.graph = self._build_graph()

    def _build_graph(self):
        """Build LangGraph with streaming support"""
        builder = StateGraph(MessagesState)

        # Add agent node
        builder.add_node("agent", self._agent_node)

        # Add tool nodes
        for tool in self.tools.values():
            builder.add_node(tool.name, self._create_tool_node(tool))

        builder.add_edge(START, "agent")
        builder.add_edge("agent", END)

        return builder.compile()

    def _agent_node(self, state: MessagesState):
        """Main reasoning node"""
        messages = state["messages"]
        return {"messages": messages + [self.llm.invoke(messages)]}

    def _create_tool_node(self, tool):
        """Create tool node that preserves stream_writer in config"""
        async def tool_node(state: MessagesState, config: Any):
            # The config contains stream_writer from parent astream_events()
            tool_result = await tool(state, config)
            return {"messages": [ToolMessage(content=str(tool_result))]}

        return tool_node

    async def stream_analysis(self, alert_data: str):
        """
        Stream analysis events to caller.

        Usage:
            async for mode, chunk in agent.stream_analysis(alert):
                if mode == "custom":
                    progress = chunk
                    print(f"Progress: {progress}")
        """
        input_state = {
            "messages": [HumanMessage(content=alert_data)]
        }

        async for mode, chunk in self.graph.astream_events(
            input=input_state,
            stream_mode=["updates", "custom"],
            config={}
        ):
            yield mode, chunk
```

---

## 2. A2A SSE Agent Implementation

### 2.1 Agent Executor with Streaming

```python
# src/alerts/a2a/insider_trading_executor.py

import json
import logging
from typing import AsyncGenerator, Dict, Any
from langgraph.types import StreamWriter

logger = logging.getLogger(__name__)

class InsiderTradingAgentExecutor:
    """
    Executes insider trading analysis and streams results via A2A protocol.
    Maps LangGraph events to A2A TaskStatusUpdateEvent.
    """

    def __init__(self, agent, llm):
        self.agent = agent
        self.llm = llm

    async def stream_message(
        self,
        task_id: str,
        alert_data: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream task execution as A2A TaskStatusUpdateEvent.

        Yields A2A-formatted events ready for SSE transmission.
        """
        logger.info(f"Starting stream for task {task_id}")

        try:
            # Map to A2A TaskStatusUpdateEvent
            event_counter = 0

            # Emit initial "working" state
            yield self._create_status_event(
                task_id=task_id,
                state="working",
                message="Initializing analysis...",
                event_id=str(event_counter),
                final=False
            )
            event_counter += 1

            # Stream events from agent
            async for mode, chunk in self.agent.stream_analysis(alert_data):
                if mode == "custom":
                    # Custom event from tool
                    progress_data = chunk

                    yield self._create_status_event(
                        task_id=task_id,
                        state="working",
                        message=progress_data.get("message", "Processing..."),
                        metadata={
                            "tool_name": progress_data.get("tool_name"),
                            "step": progress_data.get("step"),
                            "total": progress_data.get("total"),
                            "event_type": progress_data.get("type")
                        },
                        event_id=str(event_counter),
                        final=False
                    )
                    event_counter += 1

                elif mode == "updates":
                    # State update from agent node
                    logger.debug(f"Agent state update: {chunk}")

            # Emit completion with final decision
            final_decision = await self._generate_final_decision(alert_data)

            yield self._create_status_event(
                task_id=task_id,
                state="completed",
                message="Analysis complete",
                artifacts=[
                    {
                        "type": "decision",
                        "data": final_decision
                    }
                ],
                event_id=str(event_counter),
                final=True
            )

            logger.info(f"Completed stream for task {task_id} ({event_counter} events)")

        except Exception as e:
            logger.exception(f"Stream error for task {task_id}")
            yield self._create_status_event(
                task_id=task_id,
                state="failed",
                message=f"Error: {str(e)}",
                event_id=str(event_counter),
                final=True
            )

    def _create_status_event(
        self,
        task_id: str,
        state: str,
        message: str,
        event_id: str,
        final: bool,
        metadata: Dict[str, Any] = None,
        artifacts: list = None
    ) -> Dict[str, Any]:
        """
        Create A2A TaskStatusUpdateEvent wrapped in JSON-RPC Response.

        This is what gets sent over SSE.
        """
        task_message = {
            "role": "agent",
            "parts": [
                {
                    "type": "textPart",
                    "text": message
                }
            ]
        }

        if metadata:
            # Add metadata as structured part (optional)
            task_message["parts"].append({
                "type": "dataPart",
                "data": json.dumps(metadata)
            })

        return {
            "jsonrpc": "2.0",
            "result": {
                "task": {
                    "id": task_id,
                    "state": state
                },
                "taskStatusUpdateEvent": {
                    "task": {
                        "id": task_id,
                        "state": state,
                        "messages": [task_message]
                    },
                    "artifacts": artifacts or [],
                    "final": final
                }
            }
        }

    async def _generate_final_decision(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate final decision from agent"""
        # Would call agent to get final structured decision
        return {
            "determination": "ESCALATE",
            "confidence": 85,
            "findings": ["Pattern matches precedent case"]
        }
```

### 2.2 A2A Server Endpoint with SSE

```python
# src/alerts/a2a/insider_trading_server.py

from fastapi import FastAPI, Request
from sse_starlette import EventSourceResponse
import json
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

class InsiderTradingA2AServer:
    """
    FastAPI A2A server exposing insider trading agent via SSE streaming.
    """

    def __init__(self, agent, port: int = 10001):
        self.app = FastAPI(title="Insider Trading Agent (A2A)")
        self.executor = InsiderTradingAgentExecutor(agent)
        self.port = port

        self._setup_routes()

    def _setup_routes(self):
        """Setup A2A protocol endpoints"""

        @self.app.get("/.well-known/agent.json")
        async def get_agent_card():
            """Advertise agent capabilities"""
            return {
                "id": "insider-trading-agent",
                "name": "Insider Trading Analyzer",
                "description": "Analyzes SMARTS alerts for insider trading patterns",
                "capabilities": {
                    "streaming": True,
                    "pushNotifications": False,
                    "authenticated": False
                },
                "endpoint": f"http://localhost:{self.port}"
            }

        @self.app.post("/message/stream")
        async def message_stream(request: Request):
            """
            A2A message/stream RPC endpoint.

            Receives: JSON-RPC request with alert message
            Returns: Server-Sent Events stream of TaskStatusUpdateEvent
            """
            body = await request.json()

            # Extract A2A request
            jsonrpc = body.get("jsonrpc")
            method = body.get("method")
            params = body.get("params", {})
            task_id = params.get("task_id", "unknown")

            logger.info(f"Stream request: method={method}, task_id={task_id}")

            # Extract alert message from params
            messages = params.get("messages", [])
            alert_text = messages[0].get("parts", [{}])[0].get("text", "") if messages else ""

            async def event_generator() -> AsyncGenerator[Dict[str, str], None]:
                """Generate SSE events from executor"""
                try:
                    # Check client still connected
                    if await request.is_disconnected():
                        logger.debug(f"Client disconnected before stream start: {task_id}")
                        return

                    # Stream from executor
                    async for a2a_event in self.executor.stream_message(
                        task_id=task_id,
                        alert_data={"text": alert_text}
                    ):
                        # Check for disconnect between events
                        if await request.is_disconnected():
                            logger.debug(f"Client disconnected during stream: {task_id}")
                            break

                        # Convert A2A event to SSE format
                        sse_event = {
                            "data": json.dumps(a2a_event),
                            "event": "task_update",
                            "id": a2a_event.get("result", {}).get("taskStatusUpdateEvent", {}).get("task", {}).get("id"),
                            "retry": 5000
                        }

                        logger.debug(f"Emitting SSE event for task {task_id}")
                        yield sse_event

                        # Small delay to prevent overwhelming client
                        await asyncio.sleep(0.01)

                except Exception as e:
                    logger.exception(f"Error in event_generator: {e}")
                    yield {
                        "data": json.dumps({
                            "jsonrpc": "2.0",
                            "error": {"code": -32000, "message": str(e)}
                        }),
                        "event": "error"
                    }

            return EventSourceResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "X-Accel-Buffering": "no",  # Disable buffering in nginx
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive"
                }
            )

        @self.app.get("/tasks/{task_id}")
        async def get_task(task_id: str):
            """
            A2A tasks/get RPC endpoint.

            Returns current task state (for resubscription after disconnect).
            """
            # Would fetch cached task state
            return {
                "id": task_id,
                "state": "working",  # or "completed", "failed"
                "messages": [
                    {
                        "role": "agent",
                        "parts": [{"type": "textPart", "text": "Analysis in progress..."}]
                    }
                ]
            }

    def run(self):
        """Start the A2A server"""
        import uvicorn
        logger.info(f"Starting Insider Trading A2A server on port {self.port}")
        uvicorn.run(self.app, host="0.0.0.0", port=self.port)
```

---

## 3. FastAPI Backend SSE Endpoint

### 3.1 Backend Streaming Endpoint

```python
# src/frontend/app.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from sse_starlette import EventSourceResponse
from typing import AsyncGenerator, Dict, Any
import json
import logging
import httpx
import asyncio

logger = logging.getLogger(__name__)

app = FastAPI(title="SMARTS Alert Analyzer Frontend")

class A2AClient:
    """Client for communicating with A2A agents"""

    def __init__(self, base_url: str):
        self.base_url = base_url

    async def stream_message(self, alert_data: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream message to agent and receive events"""
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/message/stream",
                json={
                    "jsonrpc": "2.0",
                    "method": "message/stream",
                    "params": {
                        "messages": [
                            {
                                "role": "user",
                                "parts": [
                                    {"type": "textPart", "text": alert_data}
                                ]
                            }
                        ]
                    }
                }
            ) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Agent returned {response.status_code}"
                    )

                # Parse SSE stream
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue

                    if line.startswith("data:"):
                        data_json = line[5:].strip()
                        try:
                            data = json.loads(data_json)
                            yield data
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse JSON: {data_json}")

@app.get("/api/stream/{task_id}")
async def stream_task_events(task_id: str, request: Request):
    """
    Stream events for a task to frontend.

    Frontend connects with:
        const es = new EventSource(`/api/stream/${taskId}`);
    """

    async def event_generator():
        """Generate SSE events by proxying A2A stream"""
        logger.info(f"Frontend connected for task {task_id}")

        orchestrator_url = "http://localhost:10000"
        a2a_client = A2AClient(orchestrator_url)

        try:
            # Get task details from orchestrator (to know what to analyze)
            async with httpx.AsyncClient() as client:
                task_response = await client.get(
                    f"{orchestrator_url}/tasks/{task_id}"
                )

                if task_response.status_code != 200:
                    raise HTTPException(
                        status_code=task_response.status_code,
                        detail="Task not found"
                    )

                task_data = task_response.json()
                alert_text = task_data.get("alert_text", "")

            # Stream from orchestrator agent
            event_counter = 0
            async for a2a_event in a2a_client.stream_message(alert_text):
                # Check client still connected
                if await request.is_disconnected():
                    logger.info(f"Client disconnected: {task_id}")
                    break

                # Transform A2A event to frontend-friendly format
                try:
                    result = a2a_event.get("result", {})
                    status_event = result.get("taskStatusUpdateEvent", {})
                    task = status_event.get("task", {})
                    messages = task.get("messages", [])

                    # Extract message text for display
                    message_text = ""
                    if messages:
                        parts = messages[0].get("parts", [])
                        if parts:
                            message_text = parts[0].get("text", "")

                    # Create frontend event
                    frontend_event = {
                        "event_id": event_counter,
                        "task_id": task_id,
                        "state": task.get("state", "unknown"),
                        "message": message_text,
                        "final": status_event.get("final", False),
                        "timestamp": datetime.utcnow().isoformat()
                    }

                    # Extract metadata if present
                    if len(parts) > 1 and parts[1].get("type") == "dataPart":
                        try:
                            metadata = json.loads(parts[1].get("data", "{}"))
                            frontend_event["metadata"] = metadata
                        except:
                            pass

                    logger.debug(f"Forwarding event {event_counter}: {frontend_event}")

                    # Yield as SSE
                    yield {
                        "data": json.dumps(frontend_event),
                        "event": "progress" if not status_event.get("final") else "complete",
                        "id": str(event_counter),
                        "retry": 5000
                    }

                    event_counter += 1

                except Exception as e:
                    logger.exception(f"Error processing event: {e}")
                    yield {
                        "data": json.dumps({"error": str(e)}),
                        "event": "error"
                    }

                # Small delay
                await asyncio.sleep(0.01)

        except Exception as e:
            logger.exception(f"Stream error for task {task_id}: {e}")
            yield {
                "data": json.dumps({
                    "error": str(e),
                    "task_id": task_id
                }),
                "event": "error"
            }
        finally:
            logger.info(f"Stream closed for task {task_id}")

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )

@app.post("/api/analyze")
async def analyze_alert(request: Request):
    """
    Accept alert file upload and start analysis.
    Returns task_id for client to use with /api/stream/{task_id}
    """
    form = await request.form()
    alert_file = form.get("alert")

    if not alert_file:
        raise HTTPException(status_code=400, detail="No alert file provided")

    # Read alert XML
    alert_content = await alert_file.read()
    alert_text = alert_content.decode("utf-8")

    # Send to orchestrator and get task ID
    orchestrator_url = "http://localhost:10000"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{orchestrator_url}/analyze",
            json={"alert_text": alert_text}
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to create analysis task"
            )

        data = response.json()
        task_id = data.get("task_id")

    return {
        "task_id": task_id,
        "stream_url": f"/api/stream/{task_id}"
    }

@app.get("/")
async def index():
    """Serve frontend HTML"""
    return FileResponse("frontend/templates/index.html")

# Mount static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
```

---

## 4. Frontend JavaScript Implementation

### 4.1 Progress Timeline Component

```javascript
// frontend/static/js/progress-timeline.js

/**
 * ProgressTimeline - Stream real-time analysis progress to user
 *
 * Usage:
 *   const timeline = new ProgressTimeline('container-id');
 *   timeline.connectToTask('task-123');
 */
class ProgressTimeline {
    constructor(containerId) {
        this.containerId = containerId;
        this.container = document.getElementById(containerId);
        this.steps = [];
        this.startTime = null;
        this.eventSource = null;
        this.taskId = null;
        this.isConnected = false;

        this.setupUI();
    }

    setupUI() {
        """Set up initial HTML structure"""
        this.container.innerHTML = `
            <div class="timeline-container">
                <div class="timeline-header">
                    <div class="timeline-title">Analysis in Progress</div>
                    <div class="timeline-timer">
                        <span class="timer-icon">⏱</span>
                        <span class="elapsed-time">0s</span>
                    </div>
                </div>
                <div class="timeline-steps" id="steps-container"></div>
                <div class="timeline-status" id="status-container"></div>
            </div>
        `;

        // Start timer
        this.startTime = Date.now();
        this.updateTimer();
    }

    updateTimer() {
        """Update elapsed time display"""
        if (!this.startTime) return;

        const elapsed = Math.floor((Date.now() - this.startTime) / 1000);
        const timerEl = this.container.querySelector('.elapsed-time');
        if (timerEl) {
            timerEl.textContent = `${elapsed}s`;
        }

        setTimeout(() => this.updateTimer(), 1000);
    }

    connectToTask(taskId) {
        """Connect EventSource to stream task events"""
        this.taskId = taskId;
        const streamUrl = `/api/stream/${taskId}`;

        logger.info(`Connecting to stream: ${streamUrl}`);

        // Use native EventSource
        this.eventSource = new EventSource(streamUrl);

        // Handle progress events
        this.eventSource.addEventListener('progress', (event) => {
            const data = JSON.parse(event.data);
            this.handleProgressEvent(data);
        });

        // Handle completion
        this.eventSource.addEventListener('complete', (event) => {
            const data = JSON.parse(event.data);
            this.handleCompleteEvent(data);
            this.eventSource.close();
            this.isConnected = false;
        });

        // Handle errors
        this.eventSource.addEventListener('error', (event) => {
            if (this.eventSource.readyState === EventSource.CLOSED) {
                logger.info('Stream closed normally');
            } else {
                logger.error('Stream error - browser will reconnect automatically');
                this.showStatus('Connection lost. Reconnecting...', 'warning');
            }
        });

        // Handle generic message events
        this.eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.metadata && data.metadata.event_type === 'tool_start') {
                this.addStep({
                    title: data.metadata.tool_name || data.message,
                    description: data.message
                });
            }
        };

        this.isConnected = true;
        this.showStatus('Connected, waiting for updates...', 'info');
    }

    handleProgressEvent(data) {
        """Process progress update from stream"""
        const { message, metadata, state } = data;

        if (metadata) {
            const { event_type, tool_name, step, total } = metadata;

            if (event_type === 'tool_start') {
                this.addStep({
                    title: tool_name || 'Unknown Tool',
                    description: message,
                    totalSteps: total
                });
            } else if (event_type === 'tool_progress') {
                // Update current step progress
                const currentStep = this.steps[this.steps.length - 1];
                if (currentStep) {
                    currentStep.progress = (step / total) * 100;
                    this.renderSteps();
                }
            } else if (event_type === 'tool_complete') {
                // Mark step complete
                const currentStep = this.steps[this.steps.length - 1];
                if (currentStep) {
                    currentStep.status = 'completed';
                    currentStep.duration = Date.now() - currentStep.startTime;
                    this.renderSteps();
                }
            } else if (event_type === 'tool_error') {
                // Mark step failed
                const currentStep = this.steps[this.steps.length - 1];
                if (currentStep) {
                    currentStep.status = 'failed';
                    currentStep.error = message;
                    this.renderSteps();
                }
            }
        } else if (message) {
            this.showStatus(message, state === 'working' ? 'info' : 'warning');
        }
    }

    handleCompleteEvent(data) {
        """Process task completion"""
        this.showStatus('Analysis complete!', 'success');

        // Update final step
        if (this.steps.length > 0) {
            const lastStep = this.steps[this.steps.length - 1];
            lastStep.status = 'completed';
            lastStep.duration = Date.now() - lastStep.startTime;
            this.renderSteps();
        }

        // Show result summary
        if (data.metadata) {
            setTimeout(() => {
                this.showResult(data.metadata);
            }, 500);
        }
    }

    addStep(options = {}) {
        """Add new step to timeline"""
        const step = {
            id: this.steps.length,
            title: options.title || 'Step',
            description: options.description || '',
            status: 'in-progress',
            progress: 0,
            startTime: Date.now(),
            totalSteps: options.totalSteps || 1
        };

        this.steps.push(step);
        this.renderSteps();
    }

    renderSteps() {
        """Render all steps to DOM"""
        const container = document.getElementById('steps-container');
        container.innerHTML = this.steps.map((step, i) => `
            <div class="timeline-step ${step.status}">
                <div class="step-indicator">
                    <div class="step-number">${i + 1}</div>
                    <div class="step-connector"></div>
                </div>
                <div class="step-content">
                    <div class="step-title">${step.title}</div>
                    <div class="step-description">${step.description}</div>
                    ${step.progress > 0 && step.progress < 100 ? `
                        <div class="step-progress-bar">
                            <progress value="${step.progress}" max="100"></progress>
                            <span class="progress-text">${Math.round(step.progress)}%</span>
                        </div>
                    ` : ''}
                    ${step.status === 'completed' ? `
                        <div class="step-time">${(step.duration / 1000).toFixed(1)}s</div>
                    ` : ''}
                    ${step.status === 'failed' && step.error ? `
                        <div class="step-error">${step.error}</div>
                    ` : ''}
                </div>
            </div>
        `).join('');
    }

    showStatus(message, type = 'info') {
        """Show status message"""
        const container = document.getElementById('status-container');
        container.innerHTML = `
            <div class="status-message status-${type}">
                ${this.getStatusIcon(type)} ${message}
            </div>
        `;
    }

    showResult(result) {
        """Show final result"""
        const container = document.getElementById('status-container');
        container.innerHTML = `
            <div class="result-box">
                <h3>Analysis Result</h3>
                <pre>${JSON.stringify(result, null, 2)}</pre>
            </div>
        `;
    }

    getStatusIcon(type) {
        const icons = {
            'info': '📋',
            'warning': '⚠️',
            'success': '✅',
            'error': '❌'
        };
        return icons[type] || '•';
    }

    disconnect() {
        """Close stream connection"""
        if (this.eventSource) {
            this.eventSource.close();
            this.isConnected = false;
        }
    }
}

// Logger utility
const logger = {
    info: (msg) => console.log(`[INFO] ${msg}`),
    debug: (msg) => console.debug(`[DEBUG] ${msg}`),
    error: (msg) => console.error(`[ERROR] ${msg}`)
};
```

### 4.2 Tailwind CSS Styling

```css
/* frontend/static/css/timeline.css */

/* Timeline Container */
.timeline-container {
    @apply max-w-2xl mx-auto p-6 bg-white rounded-lg shadow-lg;
}

.timeline-header {
    @apply flex justify-between items-center mb-6 pb-4 border-b-2 border-gray-200;
}

.timeline-title {
    @apply text-2xl font-bold text-gray-900;
}

.timeline-timer {
    @apply flex items-center gap-2 text-gray-600;
}

.timer-icon {
    @apply text-xl;
}

/* Steps Container */
.timeline-steps {
    @apply space-y-4 mb-6;
}

.timeline-step {
    @apply flex gap-4 p-4 rounded-lg border-l-4 transition-all duration-300;
}

.timeline-step.in-progress {
    @apply bg-blue-50 border-l-blue-500;
}

.timeline-step.completed {
    @apply bg-green-50 border-l-green-500;
}

.timeline-step.failed {
    @apply bg-red-50 border-l-red-500;
}

/* Step Indicator */
.step-indicator {
    @apply flex flex-col items-center;
}

.step-number {
    @apply flex items-center justify-center w-10 h-10 rounded-full font-bold text-white bg-gray-400;
}

.timeline-step.in-progress .step-number {
    @apply bg-blue-500 animate-pulse;
}

.timeline-step.completed .step-number {
    @apply bg-green-500;
}

.timeline-step.failed .step-number {
    @apply bg-red-500;
}

.step-connector {
    @apply flex-1 w-1 bg-gray-200 my-2 last-child:hidden;
}

/* Step Content */
.step-content {
    @apply flex-1;
}

.step-title {
    @apply text-lg font-semibold text-gray-900 mb-1;
}

.step-description {
    @apply text-sm text-gray-600 mb-3;
}

/* Progress Bar */
.step-progress-bar {
    @apply flex items-center gap-2 my-2;
}

.step-progress-bar progress {
    @apply flex-1 h-2 rounded-full;
    accent-color: #3b82f6;
}

.progress-text {
    @apply text-xs text-gray-500 min-w-max;
}

.step-time {
    @apply text-xs text-gray-400 mt-2;
}

.step-error {
    @apply text-xs text-red-600 mt-2 font-medium;
}

/* Status Message */
.timeline-status {
    @apply mt-6;
}

.status-message {
    @apply p-4 rounded-lg text-sm font-medium flex items-center gap-2;
}

.status-info {
    @apply bg-blue-100 text-blue-800 border border-blue-300;
}

.status-warning {
    @apply bg-yellow-100 text-yellow-800 border border-yellow-300;
}

.status-success {
    @apply bg-green-100 text-green-800 border border-green-300;
}

.status-error {
    @apply bg-red-100 text-red-800 border border-red-300;
}

/* Result Box */
.result-box {
    @apply p-4 bg-gray-50 rounded-lg border border-gray-200;
}

.result-box h3 {
    @apply font-bold text-gray-900 mb-3;
}

.result-box pre {
    @apply text-xs bg-white p-3 rounded border border-gray-200 overflow-auto max-h-96;
}
```

### 4.3 HTML Integration

```html
<!-- frontend/templates/index.html -->

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMARTS Alert Analyzer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="/static/css/timeline.css">
</head>
<body class="bg-gray-100">
    <div class="min-h-screen py-12">
        <!-- Upload Section -->
        <div id="upload-section" class="max-w-2xl mx-auto mb-8">
            <div class="bg-white rounded-lg shadow-lg p-8">
                <h1 class="text-3xl font-bold mb-6">SMARTS Alert Analyzer</h1>

                <div id="upload-form" class="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center cursor-pointer hover:border-blue-400 transition">
                    <svg class="mx-auto h-12 w-12 text-gray-400 mb-4" stroke="currentColor" fill="none" viewBox="0 0 48 48">
                        <path d="M28 8H12a4 4 0 00-4 4v20a4 4 0 004 4h24a4 4 0 004-4V20m-14-8v8m-4 12h8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                    <p class="text-gray-600 font-medium">Click to upload or drag and drop</p>
                    <p class="text-gray-400 text-sm">XML Alert File</p>
                    <input type="file" id="alert-file" accept=".xml" style="display: none;">
                </div>

                <button id="analyze-btn" class="mt-6 w-full bg-blue-600 text-white font-bold py-3 rounded-lg hover:bg-blue-700 transition disabled:opacity-50" disabled>
                    Start Analysis
                </button>
            </div>
        </div>

        <!-- Timeline Section -->
        <div id="timeline-section" style="display: none;">
            <div id="timeline-container"></div>
        </div>
    </div>

    <script src="/static/js/progress-timeline.js"></script>
    <script>
        // File upload handling
        const uploadForm = document.getElementById('upload-form');
        const alertFile = document.getElementById('alert-file');
        const analyzeBtn = document.getElementById('analyze-btn');

        uploadForm.addEventListener('click', () => alertFile.click());
        uploadForm.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadForm.classList.add('border-blue-400');
        });
        uploadForm.addEventListener('dragleave', () => {
            uploadForm.classList.remove('border-blue-400');
        });
        uploadForm.addEventListener('drop', (e) => {
            e.preventDefault();
            alertFile.files = e.dataTransfer.files;
            analyzeBtn.disabled = false;
        });

        alertFile.addEventListener('change', () => {
            analyzeBtn.disabled = false;
        });

        // Analysis workflow
        analyzeBtn.addEventListener('click', async () => {
            const file = alertFile.files[0];
            if (!file) return;

            // Upload alert and get task ID
            const formData = new FormData();
            formData.append('alert', file);

            try {
                const response = await fetch('/api/analyze', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();
                const taskId = data.task_id;

                // Show timeline
                document.getElementById('upload-section').style.display = 'none';
                document.getElementById('timeline-section').style.display = 'block';

                // Start streaming
                const timeline = new ProgressTimeline('timeline-container');
                timeline.connectToTask(taskId);

            } catch (error) {
                alert(`Error: ${error.message}`);
            }
        });
    </script>
</body>
</html>
```

---

## Configuration & Deployment

### 5.1 Environment Configuration

```bash
# .env

# A2A Agents
INSIDER_TRADING_AGENT_URL=http://localhost:10001
WASH_TRADE_AGENT_URL=http://localhost:10002
ORCHESTRATOR_URL=http://localhost:10000

# LLM
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Logging
LOG_LEVEL=INFO

# SSE Settings
SSE_HEARTBEAT_INTERVAL=20  # seconds
SSE_TIMEOUT=600  # 10 minutes
SSE_MAX_CONCURRENT=1000
```

### 5.2 Docker Compose

```yaml
# docker-compose.yml

version: '3.8'

services:
  insider-trading-agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
    ports:
      - "10001:10001"
    environment:
      AGENT_TYPE: insider_trading
      PORT: 10001
      LLM_PROVIDER: openai
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    volumes:
      - ./test_data:/app/test_data

  wash-trade-agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
    ports:
      - "10002:10002"
    environment:
      AGENT_TYPE: wash_trade
      PORT: 10002
      LLM_PROVIDER: openai
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    volumes:
      - ./test_data:/app/test_data

  orchestrator:
    build:
      context: .
      dockerfile: Dockerfile.agent
    ports:
      - "10000:10000"
    environment:
      AGENT_TYPE: orchestrator
      PORT: 10000
      INSIDER_TRADING_URL: http://insider-trading-agent:10001
      WASH_TRADE_URL: http://wash-trade-agent:10002
    depends_on:
      - insider-trading-agent
      - wash-trade-agent

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "8080:8080"
    environment:
      ORCHESTRATOR_URL: http://orchestrator:10000
    depends_on:
      - orchestrator
```

---

These examples provide production-ready implementations for each layer of your streaming architecture. Adapt and extend as needed for your specific use cases.
