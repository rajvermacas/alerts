# LangGraph Tool-Calling Agent - Quick Reference Card

## Core Pattern

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

# 1. Create tools
@tool
def my_tool(query: str) -> str:
    """Tool description."""
    return "result"

# 2. Create agent
llm = ChatOpenAI(model="gpt-4o-mini")
llm_with_tools = llm.bind_tools([my_tool])

# 3. Build graph
builder = StateGraph(MessagesState)
builder.add_node("agent", lambda s: {"messages": [llm_with_tools.invoke(s["messages"])]})
builder.add_node("tools", ToolNode([my_tool]))
builder.add_edge(START, "agent")
builder.add_edge("agent", "tools")
builder.add_edge("tools", "agent")

graph = builder.compile()

# 4. Run
result = graph.invoke({"messages": [HumanMessage(content="Query")]})
```

## Tool with Internal LLM

```python
class MyTool:
    def __init__(self, llm):
        self.llm = llm
        self.name = "my_tool"
        self.description = "Does something"

    def __call__(self, query: str) -> str:
        prompt = f"Process: {query}"
        return self.llm.invoke(prompt).content

llm = ChatOpenAI(model="gpt-4o-mini")
tool_instance = MyTool(llm)
tool = tool(tool_instance, name=tool_instance.name, description=tool_instance.description)
```

## Structured Output

```python
from pydantic import BaseModel, Field

class Output(BaseModel):
    summary: str
    insights: list[str]
    confidence: float = Field(ge=0.0, le=1.0)

llm_structured = llm.with_structured_output(Output)
result = llm_structured.invoke(messages)  # Returns Output instance
```

## Routing Pattern

```python
def should_continue(state: MessagesState) -> Literal["tools", END]:
    last_message = state["messages"][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    return END

builder.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    END: END,
})
```

## State Management

```python
# DON'T
state = {"messages": []}

# DO
from langgraph.graph import MessagesState
# MessagesState automatically handles message accumulation
```

## Error Handling

```python
def __call__(self, query: str) -> str:
    try:
        if not query:
            return "Error: Empty input"
        result = self.llm.invoke(query).content
        return result
    except Exception as e:
        logger.error(f"Failed: {e}")
        return f"Error: {str(e)}"
```

## Testing

```python
from unittest.mock import MagicMock

mock_llm = MagicMock()
mock_llm.invoke.return_value.content = "Result"

tool = MyTool(mock_llm)
result = tool("test")

assert result == "Result"
assert mock_llm.invoke.called
```

## Logging

```python
import logging

logger = logging.getLogger(__name__)

def agent_node(state):
    logger.info(f"Agent: {len(state['messages'])} messages")
    response = llm_with_tools.invoke(state["messages"])
    if hasattr(response, 'tool_calls') and response.tool_calls:
        logger.info(f"Tools called: {[t.get('name') for t in response.tool_calls]}")
    return {"messages": [response]}
```

## Common Pitfalls

❌ **Global LLM**
```python
LLM = ChatOpenAI()  # Bad
def tool_func():
    return LLM.invoke(...)
```

✅ **Injected LLM**
```python
class Tool:
    def __init__(self, llm):
        self.llm = llm
```

---

❌ **Custom dict state**
```python
state = {"messages": [], "results": []}
```

✅ **MessagesState**
```python
from langgraph.graph import MessagesState
```

---

❌ **Forgot to bind tools**
```python
response = llm.invoke(query)  # LLM doesn't know about tools
```

✅ **Bind tools first**
```python
llm_with_tools = llm.bind_tools(tools)
response = llm_with_tools.invoke(query)
```

---

❌ **Async in sync agent**
```python
async def tool_func(query):
    await something()
```

✅ **Synchronous only**
```python
def tool_func(query):
    # sync code only
    return result
```

---

❌ **Returning objects**
```python
return {"key": "value"}  # Not string
```

✅ **Returning strings**
```python
return json.dumps({"key": "value"})
```

## Key Dependencies

```
langgraph>=0.2.0
langchain-core>=0.3.0
langchain-openai>=0.2.0
pydantic>=2.0.0
python>=3.10
```

## File Organization

```
project/
├── config.py           # Configuration
├── schemas.py          # Pydantic models
├── tools/
│   ├── __init__.py
│   └── [6 tool files]
├── agent.py           # Main agent
├── logging_utils.py   # Logging
├── main.py            # Entry point
└── tests/
    └── test_*.py
```

## Implementation Checklist

- [ ] Define Pydantic output schema
- [ ] Create tool classes with LLM injection
- [ ] Convert tools to LangChain tools
- [ ] Bind tools to LLM
- [ ] Create agent node
- [ ] Create should_continue routing
- [ ] Create response node with structured output
- [ ] Build graph with nodes and edges
- [ ] Add comprehensive logging
- [ ] Add error handling
- [ ] Write unit tests for tools
- [ ] Write integration tests for graph
- [ ] Test with real LLM
- [ ] Add monitoring/statistics
- [ ] Document and deploy

## LLM Choices

| Model | Cost | Tool Support | Speed | Best For |
|-------|------|--------------|-------|----------|
| gpt-4o-mini | $ | Excellent | Fast | **Default choice** |
| gpt-4o | $$ | Excellent | Slower | Complex reasoning |
| claude-3.5-sonnet | $ | Excellent | Fast | Alternative |
| azure-openai | $$ | Excellent | Fast | Enterprise |

## Timing Expectations

- **Tool with 1 call**: 500-1000ms
- **Agent with 2-3 tool calls**: 2-4 seconds
- **Complex agent (5-6 tools)**: 4-10 seconds

*Varies by model and network latency*

## Resources

| Resource | Link | Notes |
|----------|------|-------|
| Tool Calling | https://python.langchain.com/docs/concepts/tool_calling/ | Concepts |
| Structured Output | https://python.langchain.com/docs/how_to/structured_output/ | How-to |
| LangGraph Docs | https://langchain-ai.github.io/langgraph/ | Official |
| Real Python Guide | https://realpython.com/langgraph-python/ | Tutorial |
| Reference Impl | langgraph-reference-implementation.md | Copy template |

## Support

See the full documentation files:
- **Best Practices**: langgraph-tool-calling-agent-best-practices.md
- **Code Patterns**: langgraph-tool-calling-patterns.md
- **Reference Implementation**: langgraph-reference-implementation.md
- **Navigation Guide**: README.md

---

**Last Updated:** November 29, 2025
**Version:** 1.0
