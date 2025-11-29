# LangGraph Tool-Calling Agent Implementation Guide

**Complete Research & Implementation Documentation**
**Date**: November 2024
**Status**: Production Ready

---

## Overview

This documentation package provides comprehensive guidance for building multi-tool agents using LangGraph with the following capabilities:

- Single agent with 6+ tools
- Each tool calls an LLM internally for data interpretation
- Tools return string insights (not structured data)
- Agent produces structured Pydantic output
- Synchronous (blocking) execution
- Support for OpenAI and Azure OpenAI

---

## Documentation Structure

### 1. **Main Reference** - Start Here
**File**: `langgraph-tool-calling-agent-reference.md` (31 KB)

Comprehensive reference covering:
- Core architecture (ReAct pattern)
- Tool definitions with @tool decorator
- Tool configuration and LLM access patterns
- Building StateGraph with tools
- Structured output with Pydantic
- Complete 6-tool working example
- Best practices and troubleshooting
- Quick import reference

**Read this when**: You need complete understanding of how everything fits together

---

### 2. **Advanced Patterns** - Deep Dives
**File**: `langgraph-advanced-patterns.md` (23 KB)

Production-level patterns including:
- Tool state updates with Command object
- Multiple tool invocation strategies (sequential, parallel, conditional)
- Tool chaining and dependencies
- Error recovery and retry logic
- Performance optimization (caching, batching, token limits)
- Testing strategies (unit, integration, mocking)
- Monitoring and observability
- Common pitfalls and how to avoid them

**Read this when**: You need production-ready implementations and want to optimize performance

---

### 3. **Quick Code Snippets** - Copy & Paste Ready
**File**: `langgraph-code-snippets.md` (16 KB)

Organized by use case:
- Basic agent setup (minimal and custom)
- LLM configuration (OpenAI, Azure, with fallback)
- Tool patterns (simple, API, LLM-based, caching, retries)
- State management (TypedDict, Pydantic, initialization)
- Graph building (linear, conditional, loop, parallel)
- Execution patterns (invoke, streaming, batch)
- Error handling (try-catch, tool errors, timeouts)
- Testing code
- Production checklist

**Read this when**: You need quick copy-paste code for specific patterns

---

## Quick Start (5 Minutes)

### Minimal Agent

```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

@tool
def get_weather(location: str) -> str:
    """Get weather for a location."""
    return f"Sunny in {location}"

llm = ChatOpenAI(model="gpt-4o-mini")
agent = create_react_agent(llm, [get_weather])

result = agent.invoke({
    "messages": [{"role": "user", "content": "What's the weather?"}]
})
```

### Custom Agent with 6 Tools

See the **complete working example** in `langgraph-tool-calling-agent-reference.md` (Section 8: Complete Working Example)

This is a production-ready 6-tool agent with:
- Text analysis tools (sentiment, entities, topics, etc.)
- Internal LLM calls for insights
- String output from all tools
- State management
- Full error handling

---

## Key Architecture Patterns

### ReAct Agent Flow

```
[User Input]
    ↓
[Agent Node] → Calls LLM with tools bound
    ↓
[Should Continue?] → Decision point
    ├→ No → [End] → Return result
    └→ Yes
         ↓
[Tools Node] → Execute selected tools
         ↓
[Agent Node] → Loop back with tool results
```

### Tool Definition Pattern (Recommended)

```python
def create_tools(llm_client):
    """Factory pattern with LLM access via closure."""

    @tool
    def tool_name(input: str) -> str:
        """Clear docstring describing the tool."""
        # Tool uses llm_client from closure
        result = llm_client.invoke(f"Process: {input}")
        return result.content

    return [tool_name]

# Usage
tools = create_tools(llm)
```

**Why this pattern?**
- LLM client access via closure (clean, testable)
- No magic ToolRuntime complexity
- Tool remains a pure function

### State Management Pattern

```python
from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # add_messages is a reducer - prevents message duplication
```

### Graph Pattern

```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)

# Set flow
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {
    "continue": "tools",
    "end": END,
})
workflow.add_edge("tools", "agent")

graph = workflow.compile()
```

---

## Structured Output Options

### Option 1: Using create_react_agent (Simplest)

```python
from pydantic import BaseModel
from langgraph.prebuilt import create_react_agent

class ResultSchema(BaseModel):
    summary: str
    insights: list[str]
    confidence: float

agent = create_react_agent(
    llm,
    tools,
    response_format=ResultSchema
)

result = agent.invoke({"messages": [...]})
structured = result.get("structured_response")
```

### Option 2: Custom Response Node

Add a response node at the end that formats output using `with_structured_output()`:

