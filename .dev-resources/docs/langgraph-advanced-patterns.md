# LangGraph Tool-Calling Agent: Advanced Patterns

**Document Date**: November 2024
**Focus**: Production patterns, edge cases, and optimization strategies

---

## Table of Contents
1. [Tool State Updates with Command](#tool-state-updates-with-command)
2. [Multiple Tool Invocation Patterns](#multiple-tool-invocation-patterns)
3. [Tool Chaining and Dependencies](#tool-chaining-and-dependencies)
4. [Error Recovery and Retries](#error-recovery-and-retries)
5. [Performance Optimization](#performance-optimization)
6. [Testing Patterns](#testing-patterns)
7. [Monitoring and Observability](#monitoring-and-observability)
8. [Common Pitfalls](#common-pitfalls)

---

## Tool State Updates with Command

### Pattern: Tools Updating Agent State Directly

Instead of tools just returning strings, they can update the agent state using `Command`:

```python
from langgraph.types import Command
from langchain_core.tools import tool, ToolRuntime
from typing import Annotated

def create_stateful_tools(llm_client):
    """Create tools that can update agent state."""

    @tool
    def store_insight(
        key: str,
        value: str,
        runtime: Annotated[ToolRuntime, "ToolRuntime"] = None
    ) -> Command:
        """Store an insight in agent state for later reference.

        This tool updates the agent state directly.
        """
        if not runtime:
            return Command(update={})

        # Use Command to update state
        return Command(
            update={
                "insights": {
                    key: value
                }
            }
        )

    @tool
    def get_stored_insights(
        runtime: Annotated[ToolRuntime, "ToolRuntime"] = None
    ) -> str:
        """Retrieve previously stored insights."""
        if not runtime:
            return "No insights stored"

        insights = runtime.state.get("insights", {})
        if not insights:
            return "No insights stored"

        return "\n".join([f"- {k}: {v}" for k, v in insights.items()])

    return [store_insight, get_stored_insights]
```

### Updated State Schema

```python
from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AdvancedAgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    insights: dict = {}  # Updated by tools
    analysis_count: int = 0  # Track analysis runs
    user_preferences: dict = {}  # Store user-specific settings
```

---

## Multiple Tool Invocation Patterns

### Pattern 1: Sequential Tool Execution

Tools are called one at a time, each seeing results of previous:

```python
def sequential_tools_node(state: AgentState):
    """Execute tools sequentially."""
    outputs = []
    last_message = state["messages"][-1]

    # Tools are called in order
    for tool_call in last_message.tool_calls:
        tool_result = tools_by_name[tool_call["name"]].invoke(tool_call["args"])
        outputs.append(ToolMessage(
            content=tool_result,
            name=tool_call["name"],
            tool_call_id=tool_call["id"],
        ))
        # Next tool call can see previous results
    return {"messages": outputs}
```

### Pattern 2: Parallel Tool Execution

Multiple tools execute concurrently:

```python
import concurrent.futures
from typing import List

def parallel_tools_node(state: AgentState):
    """Execute multiple tools in parallel."""
    outputs = []
    last_message = state["messages"][-1]

    def execute_tool(tool_call):
        tool_result = tools_by_name[tool_call["name"]].invoke(tool_call["args"])
        return ToolMessage(
            content=tool_result,
            name=tool_call["name"],
            tool_call_id=tool_call["id"],
        )

    # Execute tools in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(execute_tool, tc)
            for tc in last_message.tool_calls
        ]
        outputs = [f.result() for f in concurrent.futures.as_completed(futures)]

    return {"messages": outputs}
```

**Use Parallel When:**
- Tools have independent inputs
- Tools make external API calls (I/O bound)
- Latency is critical

**Use Sequential When:**
- Later tools depend on earlier results
- Tools share state
- Want deterministic execution order

### Pattern 3: Conditional Tool Selection

```python
def smart_tools_node(state: AgentState):
    """Execute only necessary tools based on content."""
    outputs = []
    last_message = state["messages"][-1]

    if not hasattr(last_message, 'tool_calls'):
        return {"messages": outputs}

    # Filter tool calls based on some logic
    important_tools = ['sentiment_analysis', 'entity_extraction']

    for tool_call in last_message.tool_calls:
        # Only run priority tools if in analyze mode
        if "analyze_mode" in state and tool_call["name"] not in important_tools:
            continue

        tool_result = tools_by_name[tool_call["name"]].invoke(tool_call["args"])
        outputs.append(ToolMessage(
            content=tool_result,
            name=tool_call["name"],
            tool_call_id=tool_call["id"],
        ))

    return {"messages": outputs}
```

---

## Tool Chaining and Dependencies

### Pattern: Tool Result Input to Next Tool

```python
def create_chained_tools(llm_client):
    """Tools that work in sequence with dependencies."""

    # Tool 1: Extract entities
    @tool
    def extract_entities(text: str) -> str:
        """Extract named entities from text."""
        prompt = f"Extract entities: {text}"
        result = llm_client.invoke(prompt)
        return result.content

    # Tool 2: Analyze entities (takes output of tool 1)
    @tool
    def analyze_entities(entities_text: str) -> str:
        """Analyze the extracted entities."""
        prompt = f"Analyze these entities and their relationships: {entities_text}"
        result = llm_client.invoke(prompt)
        return result.content

    # Tool 3: Generate report (takes output of tool 2)
    @tool
    def generate_report(analysis: str) -> str:
        """Generate a final report from analysis."""
        prompt = f"Create a concise report: {analysis}"
        result = llm_client.invoke(prompt)
        return result.content

    return [extract_entities, analyze_entities, generate_report]

# The LLM orchestrates the calling order based on dependencies
# by being prompted appropriately:
system_prompt = """You have tools for entity extraction, analysis, and reporting.
Use them in this order to analyze text:
1. First extract entities from the input text
2. Then analyze the entities using the previous output
3. Finally generate a report using the analysis"""
```

### Managing Tool Order

```python
def should_continue_with_order(state: AgentState) -> str:
    """Control tool execution order."""
    messages = state["messages"]

    # Check what tools have been called
    tool_calls_made = []
    for msg in messages:
        if hasattr(msg, 'tool_calls'):
            tool_calls_made.extend([tc['name'] for tc in msg.tool_calls])

    # Define required sequence
    required_sequence = ['extract_entities', 'analyze_entities', 'generate_report']

    # Check if sequence was followed
    if len(tool_calls_made) >= len(required_sequence):
        return "end"

    # Check if last tool called is in sequence
    if tool_calls_made and tool_calls_made[-1] not in required_sequence:
        return "continue"

    return "continue"
```

---

## Error Recovery and Retries

### Pattern 1: Tool-Level Error Handling

```python
from functools import wraps
import time

def with_retry(max_retries: int = 3, delay: float = 1.0):
    """Decorator to add retry logic to tools."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (2 ** attempt))  # Exponential backoff
                    continue
            # All retries failed
            return f"Error after {max_retries} attempts: {str(last_exception)}"
        return wrapper
    return decorator

@tool
@with_retry(max_retries=3)
def api_tool(query: str) -> str:
    """Tool that calls external API with retry logic."""
    # May fail, will retry automatically
    return call_external_api(query)
```

### Pattern 2: Agent-Level Error Handling

```python
from langchain_core.messages import AIMessage

def agent_node_with_fallback(state: AgentState, config: RunnableConfig):
    """Agent with fallback on error."""
    try:
        response = llm_with_tools.invoke(
            [SystemMessage("You are helpful")] + list(state["messages"]),
            config
        )
        return {"messages": [response]}
    except Exception as e:
        # Fallback: return simple message without tools
        fallback_response = AIMessage(
            content=f"I encountered an error but I'm still here to help. "
                    f"Could you rephrase your question?"
        )
        return {"messages": [fallback_response]}
```

### Pattern 3: Validation Before Tool Execution

```python
def tools_node_with_validation(state: AgentState):
    """Validate tool calls before execution."""
    outputs = []
    last_message = state["messages"][-1]

    if not hasattr(last_message, 'tool_calls'):
        return {"messages": outputs}

    for tool_call in last_message.tool_calls:
        # Validate tool exists
        if tool_call["name"] not in tools_by_name:
            outputs.append(ToolMessage(
                content=f"Error: Unknown tool '{tool_call['name']}'",
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            ))
            continue

        # Validate arguments
        try:
            tool = tools_by_name[tool_call["name"]]
            # Check required arguments
            result = tool.invoke(tool_call["args"])
            outputs.append(ToolMessage(
                content=result,
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            ))
        except TypeError as e:
            outputs.append(ToolMessage(
                content=f"Error: Invalid arguments - {str(e)}",
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            ))
        except Exception as e:
            outputs.append(ToolMessage(
                content=f"Error executing tool: {str(e)}",
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            ))

    return {"messages": outputs}
```

---

## Performance Optimization

### Pattern 1: Tool Caching

```python
from functools import lru_cache
import hashlib
import json

class CachedTool:
    """Tool with caching to avoid redundant LLM calls."""

    def __init__(self, llm_client, cache_size: int = 128):
        self.llm_client = llm_client
        self.cache_size = cache_size
        self.cache = {}

    def _get_cache_key(self, args: dict) -> str:
        """Generate cache key from arguments."""
        args_str = json.dumps(args, sort_keys=True)
        return hashlib.md5(args_str.encode()).hexdigest()

    def invoke(self, args: dict) -> str:
        """Invoke tool with caching."""
        cache_key = self._get_cache_key(args)

        # Check cache
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Execute tool
        result = self.llm_client.invoke(str(args)).content

        # Store in cache (simple FIFO eviction)
        if len(self.cache) >= self.cache_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]

        self.cache[cache_key] = result
        return result

def create_cached_tools(llm_client):
    """Create tools with built-in caching."""

    sentiment_tool = CachedTool(llm_client)

    @tool
    def sentiment_analysis(text: str) -> str:
        """Analyze sentiment (cached)."""
        return sentiment_tool.invoke({"text": text})

    return [sentiment_analysis]
```

### Pattern 2: Batch Tool Execution

```python
def batch_tools_node(state: AgentState):
    """Execute tools in batches for efficiency."""
    outputs = []
    last_message = state["messages"][-1]

    if not hasattr(last_message, 'tool_calls'):
        return {"messages": outputs}

    # Group tool calls by type
    tool_groups = {}
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        if tool_name not in tool_groups:
            tool_groups[tool_name] = []
        tool_groups[tool_name].append(tool_call)

    # Execute each group
    for tool_name, calls in tool_groups.items():
        tool = tools_by_name[tool_name]

        # Could batch process if tool supports it
        for tool_call in calls:
            result = tool.invoke(tool_call["args"])
            outputs.append(ToolMessage(
                content=result,
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            ))

    return {"messages": outputs}
```

### Pattern 3: Token Budget Management

```python
def agent_node_with_token_limit(state: AgentState, config: RunnableConfig):
    """Manage token usage by limiting message history."""
    messages = list(state["messages"])

    # Keep only recent messages to manage tokens
    max_messages = 10
    if len(messages) > max_messages:
        messages = messages[-max_messages:]

    system_prompt = SystemMessage(
        "You are helpful. Use tools efficiently. Keep responses concise."
    )

    response = llm_with_tools.invoke(
        [system_prompt] + messages,
        config
    )

    return {"messages": [response]}
```

---

## Testing Patterns

### Pattern 1: Unit Testing Tools

```python
import pytest
from unittest.mock import Mock, patch

def test_sentiment_analysis_tool():
    """Test sentiment analysis tool."""
    # Mock the LLM
    mock_llm = Mock()
    mock_llm.invoke.return_value = Mock(content="positive")

    # Create tool with mock
    tools = create_analysis_tools(mock_llm)
    sentiment_tool = [t for t in tools if t.name == "sentiment_analysis"][0]

    # Test
    result = sentiment_tool.invoke({"text": "I love this!"})

    assert "positive" in result.lower()
    mock_llm.invoke.assert_called_once()
```

### Pattern 2: Integration Testing Agent

```python
def test_agent_execution_flow():
    """Test agent executes tools correctly."""
    # Create test state
    state = {
        "messages": [HumanMessage(content="Analyze this text")]
    }

    # Execute agent
    result = graph.invoke(state)

    # Verify tools were called
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) > 0

    # Verify state was updated
    assert "messages" in result
```

### Pattern 3: Mock Tool Execution

```python
def test_agent_with_mock_tools():
    """Test agent with mocked tool responses."""
    # Create mock tools
    mock_tools = []

    @tool
    def mock_sentiment(text: str) -> str:
        """Mock sentiment tool."""
        return "positive"

    mock_tools.append(mock_sentiment)

    # Create agent with mocks
    llm_with_mocks = llm.bind_tools(mock_tools)

    # Test agent
    state = {"messages": [HumanMessage(content="Test message")]}
    # ... test execution
```

---

## Monitoring and Observability

### Pattern 1: Detailed Logging

```python
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def agent_node_with_logging(state: AgentState, config: RunnableConfig):
    """Agent with comprehensive logging."""
    start_time = datetime.now()
    logger.info(f"Agent node invoked. Message count: {len(state['messages'])}")

    try:
        response = llm_with_tools.invoke(
            [SystemMessage("You are helpful")] + list(state["messages"]),
            config
        )
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Agent response generated in {elapsed:.2f}s")
        return {"messages": [response]}
    except Exception as e:
        logger.error(f"Agent error: {str(e)}", exc_info=True)
        raise

def tools_node_with_logging(state: AgentState):
    """Tools node with detailed logging."""
    outputs = []
    last_message = state["messages"][-1]

    if not hasattr(last_message, 'tool_calls'):
        return {"messages": outputs}

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        logger.info(f"Executing tool: {tool_name}")
        start_time = datetime.now()

        try:
            tool_result = tools_by_name[tool_name].invoke(tool_call["args"])
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.debug(f"Tool {tool_name} executed in {elapsed:.2f}s")
            outputs.append(ToolMessage(
                content=tool_result,
                name=tool_name,
                tool_call_id=tool_call["id"],
            ))
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {str(e)}")
            outputs.append(ToolMessage(
                content=f"Error: {str(e)}",
                name=tool_name,
                tool_call_id=tool_call["id"],
            ))

    return {"messages": outputs}
```

### Pattern 2: LangSmith Integration

```python
import os

# Enable LangSmith tracing
os.environ["LANGSMITH_API_KEY"] = "your-api-key"
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "your-project-name"

# Now all invocations are automatically traced
result = graph.invoke({"messages": [HumanMessage(content="test")]})

# View traces at https://smith.langchain.com/
```

### Pattern 3: Metrics Collection

```python
from dataclasses import dataclass
from typing import List
from datetime import datetime

@dataclass
class AgentMetrics:
    start_time: datetime
    end_time: datetime = None
    tool_calls_count: int = 0
    tools_used: List[str] = None
    message_count: int = 0
    errors: List[str] = None

    def duration_seconds(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0

class MetricsCollector:
    """Collect metrics during agent execution."""

    def __init__(self):
        self.metrics = AgentMetrics(start_time=datetime.now(), tools_used=[])

    def record_tool_call(self, tool_name: str):
        self.metrics.tool_calls_count += 1
        self.metrics.tools_used.append(tool_name)

    def record_error(self, error: str):
        if self.metrics.errors is None:
            self.metrics.errors = []
        self.metrics.errors.append(error)

    def finish(self):
        self.metrics.end_time = datetime.now()

    def report(self) -> dict:
        return {
            "duration": self.metrics.duration_seconds(),
            "tool_calls": self.metrics.tool_calls_count,
            "tools_used": list(set(self.metrics.tools_used)),
            "errors": self.metrics.errors or [],
        }

# Usage in agent
def agent_node_with_metrics(
    state: AgentState,
    config: RunnableConfig,
    metrics: MetricsCollector = None
):
    if metrics:
        metrics.message_count = len(state["messages"])

    try:
        response = llm_with_tools.invoke(
            [SystemMessage("You are helpful")] + list(state["messages"]),
            config
        )
        return {"messages": [response]}
    except Exception as e:
        if metrics:
            metrics.record_error(str(e))
        raise
```

---

## Common Pitfalls

### Pitfall 1: Forgetting the Reducer

```python
# WRONG - messages will be lists of lists
class BadState(TypedDict):
    messages: Sequence[BaseMessage]

# CORRECT - messages properly merged
class GoodState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
```

### Pitfall 2: Tools Returning Complex Objects

```python
# WRONG - returns dict/json
@tool
def process(text: str) -> dict:
    return {"status": "ok", "data": [...]}

# CORRECT - returns string
@tool
def process(text: str) -> str:
    result = {"status": "ok", "data": [...]}
    return json.dumps(result)  # Or just return string insight
```

### Pitfall 3: Not Checking for tool_calls

```python
# WRONG - crashes if no tool_calls
def tools_node(state: AgentState):
    for tool_call in state["messages"][-1].tool_calls:
        # ...

# CORRECT - checks first
def tools_node(state: AgentState):
    last_message = state["messages"][-1]
    if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        return {"messages": []}
    for tool_call in last_message.tool_calls:
        # ...
```

### Pitfall 4: Mixing Sync and Async

```python
# WRONG - async tools in sync agent
async def async_tool(text: str) -> str:
    result = await some_async_call()
    return result

# CORRECT - use sync tools or handle async properly
def sync_tool(text: str) -> str:
    result = some_sync_call()
    return result
```

### Pitfall 5: Unbounded Message History

```python
# WRONG - message list grows indefinitely
def agent_node(state: AgentState):
    # Messages accumulate forever
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

# CORRECT - manage message history
def agent_node(state: AgentState):
    messages = list(state["messages"])
    # Keep only recent messages
    if len(messages) > 20:
        # Keep system message + recent messages
        messages = messages[:1] + messages[-19:]

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}
```

### Pitfall 6: Tool Docstring Issues

```python
# WRONG - no docstring or poor docstring
@tool
def analyze(text: str) -> str:
    return llm.invoke(text).content

# CORRECT - clear, detailed docstring
@tool
def analyze(text: str) -> str:
    """Analyze text sentiment and emotional tone.

    Use this tool to understand the emotional content of user messages.
    Returns a brief assessment of sentiment (positive/negative/neutral)
    and the primary emotions expressed.

    Args:
        text: The text to analyze

    Returns:
        String with sentiment assessment and emotions detected
    """
    return llm.invoke(text).content
```

---

## Summary: Key Takeaways

1. **Tools return strings** - String insights, not structured data
2. **Use closures** - Pass LLM clients via closures, not ToolRuntime
3. **Add error handling** - Validate inputs, catch exceptions gracefully
4. **Manage state carefully** - Use Annotated with add_messages reducer
5. **Log extensively** - Enable LangSmith for production visibility
6. **Test thoroughly** - Mock tools and test execution flows
7. **Optimize performance** - Cache results, batch operations, manage tokens
8. **Handle errors at tool level** - Retry logic, fallbacks, validation

---

**Last Updated**: November 2024
**Status**: Production Ready
