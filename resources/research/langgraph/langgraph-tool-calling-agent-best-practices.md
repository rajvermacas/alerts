# LangGraph Tool-Calling Agent Best Practices

## Executive Summary

This document provides comprehensive research-backed guidance for building production-ready LangGraph agents with multiple tools that internally access LLMs. Based on 2024-2025 industry practices, the key approach involves using **tool binding** with LangChain's `bind_tools()` method, **state management** via `MessagesState`, and **structured output** through Pydantic models with `.with_structured_output()`. The critical pattern for tools requiring LLM access is injecting dependencies through **node-level configuration** or **class-based tool wrappers** rather than global state.

## Problem Context

Your requirements demand:
- A single LangGraph agent with 6 tools
- Tools that call an LLM internally for decision-making/processing
- Tools returning string insights (text-based output, not structured objects)
- Final agent output as structured Pydantic data
- Synchronous execution model
- OpenAI or Azure OpenAI backend

This creates an interesting architectural constraint: tools need access to the LLM client without creating circular dependencies or global state pollution. The solution involves dependency injection patterns and careful separation of concerns.

## Research Findings

### Current Industry Landscape

LangGraph has matured significantly in 2024-2025 as the official low-level agent orchestration framework from LangChain. Major companies (Klarna, Replit, Elastic) use it for production agents. The framework evolved from ReAct-style agents to support:

1. **Explicit control flow** over agent loops (not hidden in orchestration)
2. **Tool binding** via `model.bind_tools()` for native tool calling
3. **Structured outputs** via `.with_structured_output()` method
4. **Context/config passing** to nodes and tools (new in 0.2.x+)
5. **State management** through typed state graphs with message accumulation

### Key Technical Insights

#### 1. Tool Binding Architecture

The modern approach uses LangChain's `bind_tools()` method:

```python
llm_with_tools = llm.bind_tools(tools)
```

This creates a tool-aware LLM that:
- Understands available tool schemas
- Returns structured `tool_calls` in messages when appropriate
- Falls back to text generation for non-tool queries

#### 2. State Management with MessagesState

`MessagesState` is a predefined typed state that automatically handles message accumulation:

```python
from langgraph.graph import MessagesState

# MessagesState has a single "messages" field using operator.add
# This means each node appends to messages rather than replacing
```

This is superior to manual state dicts because:
- Built-in message deduplication
- Automatic history management
- Proper typing for IDE support

#### 3. Tool Definition Requirements

Modern tool definitions follow these patterns:

**Pattern 1: @tool decorator (recommended)**
```python
from langchain_core.tools import tool

@tool
def my_tool(input_text: str) -> str:
    """Clear description of what this tool does."""
    return result
```

**Pattern 2: Tool class (for complex tools)**
```python
from langchain_core.tools import BaseTool

class MyTool(BaseTool):
    name: str = "my_tool"
    description: str = "Does something"

    def _run(self, input_text: str) -> str:
        return result
```

**Key constraint**: Tools are expected to be `(str) -> str` for basic binding, though you can use `@tool` decorator with typed parameters for structured inputs.

#### 4. Structured Output with Pydantic

The `.with_structured_output()` method forces the LLM to return valid Pydantic objects:

```python
from pydantic import BaseModel

class AgentOutput(BaseModel):
    insights: list[str]
    recommendation: str
    confidence: float

# Create a response node that extracts to structured output
llm_structured = llm.with_structured_output(AgentOutput)
response = llm_structured.invoke([messages])
```

This is the **cleanest way** to get typed output from agents in 2024.

#### 5. Tools with LLM Access (Dependency Injection)

This is the critical pattern for your requirement. Do NOT create global LLM instances. Instead:

**Option A: Tool wrapper class (RECOMMENDED)**
```python
class AnalysisTool:
    def __init__(self, llm):
        self.llm = llm

    def __call__(self, query: str) -> str:
        # Tool uses internal LLM
        return self.llm.invoke(query)

# Create tool instance
analysis = AnalysisTool(llm)
tools = [
    tool(analysis, name="analyze", description="..."),
    # more tools
]
```

