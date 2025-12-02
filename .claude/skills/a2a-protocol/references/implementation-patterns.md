# A2A Protocol: Implementation Patterns

## Table of Contents
1. [FastAPI Server Pattern](#fastapi-server-pattern)
2. [Robust Client Pattern](#robust-client-pattern)
3. [LangGraph Integration](#langgraph-integration)
4. [Circuit Breaker Pattern](#circuit-breaker-pattern)
5. [Testing Patterns](#testing-patterns)

## FastAPI Server Pattern

### Minimal A2A Server

```python
from fastapi import FastAPI, Header, HTTPException
from typing import Dict, Any
import os

app = FastAPI(title="A2A Agent")

AGENT_CARD = {
    "id": "agent/example/v1",
    "name": "Example Agent",
    "description": "Processes requests",
    "endpoint": os.getenv("AGENT_ENDPOINT", "http://localhost:8000/a2a"),
    "version": "1.0.0",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "longRunningOperations": False
    },
    "security": {
        "apiKey": {"name": "x-api-key", "in": "header"}
    },
    "skills": [
        {
            "id": "process_request",
            "name": "Process Request",
            "description": "Processes incoming requests",
            "inputs": ["text"],
            "outputs": ["result"]
        }
    ]
}

@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    """A2A Agent Card Discovery"""
    return AGENT_CARD

@app.post("/a2a/message/send")
async def send_message(request: Dict[str, Any], x_api_key: str = Header(...)):
    """Handle A2A message/send RPC call"""

    # Verify authentication
    if x_api_key != os.getenv("AGENT_API_KEY", "test-key"):
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        # Extract message
        message = request["params"]["message"]
        user_text = message["parts"][0]["text"]

        # Process
        result = await process(user_text)

        # Return A2A response
        return {
            "jsonrpc": "2.0",
            "result": {
                "artifacts": [
                    {
                        "id": "art_1",
                        "parts": [{"kind": "text", "text": result}]
                    }
                ]
            }
        }

    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,
                "message": "Internal error",
                "data": {"details": str(e)}
            }
        }

async def process(text: str) -> str:
    """Process the incoming request"""
    return f"Processed: {text}"
```

## Robust Client Pattern

### A2A Client with Retry Logic

```python
import httpx
import logging
from typing import Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class A2AClient:
    """Robust A2A client with automatic retry"""

    def __init__(self, endpoint: str, api_key: str, timeout: float = 30.0):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout
        self.agent_card_cache: Optional[Dict] = None
        self.http_client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.http_client.aclose()

    async def get_agent_card(self, use_cache: bool = True) -> Dict[str, Any]:
        """Get agent's card with optional caching"""
        if use_cache and self.agent_card_cache:
            return self.agent_card_cache

        response = await self.http_client.get(
            f"{self.endpoint}/.well-known/agent-card.json"
        )
        response.raise_for_status()
        self.agent_card_cache = response.json()
        return self.agent_card_cache

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=True
    )
    async def send_message(self, text: str,
                          extra_data: Optional[Dict] = None) -> Dict[str, Any]:
        """Send message with automatic retry"""

        # Build message
        parts = [{"kind": "text", "text": text}]
        if extra_data:
            parts.append({
                "kind": "data",
                "mimeType": "application/json",
                "data": extra_data
            })

        request_body = {
            "jsonrpc": "2.0",
            "id": "msg_1",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": parts
                }
            }
        }

        try:
            response = await self.http_client.post(
                f"{self.endpoint}/a2a/message/send",
                json=request_body,
                headers={"x-api-key": self.api_key}
            )
            response.raise_for_status()
            result = response.json()

            # Handle RPC errors
            if "error" in result:
                raise RuntimeError(f"RPC Error: {result['error']['message']}")

            return result["result"]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise PermissionError("Invalid API key")
            elif e.response.status_code == 404:
                raise ValueError("Agent endpoint not found")
            elif e.response.status_code == 429:
                # Rate limited - will retry
                logger.warning("Rate limited, retrying...")
                raise
            elif 500 <= e.response.status_code < 600:
                # Server error - will retry
                logger.warning(f"Server error {e.response.status_code}, retrying...")
                raise
            else:
                raise

# Usage
async def example():
    async with A2AClient(
        endpoint="http://localhost:8000/a2a",
        api_key="test-key"
    ) as client:
        # Get agent capabilities
        card = await client.get_agent_card()
        print(f"Agent: {card['name']}")

        # Send message
        result = await client.send_message("Hello, agent!")
        print(f"Result: {result}")
```

## LangGraph Integration

### LangGraph Agent with A2A Support

```python
from typing import List, TypedDict
from langgraph.graph import StateGraph, START, END
import anthropic

class Message(TypedDict):
    role: str  # "user" or "assistant"
    content: str

class AgentState(TypedDict):
    """State must have 'messages' key for A2A compatibility"""
    messages: List[Message]

def process_user_message(state: AgentState):
    """Process incoming message using Claude API"""

    client = anthropic.Anthropic()

    # Build conversation for Claude
    messages_for_api = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in state["messages"]
    ]

    # Call Claude
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        system="You are a helpful assistant.",
        messages=messages_for_api
    )

    assistant_message = response.content[0].text

    # Return updated state
    return {
        "messages": state["messages"] + [
            {"role": "assistant", "content": assistant_message}
        ]
    }

# Build the graph
graph_builder = StateGraph(AgentState)
graph_builder.add_node("process", process_user_message)
graph_builder.add_edge(START, "process")
graph_builder.add_edge("process", END)

# Compile
graph = graph_builder.compile()

# When deployed to LangGraph Platform:
# - POST /a2a/{assistant_id}/message/send
# - GET /.well-known/agent-card.json
# are automatically available
```

### Multi-Agent Orchestration

```python
import asyncio
from typing import List, Dict, Any

async def orchestrate_analysis(data: dict, registry: AgentRegistry):
    """Coordinate multiple specialist agents"""

    # Find specialists
    compliance_agent = registry.find_agent_by_skill("compliance_check")
    risk_agent = registry.find_agent_by_skill("risk_analysis")

    # Call specialists in parallel
    async def call_compliance():
        client = A2AClient(compliance_agent.endpoint, api_key="...")
        return await client.send_message(
            "Analyze for compliance",
            extra_data=data
        )

    async def call_risk():
        client = A2AClient(risk_agent.endpoint, api_key="...")
        return await client.send_message(
            "Assess risk level",
            extra_data=data
        )

    # Execute in parallel
    compliance, risk = await asyncio.gather(
        call_compliance(),
        call_risk()
    )

    # Aggregate results
    return {
        "compliance": compliance,
        "risk": risk,
        "final_decision": make_decision(compliance, risk)
    }
```

## Circuit Breaker Pattern

### Resilient Agent Calls

```python
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"  # Working normally
    OPEN = "open"      # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5  # Failures before opening
    recovery_timeout: int = 60  # Seconds before half-open
    success_threshold: int = 2  # Successes to close

class ResilientA2AClient:
    """A2A client with circuit breaker"""

    def __init__(self, endpoint: str, api_key: str,
                 config: CircuitBreakerConfig = None):
        self.endpoint = endpoint
        self.api_key = api_key
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.opened_time = None

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows request"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if enough time passed to try recovery
            if self.opened_time:
                elapsed = (datetime.now() - self.opened_time).total_seconds()
                if elapsed >= self.config.recovery_timeout:
                    logger.info("Circuit breaker entering half-open")
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return True  # Allow test request

        return False

    def _record_success(self):
        """Record successful request"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                logger.info("Circuit breaker closed (recovered)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0

    def _record_failure(self):
        """Record failed request"""
        if self.state == CircuitState.HALF_OPEN:
            logger.warning("Circuit breaker reopened")
            self.state = CircuitState.OPEN
            self.opened_time = datetime.now()

        elif self.state == CircuitState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.config.failure_threshold:
                logger.error(f"Circuit breaker opened (failures: {self.failure_count})")
                self.state = CircuitState.OPEN
                self.opened_time = datetime.now()

    async def send_message(self, text: str):
        """Send message with circuit breaker protection"""
        if not self._check_circuit_breaker():
            raise RuntimeError(f"Circuit breaker is {self.state.value}")

        try:
            # Make the call
            result = await self._do_send_message(text)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise
```

## Testing Patterns

### Unit Test for A2A Server

```python
import pytest
from fastapi.testclient import TestClient
from your_agent import app

@pytest.fixture
def client():
    return TestClient(app)

def test_agent_card(client):
    """Test agent card is returned"""
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    card = response.json()
    assert card["name"] == "Example Agent"
    assert "skills" in card

def test_send_message_success(client):
    """Test successful message/send"""
    request = {
        "jsonrpc": "2.0",
        "id": "msg_1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "Hello"}]
            }
        }
    }

    response = client.post(
        "/a2a/message/send",
        json=request,
        headers={"x-api-key": "test-key"}
    )

    assert response.status_code == 200
    result = response.json()
    assert "result" in result
    assert "artifacts" in result["result"]

def test_send_message_auth_failure(client):
    """Test authentication failure"""
    request = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "Hello"}]
            }
        }
    }

    response = client.post(
        "/a2a/message/send",
        json=request,
        headers={"x-api-key": "wrong-key"}
    )

    assert response.status_code == 401
```

### Integration Test for Multi-Agent Workflow

```python
import pytest
import asyncio
from your_agents import orchestrate_analysis, AgentRegistry

@pytest.mark.asyncio
async def test_multi_agent_workflow():
    """Test multi-agent orchestration"""

    # Setup registry with test agents
    registry = AgentRegistry()
    await registry.add_agent("http://localhost:8001/a2a")  # Compliance
    await registry.add_agent("http://localhost:8002/a2a")  # Risk

    # Run orchestration
    test_data = {"trade_id": "T123", "amount": 50000}
    result = await orchestrate_analysis(test_data, registry)

    # Verify results
    assert "compliance" in result
    assert "risk" in result
    assert "final_decision" in result
```

## Best Practices

1. **Always use async/await** - A2A calls are I/O-bound
2. **Implement retry logic** - Network failures happen
3. **Cache agent cards** - Don't fetch on every request
4. **Use circuit breakers** - Protect against cascading failures
5. **Log all inter-agent calls** - Essential for debugging
6. **Set appropriate timeouts** - 30s recommended default
7. **Validate inputs** - Reject malformed A2A messages early
8. **Monitor latency** - Track p50, p95, p99 response times