```python
def response_node(state: AgentState):
    structured_llm = llm.with_structured_output(ResultSchema)
    result = structured_llm.invoke(state["messages"][-1].content)
    return {"structured_output": result.model_dump()}

workflow.add_node("respond", response_node)
# Route to respond before END
```

---

## Common Patterns by Use Case

### Pattern 1: Text Analysis Agent (6 Tools)
**See**: Main reference document, Section 8
- Sentiment analysis
- Entity extraction
- Key topics identification
- Readability assessment
- Content summarization
- Bias detection

Each tool uses internal LLM for insights.

### Pattern 2: Research Agent
Tools: web search, document summarization, fact checking, data extraction
All tools return string insights that feed into final structured output.

### Pattern 3: Decision Support Agent
Tools: data analysis, risk assessment, recommendation generation
Agent gathers insights from all tools, LLM synthesizes into structured decision.

### Pattern 4: Content Generation Agent
Tools: outline generation, section writing, editing, fact-checking
Sequential tool execution with dependencies.

---

## Troubleshooting Guide

### Issue: "AttributeError: 'OpenAI' object has no attribute 'bind_tools'"

**Cause**: Using `OpenAI` instead of `ChatOpenAI`

**Fix**:
```python
from langchain_openai import ChatOpenAI  # Not OpenAI
llm = ChatOpenAI(model="gpt-4o-mini")
```

### Issue: Tool not appearing in agent calls

**Cause**: Tools not bound to LLM

**Fix**:
```python
llm_with_tools = llm.bind_tools(tools)
# Use llm_with_tools in agent node, not llm
```

### Issue: Duplicate messages in state

**Cause**: Missing `add_messages` reducer

**Fix**:
```python
from langgraph.graph.message import add_messages
messages: Annotated[Sequence[BaseMessage], add_messages]
```

### Issue: Infinite loop

**Cause**: `should_continue` never returns "end"

**Fix**:
```python
def should_continue(state: AgentState) -> str:
    if not state["messages"][-1].tool_calls:
        return "end"  # Must have exit condition
    return "continue"
```

### Issue: Tools returning wrong format

**Cause**: Tools returning dicts instead of strings

**Fix**:
```python
# Wrong
@tool
def my_tool(input: str) -> dict:
    return {"result": "..."}

# Correct
@tool
def my_tool(input: str) -> str:
    result = {"result": "..."}
    return json.dumps(result)  # Or return string insight
```

---

## Environment Setup

### Prerequisites

```bash
pip install langgraph langchain-core langchain-openai
```

### Environment Variables

**OpenAI**:
```bash
export OPENAI_API_KEY="sk-..."
```

**Azure OpenAI**:
```bash
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_ENDPOINT="https://xxx.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="deployment-name"
export AZURE_OPENAI_API_VERSION="2024-02-15-preview"
```

**Optional - LangSmith Tracing**:
```bash
export LANGSMITH_API_KEY="..."
export LANGCHAIN_TRACING_V2="true"
export LANGCHAIN_PROJECT="your-project"
```

---

## Best Practices Summary

### Tool Design
- Return string insights, not structured objects
- Include comprehensive docstrings
- Use type hints for all parameters
- Make tools single-responsibility
- Handle errors gracefully

### LLM Access
- Use **closure pattern** (recommended):
  ```python
  def create_tools(llm):
      @tool
      def my_tool(input: str) -> str:
          result = llm.invoke(input)
          return result.content
      return [my_tool]
  ```
- Don't use ToolRuntime unless specifically needed

