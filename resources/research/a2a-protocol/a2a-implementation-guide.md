# A2A Protocol: Implementation Quick Reference & Code Examples

## Quick Start Guide

### 1-Minute Overview

```python
# A2A in 60 seconds:

# 1. Expose your agent via A2A (LangGraph does this automatically)
@app.post("/.well-known/agent-card.json")
async def get_agent_card():
    return {
        "id": "agent/analyzer/v1",
        "name": "Alert Analyzer",
        "endpoint": "https://api.example.com/a2a",
        "skills": [...]
    }

# 2. Handle messages (JSON-RPC 2.0)
@app.post("/a2a/message/send")
async def receive_message(request: dict):
    user_message = request["params"]["message"]["parts"][0]["text"]
    result = await analyze(user_message)
    return {"result": {"artifacts": [...]}}

# 3. Other agents discover and call you
client = A2AClient(endpoint="https://api.example.com/a2a")
response = await client.send_message({
    "role": "user",
    "parts": [{"kind": "text", "text": "Analyze this alert..."}]
})
```

## Code Template Library

### Template 1: Minimal A2A Server (FastAPI)

```python
# /workspaces/alerts/agents/minimal_a2a_server.py

from fastapi import FastAPI, Header, HTTPException
from contextlib import asynccontextmanager
import json
import os
from typing import Dict, Any

app = FastAPI(title="A2A Agent")

# Store agent metadata
AGENT_CARD = {
    "id": "agent/example/v1",
    "name": "Example Agent",
    "description": "Does example tasks",
    "endpoint": os.getenv("AGENT_ENDPOINT", "http://localhost:8000/a2a"),
    "version": "1.0.0",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "longRunningOperations": False
    },
    "security": {
        "apiKey": {
            "name": "x-api-key",
            "in": "header"
        }
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
                        "parts": [
                            {
                                "kind": "text",
                                "text": result
                            }
                        ]
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Template 2: A2A Client with Automatic Retry

```python
# /workspaces/alerts/agents/a2a_client.py