**Option B: functools.partial (LIGHTER)**
```python
from functools import partial

def deep_analysis(query: str, llm) -> str:
    return llm.invoke(query)

tools = [
    tool(partial(deep_analysis, llm=llm), name="analyze", description="..."),
]
```

**Option C: Node-level config passing (COMPLEX but flexible)**
```python
# Pass via RunnableConfig
def node(state: MessagesState, config: RunnableConfig):
    llm = config["configurable"]["llm"]
```

**Best practice**: Use Option A (class wrapper) because it's:
- Clean and testable
- Doesn't pollute node signatures
- Works naturally with tool binding
- Type-safe

#### 6. Conditional Edge Routing

The standard pattern for tool-calling agents:

```python
def should_continue(state: MessagesState) -> Literal["tools", END]:
    """Check if LLM wants to call a tool."""
    last_message = state["messages"][-1]

    # If tool calls exist in LLM response, route to tools
    if last_message.tool_calls:
        return "tools"
    # Otherwise, we have the final response
    return END

# Add conditional edge
graph.add_conditional_edges(
    "agent",
    should_continue,
    {
        "tools": "handle_tools",
        END: END,
    }
)
```

#### 7. Tool Node Execution

The `ToolNode` class automatically maps tool calls to execution:

```python
from langgraph.prebuilt import ToolNode

# ToolNode automatically:
# 1. Parses tool_calls from LLM message
# 2. Invokes correct tool
# 3. Returns ToolMessage with results

tool_node = ToolNode(tools)
graph.add_node("tools", tool_node)
```

### Recommended Approaches

#### Approach 1: ReAct Pattern (Prebuilt - Fastest)
**Maturity Level**: Proven/Standard
**Best For**: Straightforward agents, quick prototyping
**Trade-offs**:
- Pro: Minimal code, built-in best practices
- Con: Less customization

```python
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(
    model=llm,
    tools=tools,
    state_modifier="You are a helpful assistant."
)

result = agent.invoke({"messages": [HumanMessage(content="Query")]})
```

#### Approach 2: Custom StateGraph (Recommended for Your Case)
**Maturity Level**: Proven/Standard
**Best For**: Multiple tools, tools with internal LLM, structured output requirement
**Trade-offs**:
- Pro: Full control, clear separation of concerns, easy to test
- Con: More code than prebuilt

This is the pattern you should use because it:
1. Allows tools to have their own LLM instances
2. Clear control over state flow
3. Easy to add structured output node
4. Testable with clear node boundaries

#### Approach 3: Command-Based State Updates (Emerging)
**Maturity Level**: Emerging (0.2.x+)
**Best For**: Complex state mutations, tools that need to update state directly
**Trade-offs**:
- Pro: Tools can directly return Command objects to mutate state
- Con: Requires newer LangGraph version (0.2.x+)

```python
from langgraph.types import Command

def tool_node(state: MessagesState):
    # Instead of returning {"messages": [...]}, tools can return:
    return Command(
        update={"messages": [tool_result]},
        goto="agent"  # Optional: redirect to specific node
    )
```

## Technology Stack Recommendations

### Required Packages
```
langgraph>=0.2.0           # Core framework
langchain-core>=0.3.0      # Tool definitions, base types
langchain-openai>=0.2.0    # OpenAI provider
pydantic>=2.0.0            # Structured output
python>=3.10               # Type hints support
```

### Optional but Recommended
```
langchain-anthropic>=0.1.0 # Alternative: Claude models
python-dotenv>=1.0.0       # Environment management
pytest>=7.0                # Testing
pytest-asyncio>=0.21.0     # Async test support
```