### State Management
- Use TypedDict for simple cases
- Use Pydantic BaseModel for validation
- Always include `add_messages` reducer
- Manage message history (don't let it grow unbounded)

### Error Handling
- Wrap tool execution in try-catch
- Return error messages as strings
- Add input validation
- Log errors extensively

### Testing
- Mock LLM calls with unittest.mock
- Test tools independently
- Test agent execution flow
- Test error scenarios

### Production
- Enable LangSmith tracing
- Add comprehensive logging
- Monitor token usage
- Implement timeouts
- Cache results when appropriate

---

## File Reference

```
.dev-resources/
└── docs/
    ├── README-LANGGRAPH.md (this file)
    ├── langgraph-tool-calling-agent-reference.md (Main reference)
    ├── langgraph-advanced-patterns.md (Production patterns)
    └── langgraph-code-snippets.md (Quick code examples)
```

---

## Next Steps

### 1. Start with Minimal Agent
Use the "Quick Start" section above to create a simple agent and verify setup.

### 2. Read Main Reference
Go through `langgraph-tool-calling-agent-reference.md` sections in order:
- Overview
- Installation
- Core Architecture
- Tool Definitions
- StateGraph Building
- Complete Example

### 3. Implement Your Agent
Use the complete example in Section 8 as a template for your 6-tool agent.

### 4. Optimize for Production
Review `langgraph-advanced-patterns.md` for:
- Error handling strategies
- Performance optimization
- Testing patterns
- Monitoring setup

### 5. Quick Reference
Keep `langgraph-code-snippets.md` open for quick copy-paste code patterns.

---

## Key Concepts Reference

### ReAct (Reasoning + Acting)
The standard agent pattern where:
1. Agent reasons about the task
2. Agent decides which tool(s) to use
3. Tools execute and return results
4. Agent reasons about results
5. Repeat until task is complete

### Reducer
A function that combines state updates. The `add_messages` reducer:
- Prevents duplicate messages
- Merges message lists correctly
- Maintains message order

```python
messages: Annotated[Sequence[BaseMessage], add_messages]
```

### Tool Binding
The process of telling an LLM which tools it can use:
```python
llm_with_tools = llm.bind_tools(tools)
```

### State Graph
A computational graph where:
- Nodes are functions
- Edges define execution flow
- State flows through all nodes
- Conditional edges create branches

### Structured Output
Forcing the LLM to return data in a specific Pydantic model format:
```python
llm.with_structured_output(MyModel)
```

---

## Performance Considerations

### Token Usage
- Reuse LLM clients across tool calls
- Manage message history (max 20-30 recent messages)
- Use token counting to monitor costs

### Latency
- Use parallel tool execution for independent tools
- Consider tool caching for repeated queries
- Stream responses for real-time feedback

### Reliability
- Implement retry logic with exponential backoff
- Add timeouts to prevent hanging
- Use error recovery patterns

---

## Testing Checklist

- [ ] Tool works standalone with mock LLM
- [ ] Agent executes basic query
- [ ] Tools are called when appropriate
- [ ] Tool errors are handled gracefully
- [ ] State updates correctly
- [ ] Output matches expected schema
- [ ] Agent terminates (no infinite loop)
- [ ] Error cases handled
- [ ] Performance acceptable

---

## Official Sources

**Official Documentation**:
- [LangGraph Official Docs](https://langchain-ai.github.io/langgraph/)
- [LangChain Tools Reference](https://docs.langchain.com/oss/python/langchain/tools)
- [ReAct Agent from Scratch](https://langchain-ai.github.io/langgraph/how-tos/react-agent-from-scratch/)

**Azure Integration**:
- [Azure OpenAI + LangGraph](https://techcommunity.microsoft.com/blog/educatordeveloperblog/how-to-build-tool-calling-agents-with-azure-openai-and-lang-graph/4391136)

**Advanced Topics**:
- [Tool Runtime Documentation](https://python.langchain.com/docs/how_to/tool_runtime/)
- [Structured Output](https://langchain-ai.github.io/langgraph/how-tos/react-agent-structured-output/)
- [State Models](https://langchain-ai.github.io/langgraph/how-tos/state-model/)

---

## Quick Import Reference

```python
# Core LangGraph
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent, ToolNode, tools_condition

# LangChain Core
from langchain_core.tools import tool, ToolRuntime
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, SystemMessage, AIMessage
from langchain_core.runnables import RunnableConfig

# LLM Providers
from langchain_openai import ChatOpenAI, AzureChatOpenAI

# State & Types
from typing import Annotated, Sequence, TypedDict
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# Utilities
import json
import os
```

---

## Document Statistics

| Document | Size | Sections | Focus |
|----------|------|----------|-------|
| Main Reference | 31 KB | 11 | Complete guide with examples |
| Advanced Patterns | 23 KB | 8 | Production patterns & optimization |
| Code Snippets | 16 KB | 8 | Quick copy-paste code |
| **Total** | **70 KB** | **27+** | Comprehensive coverage |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Nov 2024 | Initial comprehensive documentation |

---

## Support & Resources

**If you encounter issues**:
1. Check the **Troubleshooting Guide** in this README
2. Search in `langgraph-advanced-patterns.md` for "Common Pitfalls"
3. Review relevant section in `langgraph-code-snippets.md`
4. Check official LangGraph documentation (links above)
5. Enable LangSmith tracing for debugging

**For specific patterns**:
- Multi-tool execution → See "Advanced Patterns: Multiple Tool Invocation"
- Structured output → See "Reference: Structured Output with Pydantic"
- Error handling → See "Advanced Patterns: Error Recovery"
- Testing → See "Advanced Patterns: Testing Patterns"

---

**Last Updated**: November 2024
**Status**: Production Ready
**Maintained By**: Research Team

For questions or updates, refer to the official LangGraph documentation.