import httpx
import asyncio
import logging
from typing import Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class A2AClient:
    """Robust A2A client with automatic retry and caching"""

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

    async def stream_message(self, text: str):
        """Stream message with SSE"""
        request_body = {
            "jsonrpc": "2.0",
            "id": "msg_1",
            "method": "message/stream",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": text}]
                }
            }
        }

        async with self.http_client.stream(
            "POST",
            f"{self.endpoint}/a2a/message/stream",
            json=request_body,
            headers={"x-api-key": self.api_key}
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    yield json.loads(line[6:])

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

if __name__ == "__main__":
    asyncio.run(example())
```

### Template 3: LangGraph A2A Integration

```python
# /workspaces/alerts/agents/langgraph_a2a_agent.py

from typing import Any, Dict, List, TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
import anthropic
import json

class Message(TypedDict):
    role: str  # "user" or "assistant"
    content: str

class AgentState(TypedDict):
    """State must have 'messages' key for A2A compatibility"""
    messages: List[Message]
    task_id: str

def process_user_message(state: AgentState) -> Dict[str, Any]:
    """
    Process incoming message using Claude API.

    This function will be called:
    - When deployed to LangGraph Platform (via A2A endpoint)
    - When called directly via graph.invoke()
    """

    client = anthropic.Anthropic()

    # Get the latest user message
    latest_message = state["messages"][-1]

    # Build conversation for Claude
    messages_for_api = [
        {
            "role": msg["role"],
            "content": msg["content"]
        }
        for msg in state["messages"]
    ]

    # Call Claude
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        system="You are a helpful assistant. Be concise and direct.",
        messages=messages_for_api
    )

    assistant_message = response.content[0].text

    # Return updated state (LangGraph automatically handles A2A conversion)
    return {
        "messages": state["messages"] + [
            {
                "role": "assistant",
                "content": assistant_message
            }
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
# - POST /a2a/{assistant_id}/message/stream
# - GET /.well-known/agent-card.json?assistant_id={assistant_id}
# are automatically available

# Local testing
if __name__ == "__main__":
    initial_state = {
        "messages": [
            {"role": "user", "content": "Hello, what is 2 + 2?"}
        ],
        "task_id": "task_123"
    }

    result = graph.invoke(initial_state)
    print("Assistant:", result["messages"][-1]["content"])
```

### Template 4: Agent Discovery & Routing

```python
# /workspaces/alerts/agents/agent_registry.py

import httpx
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class AgentInfo:
    id: str
    name: str
    description: str
    endpoint: str
    skills: List[str]

class AgentRegistry:
    """Discover and manage available A2A agents"""

    def __init__(self, registry_url: Optional[str] = None):
        self.registry_url = registry_url
        self.agents: Dict[str, AgentInfo] = {}
        self.http_client = httpx.AsyncClient(timeout=10.0)

    async def discover_agents(self):
        """Fetch agents from registry"""
        if not self.registry_url:
            logger.warning("No registry configured")
            return

        try:
            response = await self.http_client.get(self.registry_url)
            response.raise_for_status()
            agent_list = response.json()

            for agent_data in agent_list:
                agent_info = AgentInfo(
                    id=agent_data["id"],
                    name=agent_data["name"],
                    description=agent_data.get("description", ""),
                    endpoint=agent_data["endpoint"],
                    skills=agent_data.get("skills", [])
                )
                self.agents[agent_info.id] = agent_info
                logger.info(f"Discovered agent: {agent_info.name}")

        except Exception as e:
            logger.error(f"Failed to discover agents: {e}")

    async def add_agent(self, endpoint: str):
        """Discover a single agent from its endpoint"""
        try:
            response = await self.http_client.get(
                f"{endpoint}/.well-known/agent-card.json"
            )
            response.raise_for_status()
            card = response.json()

            agent_info = AgentInfo(
                id=card["id"],
                name=card["name"],
                description=card.get("description", ""),
                endpoint=endpoint,
                skills=[skill["name"] for skill in card.get("skills", [])]
            )
            self.agents[agent_info.id] = agent_info
            logger.info(f"Added agent: {agent_info.name}")

        except Exception as e:
            logger.error(f"Failed to add agent {endpoint}: {e}")

    def find_agent_by_skill(self, skill_name: str) -> Optional[AgentInfo]:
        """Find an agent with specific skill"""
        for agent in self.agents.values():
            if skill_name.lower() in [s.lower() for s in agent.skills]:
                return agent
        return None

    def list_agents(self) -> List[AgentInfo]:
        """List all discovered agents"""
        return list(self.agents.values())

# Usage
async def example():
    registry = AgentRegistry(
        registry_url="https://registry.example.com/agents"
    )

    # Discover all agents
    await registry.discover_agents()

    # Or add specific agent
    await registry.add_agent("http://localhost:8001/a2a")

    # Find agent for a task
    flight_agent = registry.find_agent_by_skill("book_flight")
    if flight_agent:
        print(f"Found agent: {flight_agent.name} at {flight_agent.endpoint}")

    # List all
    for agent in registry.list_agents():
        print(f"{agent.name}: {agent.skills}")
```

### Template 5: Error Handling & Circuit Breaker

```python
# /workspaces/alerts/agents/resilient_a2a.py

import httpx
import asyncio
import time
import logging
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CircuitBreakerState(Enum):
    CLOSED = "closed"  # Working normally
    OPEN = "open"      # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5  # Failures before opening
    recovery_timeout: int = 60  # Seconds before half-open
    success_threshold: int = 2  # Successes in half-open before closing

@dataclass
class CircuitBreakerState:
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    opened_time: Optional[datetime] = None

class ResilientA2AClient:
    """A2A client with circuit breaker pattern"""

    def __init__(self, endpoint: str, api_key: str,
                 config: CircuitBreakerConfig = None):
        self.endpoint = endpoint
        self.api_key = api_key
        self.config = config or CircuitBreakerConfig()
        self.cb_state = CircuitBreakerState()
        self.http_client = httpx.AsyncClient(timeout=30.0)

    def _check_circuit_breaker(self):
        """Check if circuit breaker allows request"""
        if self.cb_state.state == CircuitBreakerState.CLOSED:
            return True  # Normal operation

        if self.cb_state.state == CircuitBreakerState.OPEN:
            # Check if enough time has passed to try recovery
            if self.cb_state.opened_time:
                elapsed = (datetime.now() - self.cb_state.opened_time).total_seconds()
                if elapsed >= self.config.recovery_timeout:
                    logger.info(f"Circuit breaker entering half-open (recovery)")
                    self.cb_state.state = CircuitBreakerState.HALF_OPEN
                    self.cb_state.success_count = 0
                    return True
            return False  # Still open, reject

        if self.cb_state.state == CircuitBreakerState.HALF_OPEN:
            return True  # Allow test request

        return False

    def _record_success(self):
        """Record successful request"""
        if self.cb_state.state == CircuitBreakerState.CLOSED:
            self.cb_state.failure_count = 0

        elif self.cb_state.state == CircuitBreakerState.HALF_OPEN:
            self.cb_state.success_count += 1
            if self.cb_state.success_count >= self.config.success_threshold:
                logger.info("Circuit breaker closed (recovered)")
                self.cb_state.state = CircuitBreakerState.CLOSED
                self.cb_state.failure_count = 0
                self.cb_state.success_count = 0

    def _record_failure(self):
        """Record failed request"""
        self.cb_state.last_failure_time = datetime.now()

        if self.cb_state.state == CircuitBreakerState.HALF_OPEN:
            # Failure in half-open, back to open
            logger.warning("Circuit breaker reopened (recovery failed)")
            self.cb_state.state = CircuitBreakerState.OPEN
            self.cb_state.opened_time = datetime.now()
            self.cb_state.success_count = 0

        elif self.cb_state.state == CircuitBreakerState.CLOSED:
            self.cb_state.failure_count += 1
            if self.cb_state.failure_count >= self.config.failure_threshold:
                logger.error(f"Circuit breaker opened (failures: {self.cb_state.failure_count})")
                self.cb_state.state = CircuitBreakerState.OPEN
                self.cb_state.opened_time = datetime.now()

    async def send_message(self, text: str) -> Optional[Dict[str, Any]]:
        """Send message with circuit breaker protection"""

        if not self._check_circuit_breaker():
            raise RuntimeError(f"Circuit breaker is {self.cb_state.state.value}")

        try:
            response = await self.http_client.post(
                f"{self.endpoint}/a2a/message/send",
                json={
                    "jsonrpc": "2.0",
                    "id": "msg_1",
                    "method": "message/send",
                    "params": {
                        "message": {
                            "role": "user",
                            "parts": [{"kind": "text", "text": text}]
                        }
                    }
                },
                headers={"x-api-key": self.api_key}
            )

            response.raise_for_status()
            result = response.json()
            self._record_success()
            return result["result"]

        except Exception as e:
            self._record_failure()
            logger.error(f"Request failed: {e}")
            raise

# Usage
async def example():
    client = ResilientA2AClient(
        endpoint="http://localhost:8000/a2a",
        api_key="test-key",
        config=CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30
        )
    )

    for i in range(10):
        try:
            result = await client.send_message(f"Request {i}")
            print(f"Success: {result}")
        except Exception as e:
            print(f"Failed: {e}")

        await asyncio.sleep(5)
```

### Template 6: Testing A2A Agents

```python
# /workspaces/alerts/tests/test_a2a_agent.py

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from agents.a2a_client import A2AClient
from agents.agent_registry import AgentRegistry

class TestA2AClient:
    """Test A2A client functionality"""

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """Test successful message sending"""
        client = A2AClient(
            endpoint="http://localhost:8000",
            api_key="test-key"
        )

        # Mock the HTTP response
        with patch.object(client.http_client, 'post') as mock_post:
            mock_response = AsyncMock()
            mock_response.json.return_value = {
                "result": {
                    "artifacts": [{
                        "parts": [{"kind": "text", "text": "Response"}]
                    }]
                }
            }
            mock_post.return_value = mock_response

            result = await client.send_message("Test message")

            assert result is not None
            assert "artifacts" in result
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_card_caching(self):
        """Test Agent Card caching"""
        client = A2AClient(
            endpoint="http://localhost:8000",
            api_key="test-key"
        )

        card_data = {
            "id": "agent/test",
            "name": "Test Agent",
            "skills": []
        }

        with patch.object(client.http_client, 'get') as mock_get:
            mock_response = AsyncMock()
            mock_response.json.return_value = card_data
            mock_get.return_value = mock_response

            # First call
            result1 = await client.get_agent_card()
            assert result1 == card_data

            # Second call (should use cache)
            result2 = await client.get_agent_card()
            assert result2 == card_data

            # HTTP client should only be called once
            assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self):
        """Test automatic retry on transient errors"""
        client = A2AClient(
            endpoint="http://localhost:8000",
            api_key="test-key"
        )

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")

            mock_response = AsyncMock()
            mock_response.json.return_value = {"result": {"artifacts": []}}
            return mock_response

        with patch.object(client.http_client, 'post', side_effect=mock_post):
            result = await client.send_message("Test")
            assert call_count == 3  # Failed twice, succeeded on third