### LLM Provider Choice
- **OpenAI**: `ChatOpenAI(model="gpt-4o-mini")` - Fast, cheap, best tool support
- **Azure OpenAI**: `AzureChatOpenAI(...)` - Enterprise, on-prem option
- **Anthropic Claude**: `ChatAnthropic(model="claude-3-5-sonnet-20241022")` - Strong reasoning

For tool calling, all three have excellent support. GPT-4o-mini provides the best price/performance for agent tasks.

## Architecture Patterns

### Core Agent Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Graph Entry Point                   │
└──────────────────────┬──────────────────────────────┘
                       │
                       v
         ┌─────────────────────────┐
         │   Agent Node (LLM)      │
         │  - Receives state       │
         │  - Calls LLM with tools │
         │  - Returns thought/tool │
         │  - Bound to tools       │
         └──────────────┬──────────┘
                        │
         ┌──────────────v──────────────┐
         │  Conditional Router         │
         │  (should_continue)          │
         │  - Check for tool_calls     │
         │  - Route to tools or end    │
         └──────────────┬──────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
        v                               v
   ┌─────────────────┐         ┌──────────────┐
   │  Tool Node      │         │ Response Node│
   │  - Execute      │         │ - Structured │
   │    tools        │         │   output     │
   │  - Return       │         │ - Return end │
   │    results      │         │   result     │
   └────────┬────────┘         └──────────────┘
            │                        │
            v                        v
   ┌──────────────────────────────────────┐
   │    Loop back to Agent Node           │
   │    (with tool results in messages)   │
   └─────────────────────────────────────┘
```

### Dependency Injection for Tool-Accessing-LLM Pattern

```python
# 1. Create tool wrapper classes
class SummarizationTool:
    def __init__(self, llm):
        self.llm = llm
        self.name = "summarize"
        self.description = "Summarize text"

    def __call__(self, text: str) -> str:
        return self.llm.invoke(text).content

class AnalysisTool:
    def __init__(self, llm):
        self.llm = llm
        self.name = "analyze"
        self.description = "Analyze content"

    def __call__(self, text: str) -> str:
        return self.llm.invoke(text).content

# 2. Instantiate with LLM
llm = ChatOpenAI(model="gpt-4o-mini")
tools_instances = [
    SummarizationTool(llm),
    AnalysisTool(llm),
    # ... 4 more tools
]

# 3. Convert to LangChain tools
from langchain_core.tools import tool

tools = [
    tool(t, name=t.name, description=t.description)
    for t in tools_instances
]
```

### Structured Output Integration

```python
from pydantic import BaseModel, Field

class AgentInsight(BaseModel):
    """Final structured output from agent."""
    summary: str = Field(description="Summary of analysis")
    insights: list[str] = Field(description="Key insights found")
    recommendation: str = Field(description="Recommended action")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence 0-1")

# In response node:
def respond(state: MessagesState) -> dict:
    """Generate structured response."""
    llm_structured = llm.with_structured_output(AgentInsight)

    # Use conversation history
    response = llm_structured.invoke(state["messages"])

    return {"messages": [AIMessage(content=response.model_dump_json())]}
