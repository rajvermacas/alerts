# LangGraph Tool-Calling Agent: Quick Code Snippets

**Document Date**: November 2024
**Purpose**: Ready-to-use code patterns organized by use case

---

## Quick Navigation
- [Basic Agent Setup](#basic-agent-setup)
- [LLM Configuration](#llm-configuration)
- [Tool Patterns](#tool-patterns)
- [State Management](#state-management)
- [Graph Building](#graph-building)
- [Execution Patterns](#execution-patterns)
- [Error Handling](#error-handling)
- [Testing](#testing)

---

## Basic Agent Setup

### Minimal Agent (5 minutes)

```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

# Define tools
@tool
def get_weather(location: str) -> str:
    """Get weather for a location."""
    return f"Sunny in {location}"

tools = [get_weather]

# Create agent
llm = ChatOpenAI(model="gpt-4o-mini")
agent = create_react_agent(llm, tools)

# Run
result = agent.invoke({
    "messages": [{"role": "user", "content": "What's the weather in SF?"}]
})

print(result["messages"][-1].content)
```

### Custom Agent from Scratch

```python
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, SystemMessage
from typing import Annotated, Sequence, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
import json

# State
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# Tools
@tool
def my_tool(input: str) -> str:
    """My tool description."""
    return f"Result: {input}"

tools = [my_tool]
tools_by_name = {t.name: t for t in tools}

# LLM
llm = ChatOpenAI(model="gpt-4o-mini")
llm_with_tools = llm.bind_tools(tools)

# Nodes
def agent_node(state: AgentState, config: RunnableConfig):
    response = llm_with_tools.invoke(
        [SystemMessage("You are helpful")] + list(state["messages"]),
        config
    )
    return {"messages": [response]}

def tools_node(state: AgentState):
    outputs = []
    last_message = state["messages"][-1]
    if not hasattr(last_message, 'tool_calls'):
        return {"messages": outputs}
    for tc in last_message.tool_calls:
        result = tools_by_name[tc["name"]].invoke(tc["args"])
        outputs.append(ToolMessage(
            content=result,
            name=tc["name"],
            tool_call_id=tc["id"],
        ))
    return {"messages": outputs}

def should_continue(state: AgentState) -> str:
    return "end" if not state["messages"][-1].tool_calls else "continue"

# Graph
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {
    "continue": "tools",
    "end": END,
})
workflow.add_edge("tools", "agent")

graph = workflow.compile()

# Execute
result = graph.invoke({"messages": [HumanMessage(content="Test")]})
```

---

## LLM Configuration

### OpenAI

```python
from langchain_openai import ChatOpenAI
import os

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    api_key=os.getenv("OPENAI_API_KEY"),
)
```

### Azure OpenAI

```python
from langchain_openai import AzureChatOpenAI
import os

llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    api_version="2024-02-15-preview",
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
)
```

### With Model Fallback

```python
from langchain_core.language_model import BaseLanguageModel
from langchain_openai import ChatOpenAI, AzureChatOpenAI
import os

def get_llm() -> BaseLanguageModel:
    """Get LLM from Azure or OpenAI."""
    if os.getenv("AZURE_OPENAI_ENDPOINT"):
        return AzureChatOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            api_version="2024-02-15-preview",
        )
    else:
        return ChatOpenAI(
            model="gpt-4o-mini",
            api_key=os.getenv("OPENAI_API_KEY"),
        )

llm = get_llm()
```

### With Streaming

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4o-mini",
    streaming=True,
)

# Stream responses
for chunk in llm.stream("Hello"):
    print(chunk.content, end="", flush=True)
```

---

## Tool Patterns

### Simple String Tool

```python
from langchain_core.tools import tool

@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression.

    Args:
        expression: A math expression like '2 + 2'
    """
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error: {e}"
```

### Tool with External API

```python
@tool
def fetch_url(url: str) -> str:
    """Fetch content from a URL.

    Args:
        url: The URL to fetch
    """
    import requests
    try:
        response = requests.get(url, timeout=5)
        return response.text[:500]  # First 500 chars
    except Exception as e:
        return f"Error fetching {url}: {e}"
```

### Tool with Internal LLM

```python
def create_llm_tools(llm):
    @tool
    def analyze(text: str) -> str:
        """Analyze text using LLM."""
        result = llm.invoke(f"Analyze: {text}")
        return result.content

    @tool
    def summarize(text: str) -> str:
        """Summarize text using LLM."""
        result = llm.invoke(f"Summarize: {text}")
        return result.content

    return [analyze, summarize]

tools = create_llm_tools(llm)
```

### Tool with Custom Name

```python
@tool("web_search")
def search(query: str) -> str:
    """Search the web."""
    return f"Results for {query}"
```

### Tool with Context Access

```python
from langchain_core.tools import tool, ToolRuntime
from typing import Annotated

@tool
def get_user_context(
    runtime: Annotated[ToolRuntime, "ToolRuntime"] = None
) -> str:
    """Get user context from state."""
    if not runtime:
        return "No context"
    user_id = runtime.state.get("user_id", "unknown")
    return f"User: {user_id}"
```

### Tool with Retry

```python
from functools import wraps
import time

def with_retry(max_retries=3):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        return f"Failed after {max_retries} attempts: {e}"
                    time.sleep(1 * (2 ** attempt))
            return "Unknown error"
        return wrapper
    return decorator

@tool
@with_retry(max_retries=3)
def unreliable_tool(input: str) -> str:
    """Tool that might fail."""
    import random
    if random.random() < 0.5:
        raise Exception("Random failure")
    return f"Success: {input}"
```

### Tool with Caching

```python
from functools import lru_cache

class CachedTool:
    def __init__(self, ttl_seconds=3600):
        self.ttl_seconds = ttl_seconds
        self.cache = {}

    def get_or_compute(self, key, compute_fn):
        if key in self.cache:
            return self.cache[key]
        result = compute_fn()
        self.cache[key] = result
        return result

cache = CachedTool()

@tool
def cached_lookup(query: str) -> str:
    """Lookup with caching."""
    def compute():
        # Expensive operation
        return f"Result for {query}"
    return cache.get_or_compute(query, compute)
```

---

## State Management

### Simple State (TypedDict)

```python
from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
```

### Extended State

```python
class ExtendedState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
    conversation_id: str
    analysis_results: dict
```

### Pydantic State with Validation

```python
from pydantic import BaseModel, Field
from typing import Annotated, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class PydanticState(BaseModel):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str = Field(default="")
    analysis_count: int = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)
```

### State with Initialization

```python
def init_state(user_id: str) -> AgentState:
    """Initialize agent state."""
    return {
        "messages": [],
        "user_id": user_id,
        "conversation_id": str(uuid.uuid4()),
    }

# Usage
state = init_state("user123")
```

---

## Graph Building

### Simple Linear Graph

```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(AgentState)
workflow.add_node("process", process_node)
workflow.add_node("finish", finish_node)

workflow.set_entry_point("process")
workflow.add_edge("process", "finish")
workflow.add_edge("finish", END)

graph = workflow.compile()
```

### Conditional Graph

```python
def route_decision(state: AgentState) -> str:
    if len(state["messages"]) > 5:
        return "summarize"
    return "continue"

workflow.add_node("agent", agent_node)
workflow.add_node("continue_node", continue_node)
workflow.add_node("summarize", summarize_node)

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", route_decision, {
    "continue": "continue_node",
    "summarize": "summarize",
})
```

### Loop Pattern

```python
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {
    "continue": "tools",
    "end": END,
})
workflow.add_edge("tools", "agent")  # Loop back
```

### Parallel Branches

```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(AgentState)
workflow.add_node("branch_a", branch_a_node)
workflow.add_node("branch_b", branch_b_node)
workflow.add_node("merge", merge_node)

workflow.set_entry_point("branch_a")
workflow.add_edge("branch_a", "branch_b")  # Wait for both
workflow.add_edge("branch_b", "merge")
workflow.add_edge("merge", END)
```

---

## Execution Patterns

### Basic Invoke (Synchronous)

```python
result = graph.invoke({
    "messages": [HumanMessage(content="Hello")]
})

print(result["messages"][-1].content)
```

### Invoke with Config

```python
from langchain_core.runnables.config import RunnableConfig

config = RunnableConfig(
    tags=["production"],
    metadata={"user_id": "123"}
)

result = graph.invoke(
    {"messages": [HumanMessage(content="Hello")]},
    config
)
```

### Streaming Output

```python
# Stream individual events
for event in graph.stream({"messages": [HumanMessage(content="Hello")]}):
    print(event)

# Stream with mode
for output in graph.stream(
    {"messages": [HumanMessage(content="Hello")]},
    stream_mode="values"
):
    print(output)
```

### Get Final State

```python
state = graph.invoke({"messages": [HumanMessage(content="Hello")]})

# Access messages
for msg in state["messages"]:
    print(f"{msg.__class__.__name__}: {msg.content}")

# Access other state fields
print(f"User: {state.get('user_id')}")
```

### Batch Execution

```python
from langchain_core.messages import HumanMessage

queries = [
    "What is the weather?",
    "Tell me a joke",
    "Summarize this",
]

results = graph.batch([
    {"messages": [HumanMessage(content=q)]}
    for q in queries
])

for i, result in enumerate(results):
    print(f"Query {i}: {result['messages'][-1].content}")
```

---

## Error Handling

### Try-Catch Pattern

```python
try:
    result = graph.invoke({"messages": [HumanMessage(content="test")]})
except ValueError as e:
    print(f"Invalid input: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
    # Log and handle
```

### Tool Error Handling

```python
def tools_node_safe(state: AgentState):
    outputs = []
    last_message = state["messages"][-1]

    if not hasattr(last_message, 'tool_calls'):
        return {"messages": outputs}

    for tool_call in last_message.tool_calls:
        try:
            result = tools_by_name[tool_call["name"]].invoke(tool_call["args"])
        except KeyError:
            result = f"Unknown tool: {tool_call['name']}"
        except Exception as e:
            result = f"Error: {str(e)}"

        outputs.append(ToolMessage(
            content=result,
            name=tool_call["name"],
            tool_call_id=tool_call["id"],
        ))

    return {"messages": outputs}
```

### Timeout Handling

```python
import signal

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Operation timed out")

signal.signal(signal.SIGALRM, timeout_handler)

try:
    signal.alarm(30)  # 30 second timeout
    result = graph.invoke({"messages": [HumanMessage(content="test")]})
    signal.alarm(0)  # Cancel alarm
except TimeoutException:
    print("Agent execution timed out")
```

---

## Testing

### Unit Test Tool

```python
import pytest
from unittest.mock import Mock

def test_tool_success():
    mock_llm = Mock()
    mock_llm.invoke.return_value = Mock(content="test result")

    tools = create_llm_tools(mock_llm)
    tool = tools[0]

    result = tool.invoke({"input": "test"})
    assert "test result" in result

def test_tool_error():
    @tool
    def failing_tool(input: str) -> str:
        raise ValueError("Test error")

    try:
        failing_tool.invoke({"input": "test"})
    except ValueError:
        pass  # Expected
```

### Integration Test Agent

```python
def test_agent_with_tools():
    state = {"messages": [HumanMessage(content="test")]}

    # Check agent executes
    result = graph.invoke(state)

    # Verify state structure
    assert "messages" in result
    assert len(result["messages"]) > 1

    # Check messages are correct type
    from langchain_core.messages import BaseMessage
    for msg in result["messages"]:
        assert isinstance(msg, BaseMessage)
```

### Mock Tool Execution

```python
def test_agent_tool_calling():
    # Override tools with mocks
    @tool
    def mock_weather(location: str) -> str:
        return "Sunny"

    mock_tools = [mock_weather]
    mock_llm_with_tools = llm.bind_tools(mock_tools)

    # Test agent calls tools
    # ...
```

---

## Production Checklist

- [ ] Tools have docstrings
- [ ] Error handling in tools
- [ ] Logging enabled
- [ ] State management configured
- [ ] LLM provider set up
- [ ] API keys in environment variables
- [ ] Timeouts configured
- [ ] Rate limiting considered
- [ ] Tests passing
- [ ] LangSmith tracing enabled

---

## Common Issues and Solutions

### Issue: "tool_calls not found"
```python
# Check if attribute exists
if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
    # Safe to use
```

### Issue: Duplicate messages
```python
# Use add_messages reducer
from langgraph.graph.message import add_messages
messages: Annotated[Sequence[BaseMessage], add_messages]
```

### Issue: Tools not called
```python
# Ensure tools are bound
llm_with_tools = llm.bind_tools(tools)

# Ensure they're passed to invoke
llm_with_tools.invoke(messages)
```

### Issue: State not updating
```python
# Return properly formatted dict
return {"messages": [response]}
# Not {"messages": response} or just response
```

### Issue: Infinite loops
```python
# Ensure should_continue returns "end" sometimes
def should_continue(state):
    if not state["messages"][-1].tool_calls:
        return "end"  # Must have exit condition
    return "continue"
```

---

**Last Updated**: November 2024
**Version**: 1.0