class TestAgentRegistry:
    """Test agent discovery and registry"""

    @pytest.mark.asyncio
    async def test_discover_single_agent(self):
        """Test discovering a single agent"""
        registry = AgentRegistry()

        agent_card = {
            "id": "agent/test",
            "name": "Test Agent",
            "description": "A test agent",
            "skills": [
                {"name": "process_data"},
                {"name": "analyze"}
            ]
        }

        with patch.object(registry.http_client, 'get') as mock_get:
            mock_response = AsyncMock()
            mock_response.json.return_value = agent_card
            mock_get.return_value = mock_response

            await registry.add_agent("http://test-agent:8000")

            assert "agent/test" in registry.agents
            agent = registry.agents["agent/test"]
            assert agent.name == "Test Agent"
            assert "process_data" in agent.skills

    @pytest.mark.asyncio
    async def test_find_agent_by_skill(self):
        """Test finding agent with specific skill"""
        registry = AgentRegistry()
        registry.agents = {
            "agent/flight": AgentInfo(
                id="agent/flight",
                name="Flight Agent",
                description="Books flights",
                endpoint="http://flight:8000",
                skills=["search_flights", "book_flight"]
            ),
            "agent/hotel": AgentInfo(
                id="agent/hotel",
                name="Hotel Agent",
                description="Books hotels",
                endpoint="http://hotel:8000",
                skills=["search_hotels", "book_hotel"]
            )
        }

        # Find flight booking agent
        agent = registry.find_agent_by_skill("book_flight")
        assert agent is not None
        assert agent.name == "Flight Agent"

        # Find non-existent skill
        agent = registry.find_agent_by_skill("nonexistent")
        assert agent is None