```

## Implementation Roadmap

### Phase 1: Core Agent Structure (Day 1)
1. Define state using `MessagesState`
2. Create main agent node with LLM binding
3. Implement conditional routing
4. Add ToolNode for execution
5. Test basic agent flow with 1-2 tools

### Phase 2: Tool Implementation (Days 1-2)
1. Design tool wrapper classes (6 tools)
2. Implement LLM access pattern for each
3. Define clear input/output contracts
4. Create mock LLM for testing
5. Unit test each tool independently

### Phase 3: Structured Output (Day 2)
1. Define final Pydantic output model
2. Create response node with `.with_structured_output()`
3. Implement validation and error handling
4. Test end-to-end output structure

### Phase 4: Integration and Polish (Days 2-3)
1. Full agent integration test
2. Error handling and retry logic
3. Logging at each node
4. Performance profiling
5. Documentation and examples

### Phase 5: Production Hardening (Day 3)
1. Add human-in-the-loop breaks (optional)
2. Implement streaming if needed
3. Deploy with proper config management
4. Monitor and observe agent behavior

## Best Practices Checklist

- [ ] Use `MessagesState` not custom dicts (automatic message accumulation)
- [ ] Create tool wrapper classes for tools with LLM access (not global state)
- [ ] Use `@tool` decorator for simple tools, classes for complex ones
- [ ] Always include clear docstrings in tool definitions
- [ ] Bind tools to LLM with `llm.bind_tools(tools)` before graph creation
- [ ] Use `should_continue()` function for tool call routing
- [ ] Use `ToolNode` prebuilt for automatic tool execution
- [ ] Define final output as Pydantic model, use `.with_structured_output()`
- [ ] Keep agent prompt in SystemMessage, not hardcoded in node
- [ ] Add extensive logging at each node for debugging
- [ ] Test tools independently before adding to graph
- [ ] Use synchronous LLM calls (not async) for your requirements
- [ ] Implement proper exception handling in tool wrappers
- [ ] Validate Pydantic output before returning from graph
- [ ] Use `.with_config(run_name="...")` for tracking

## Anti-Patterns to Avoid

- **DON'T**: Use global LLM instances accessed by tools (creates testing nightmares)
- **DON'T**: Define tools as async functions for synchronous agent (causes conflicts)
- **DON'T**: Mix tool results with state messages without ToolMessage wrapper
- **DON'T**: Use dict state instead of MessagesState (lose message accumulation benefits)
- **DON'T**: Return structured objects from tools (spec says string insights)
- **DON'T**: Create custom tool execution logic (use ToolNode)
- **DON'T**: Skip tool docstrings (LLM won't understand tool purpose)
- **DON'T**: Ignore tool output in condition routing (tools need visibility)
- **DON'T**: Use parallel_tool_calls=True if tools have dependencies
- **DON'T**: Bind tools after graph construction (won't be available to LLM)

## Security Considerations

1. **Tool Access Control**: Validate tool inputs before execution
   ```python
   def tool_wrapper(self, text: str) -> str:
       if len(text) > 10000:
           raise ValueError("Input too large")
       return self.llm.invoke(text).content
   ```

2. **API Key Management**: Use environment variables, never hardcode
   ```python
   from langchain_openai import ChatOpenAI
   llm = ChatOpenAI(model="gpt-4o-mini")  # Uses OPENAI_API_KEY env var
   ```

3. **Cost Control**: Set max tokens and implement rate limiting
   ```python
   llm = ChatOpenAI(
       model="gpt-4o-mini",
       max_tokens=1000,
       temperature=0.7
   )
   ```

4. **Prompt Injection**: Use SystemMessage for fixed instructions
   ```python
   messages = [
       SystemMessage(content="You are a helpful assistant."),
       HumanMessage(content=user_input)  # Separate from instruction
   ]
   ```

5. **Tool Output Validation**: Always validate tool results
   ```python
   result = llm.invoke(query).content
   if not result or len(result) == 0:
       return "No meaningful result"
   return result
   ```

## Testing Strategy

### Unit Testing Tools
```python
import pytest
from unittest.mock import MagicMock

def test_summarize_tool():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "Summary text"

    tool = SummarizationTool(mock_llm)
    result = tool("Long text to summarize")

    assert result == "Summary text"
    mock_llm.invoke.assert_called_once()
```

### Integration Testing Graph
```python
def test_agent_with_tool_calling():
    llm = ChatOpenAI(model="gpt-4o-mini")
    tools = [SummarizationTool(llm), AnalysisTool(llm)]

    graph = build_agent_graph(llm, tools)

    result = graph.invoke({
        "messages": [HumanMessage(content="Analyze this text: ...")]
    })

    assert isinstance(result, AgentInsight)
    assert result.confidence > 0
```

### Output Validation
```python
def test_structured_output_validation():
    schema = AgentInsight

    # Pydantic automatically validates
    insight = schema(
        summary="Test",
        insights=["insight1"],
        recommendation="Act",
        confidence=0.8
    )

    assert insight.model_dump_json()  # Should serialize
```

### Mock LLM for Testing
```python
from langchain_core.language_models.llm import LLM

class MockLLM(LLM):
    @property
    def _llm_type(self) -> str:
        return "mock"

    def _call(self, prompt: str, **kwargs) -> str:
        return "Mock response"

    def invoke(self, input, config=None, **kwargs):
        from langchain_core.messages import AIMessage
        return AIMessage(content="Mock response")
```

## Monitoring and Observability

### Node-Level Logging
```python
import logging

logger = logging.getLogger(__name__)

def agent_node(state: MessagesState) -> dict:
    logger.info(f"Agent node invoked with {len(state['messages'])} messages")

    response = llm_with_tools.invoke(state["messages"])

    if response.tool_calls:
        logger.info(f"LLM decided to call {len(response.tool_calls)} tools")
    else:
        logger.info("LLM generated final response")

    return {"messages": [response]}
```

### Graph Execution Tracing
```python
# Enable debug mode
from langraph.graph import StateGraph

graph = StateGraph(MessagesState)
# ... add nodes and edges ...
app = graph.compile()

# Run with tracing
config = {"recursion_limit": 25}  # Prevent infinite loops
result = app.invoke(
    {"messages": [HumanMessage(content="Query")]},
    config=config
)
```

### Metrics to Track
- Tool invocation count per type
- Tool execution time (ms)
- Token usage per agent run
- Final response quality (manual or automated)
- Error rate by tool
- Agent loop count

## Further Reading

### Official Documentation
- [LangGraph Tool Calling Guide](https://langchain-ai.github.io/langgraph/how-tos/tool-calling/)
- [LangChain Tool Concepts](https://python.langchain.com/docs/concepts/tool_calling/)
- [LangChain Structured Output](https://python.langchain.com/docs/how_to/structured_output/)

### Practical Guides
- [Building Tool Calling Agents with LangGraph: A Complete Guide](https://sangeethasaravanan.medium.com/building-tool-calling-agents-with-langgraph-a-complete-guide-ebdcdea8f475) - Medium, 2024
- [LangGraph Structured Output Agent](https://github.com/Tanujkumar24/LANGGRAPH-STRUCTURED-OUTPUT-AGENT) - GitHub Reference Implementation
- [LangGraph: Build Stateful AI Agents in Python](https://realpython.com/langgraph-python/) - Real Python, November 2024

### Advanced Topics
- [LangGraph Multi-Agent Workflows](https://blog.langchain.com/langgraph-multi-agent-workflows/) - LangChain Blog
- [Building Agentic RAG Systems with LangGraph](https://www.analyticsvidhya.com/blog/2024/07/building-agentic-rag-systems-with-langgraph/) - Analytics Vidhya, July 2024
- [Comprehensive Guide to Tool Calling in LangChain](https://blog.langchain.com/tool-calling-with-langchain/) - LangChain Blog

### Community Resources
- [GitHub: awesome-LangGraph](https://github.com/von-development/awesome-LangGraph) - Curated LangGraph examples
- [LangGraph Discussions](https://github.com/langchain-ai/langgraph/discussions) - Community Q&A
- [LangChain Academy](https://github.com/langchain-ai/langchain-academy) - Official courses

## Research Metadata

- **Research Date**: November 29, 2025
- **Primary Sources Consulted**: 20+ authoritative sources
- **Date Range of Sources**: 2024-2025 (current)
- **LangGraph Versions Covered**: 0.2.x - Latest (0.6.x+)
- **Frameworks/Tools Evaluated**:
  - LangGraph (official)
  - LangChain core
  - OpenAI API
  - Azure OpenAI
  - Anthropic Claude
  - Pydantic v2

- **Key Findings**:
  1. Tool binding via `.bind_tools()` is the standard modern approach
  2. MessagesState is recommended over custom dicts
  3. Dependency injection (class wrappers) is best practice for tool-with-LLM pattern
  4. `.with_structured_output()` is the cleanest way to get Pydantic output
  5. Synchronous execution is fully supported and straightforward
  6. New context/config passing APIs make tool dependency injection cleaner

## Practical Code Patterns

### Complete Minimal Example

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import json

# 1. Define Pydantic output model
class AgentOutput(BaseModel):
    summary: str = Field(description="Summary of findings")
    insights: list[str] = Field(description="Key insights")
    recommendation: str = Field(description="Recommended action")

# 2. Define tools with LLM access
class AnalysisTool:
    def __init__(self, llm):
        self.llm = llm

    def __call__(self, query: str) -> str:
        """Analyze query and return insights."""
        response = self.llm.invoke(query)
        return response.content

# 3. Create instances
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
analysis_tool = AnalysisTool(llm)

# 4. Convert to LangChain tools
tools = [
    tool(analysis_tool, name="analyze", description="Analyze content")
]

llm_with_tools = llm.bind_tools(tools)

# 5. Define graph nodes
def agent_node(state: MessagesState) -> dict:
    """Call LLM with tools."""
    system_prompt = SystemMessage(
        content="You are a helpful analyst. Use tools to analyze requests."
    )
    messages = [system_prompt] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def respond_node(state: MessagesState) -> dict:
    """Generate structured final response."""
    llm_structured = llm.with_structured_output(AgentOutput)
    response = llm_structured.invoke(state["messages"])
    return {"messages": [response]}

# 6. Route based on tool calls
def should_continue(state: MessagesState) -> str:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return "respond"

# 7. Build graph
from langgraph.prebuilt import ToolNode

graph_builder = StateGraph(MessagesState)
graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", ToolNode(tools))
graph_builder.add_node("respond", respond_node)

graph_builder.add_edge(START, "agent")
graph_builder.add_conditional_edges(
    "agent",
    should_continue,
    {"tools": "tools", "respond": "respond"}
)
graph_builder.add_edge("tools", "agent")
graph_builder.add_edge("respond", END)

# 8. Compile and invoke
agent = graph_builder.compile()

result = agent.invoke({
    "messages": [HumanMessage(content="Analyze this project")]
})

print(result)
```