```

## Common Integration Patterns

### Pattern: Workflow with Multiple Agents

```python
async def travel_planning_workflow():
    """Orchestrate multiple agents for trip planning"""

    registry = AgentRegistry()
    await registry.discover_agents()

    # Step 1: Search flights
    flight_agent = registry.find_agent_by_skill("search_flights")
    flights = await send_to_agent(
        flight_agent,
        "Find NYC to Tokyo flights, March 10-17, budget $1500"
    )

    # Step 2: Search hotels (using flight data as context)
    hotel_agent = registry.find_agent_by_skill("search_hotels")
    hotels = await send_to_agent(
        hotel_agent,
        "Find hotels in Tokyo for March 10-17",
        context={"flight_cost": flights["estimated_cost"]}
    )

    # Step 3: Get activities
    tours_agent = registry.find_agent_by_skill("recommend_activities")
    activities = await send_to_agent(
        tours_agent,
        "Top 10 must-see activities in Tokyo"
    )

    return {
        "flights": flights,
        "hotels": hotels,
        "activities": activities,
        "total_cost": flights["cost"] + hotels["cost"]
    }
```

### Pattern: Streaming with Progress Updates

```python
async def stream_long_operation():
    """Stream message to see real-time progress"""

    client = A2AClient(
        endpoint="http://analysis-agent:8000",
        api_key="key"
    )

    async for event in client.stream_message(
        "Analyze 1 million records for anomalies"
    ):
        if "task_status" in event:
            print(f"Progress: {event['task_status']['progress']}%")
        elif "artifact" in event:
            print(f"Result chunk: {event['artifact']}")
```

### Pattern: Error Recovery with Fallback

```python
async def send_to_agent_with_fallback(primary_agent, fallback_agent, message):
    """Try primary agent, fall back to secondary on failure"""

    try:
        return await send_to_agent(primary_agent, message)
    except Exception as e:
        logger.warning(f"Primary agent failed: {e}, trying fallback...")
        try:
            return await send_to_agent(fallback_agent, message)
        except Exception as e:
            logger.error(f"Both agents failed: {e}")
            raise
```

## Performance Tuning

```python
# Connection pooling for multiple requests
limits = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20
)
client = httpx.AsyncClient(limits=limits)

# Use batch requests for efficiency
async def batch_queries(agent_endpoint, queries):
    """Send multiple queries concurrently"""
    tasks = [
        client.post(f"{agent_endpoint}/a2a/message/send", json=q)
        for q in queries
    ]
    return await asyncio.gather(*tasks)

# Implement exponential backoff
async def exponential_backoff(attempt: int, max_wait: int = 60):
    wait_time = min(2 ** attempt, max_wait)
    await asyncio.sleep(wait_time)
```

## Deployment Checklist

- [ ] Agent Card endpoint returns valid JSON with all required fields
- [ ] Security scheme in Agent Card matches actual implementation
- [ ] All endpoints are HTTPS (TLS 1.3+) in production
- [ ] API key or OAuth token validation on every request
- [ ] Proper error responses (RPC format) for all error cases
- [ ] Logging configured with request ID/trace context
- [ ] Rate limiting implemented and documented in Agent Card
- [ ] Agent Card cached (1 hour TTL) by clients
- [ ] Webhook URLs validated (SSRF protection)
- [ ] Connection pool tuned for expected load
- [ ] Monitoring and alerting configured
- [ ] Documentation updated with Agent Card and example requests
- [ ] Load testing completed
- [ ] Security testing completed (injection, auth bypass, etc.)
- [ ] Tested with official A2A Inspector tool