### Tool with Error Handling

```python
class RobustAnalysisTool:
    def __init__(self, llm):
        self.llm = llm
        self.logger = logging.getLogger(__name__)

    def __call__(self, query: str) -> str:
        """Analyze with error handling."""
        try:
            if not query or len(query) == 0:
                return "Error: Empty query provided"

            if len(query) > 5000:
                self.logger.warning(f"Query truncated from {len(query)} chars")
                query = query[:5000]

            self.logger.info(f"Analyzing query: {query[:100]}...")
            response = self.llm.invoke(query)
            result = response.content

            if not result:
                return "Error: No response from LLM"

            self.logger.info(f"Analysis completed, result length: {len(result)}")
            return result

        except Exception as e:
            self.logger.error(f"Analysis failed: {str(e)}")
            return f"Error: {str(e)}"
```

### Testing Example

```python
import pytest
from unittest.mock import MagicMock, patch

def test_agent_with_tool():
    # Create mock LLM
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "Analysis result"
    mock_llm.with_structured_output.return_value.invoke.return_value = AgentOutput(
        summary="Test",
        insights=["insight1"],
        recommendation="Act"
    )

    # Create tool
    tool_func = AnalysisTool(mock_llm)

    # Test tool directly
    result = tool_func("test query")
    assert result == "Analysis result"
    assert mock_llm.invoke.called

def test_agent_graph():
    llm = ChatOpenAI(model="gpt-4o-mini")
    agent = build_agent()  # Your build function

    result = agent.invoke({
        "messages": [HumanMessage(content="Test")]
    })

    assert "messages" in result
    assert len(result["messages"]) > 0
```

