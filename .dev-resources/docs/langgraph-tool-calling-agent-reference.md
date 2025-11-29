# LangGraph Tool-Calling Agent Reference

**Document Date**: November 2024
**LangGraph Version**: Latest (0.2+)
**API Providers**: OpenAI, Azure OpenAI, Anthropic

---

## Table of Contents
1. [Overview](#overview)
2. [Installation & Setup](#installation--setup)
3. [Core Architecture](#core-architecture)
4. [Tool Definitions](#tool-definitions)
5. [Tool Configuration & LLM Access](#tool-configuration--llm-access)
6. [Building StateGraph with Tools](#building-stategraph-with-tools)
7. [Structured Output with Pydantic](#structured-output-with-pydantic)
8. [Complete Working Example](#complete-working-example)
9. [Best Practices](#best-practices)
10. [Error Handling & Troubleshooting](#error-handling--troubleshooting)
11. [Additional Resources](#additional-resources)

---

## Overview

LangGraph is a framework for building stateful multi-step agent applications using LLMs. A tool-calling agent is an agent that can:

- Call multiple tools in sequence or based on LLM decision
- Maintain state across tool invocations
- Return structured output via Pydantic models
- Execute synchronously (blocking)

### Key Features

- **Synchronous execution** - Use `.invoke()` for synchronous calls
- **Tool binding** - Use `model.bind_tools()` to enable tool calling
- **State management** - TypedDict or Pydantic BaseModel for state schema
- **Structured output** - Use `with_structured_output()` or response schemas
- **Tool runtime access** - Tools can access LLM clients and state via `ToolRuntime`

---

## Installation & Setup

### Dependencies

```bash
pip install langgraph langchain-core langchain-openai
# OR for Azure OpenAI
pip install langgraph langchain-core langchain-openai
```

### Environment Variables

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Azure OpenAI
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_ENDPOINT="https://xxx.openai.azure.com/"
export AZURE_OPENAI_API_VERSION="2024-02-15-preview"
```

### Basic Imports

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from typing import Annotated, Sequence, TypedDict
from langgraph.graph.message import add_messages
import json
```

---

## Core Architecture

### ReAct Agent Pattern

A standard ReAct (Reasoning + Acting) agent has:

1. **Agent Node** - Calls the LLM with tools bound
2. **Tools Node** - Executes selected tools and returns results
3. **Router** - Decides whether to continue or end based on LLM response

```
[Start] → [Agent] → [Should Continue?]
                         ↓
                    [Tools] ← No → [End]
                         ↓
                      Yes (loop back to Agent)
```

### State Schema

The agent maintains state as it executes. Two approaches:

**Option A: TypedDict (simpler, no validation)**
```python
from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
```

**Option B: Pydantic BaseModel (with validation)**
```python
from pydantic import BaseModel, Field
from typing import Annotated, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(BaseModel):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str = Field(default="")
    context: dict = Field(default_factory=dict)
```

**Important**: Use `add_messages` reducer - it prevents message duplication

---

## Tool Definitions

### Basic Tool with @tool Decorator

The simplest approach. The `@tool` decorator converts a Python function into a LangChain tool.

```python
from langchain_core.tools import tool

@tool
def search_database(query: str, limit: int = 10) -> str:
    """Search the customer database for records matching the query.

    Args:
        query: Search terms to look for
        limit: Maximum number of results to return
    """
    # Your implementation
    return f"Found {limit} results for '{query}'"
```

**Key Points:**
- **Docstring is required** - Used as tool description for the LLM
- **Type hints are required** - Define the input schema
- **Return type must be `str`** - String insights, not structured data
- **Tool name** - Derived from function name (can override with `@tool("custom_name")`)

### Tool with Custom Name and Description

```python
@tool("web_search", description="Search the web for current information")
def search(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"
```

### Reserved Parameter Names

These parameter names are **reserved** and will cause runtime errors:
- `config` - Reserved for RunnableConfig
- `runtime` - Reserved for ToolRuntime

### Tool with LLM Client Access

Tools can access an LLM client to interpret data internally using `ToolRuntime`:

```python
from langchain_core.tools import tool, ToolRuntime
from typing import Annotated

@tool
def analyze_sentiment(
    text: str,
    runtime: Annotated[ToolRuntime, "ToolRuntime"] = None
) -> str:
    """Analyze sentiment of the given text using LLM.

    Args:
        text: The text to analyze
    """
    if runtime is None:
        return "Unable to access LLM client"

    # Access the LLM from context/config (see Configuration section)
    # For now, return a placeholder
    return f"Analyzed: {text}"
```

**Note**: This requires passing the LLM client via configuration (see below).

---

## Tool Configuration & LLM Access

### Approach 1: Using ToolRuntime with Config

Tools can access configuration passed during graph invocation:

```python
from langchain_core.tools import tool, ToolRuntime
from typing import Annotated

@tool
def interpret_data(
    data: str,
    runtime: Annotated[ToolRuntime, "ToolRuntime"] = None
) -> str:
    """Interpret data using LLM insight.

    Uses the LLM client from ToolRuntime to generate insights.
    """
    if not runtime or not runtime.context:
        return "Unable to access LLM client"

    llm_client = runtime.context.get("llm_client")
    if not llm_client:
        return "LLM client not configured"

    # Use the LLM client
    result = llm_client.invoke(f"Provide insight on: {data}")
    return result.content
```

### Approach 2: Passing Context During Invocation

Define a context dataclass and pass it when invoking the agent:

```python
from dataclasses import dataclass
from langchain_core.tools import tool, ToolRuntime
from typing import Annotated

@dataclass
class ToolContext:
    llm_client: object
    api_key: str

@tool
def process_with_llm(
    query: str,
    runtime: Annotated[ToolRuntime[ToolContext], "ToolRuntime"] = None
) -> str:
    """Process query using LLM from context."""
    if not runtime:
        return "Runtime not available"

    context = runtime.context
    if not context:
        return "Context not configured"

    # Use the LLM client from context
    result = context.llm_client.invoke(query)
    return result.content

# When invoking the agent:
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini")
context = ToolContext(llm_client=llm, api_key="your-key")

# Pass context during invocation (see Complete Example below)
```

### Approach 3: Closure Pattern (Recommended for Tools)

Tools are typically created with closures to have access to LLM clients:

```python
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

def create_analysis_tools(llm_client: ChatOpenAI):
    """Factory function to create tools with LLM access."""

    @tool
    def sentiment_analysis(text: str) -> str:
        """Analyze sentiment of text using LLM."""
        result = llm_client.invoke(
            f"Analyze sentiment (positive/negative/neutral) of: {text}"
        )
        return result.content

    @tool
    def content_summary(text: str) -> str:
        """Summarize content using LLM."""
        result = llm_client.invoke(
            f"Summarize this content in 2-3 sentences: {text}"
        )
        return result.content

    @tool
    def entity_extraction(text: str) -> str:
        """Extract entities from text using LLM."""
        result = llm_client.invoke(
            f"Extract named entities (people, places, organizations) from: {text}"
        )
        return result.content

    return [sentiment_analysis, content_summary, entity_extraction]

# Usage:
llm = ChatOpenAI(model="gpt-4o-mini")
tools = create_analysis_tools(llm)
```

---

## Building StateGraph with Tools

### Step 1: Define State

```python
from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
```

### Step 2: Initialize LLM and Bind Tools

```python
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

@tool
def get_weather(location: str) -> str:
    """Get weather for a location."""
    return f"Sunny in {location}"

tools = [get_weather]
llm_with_tools = llm.bind_tools(tools)
```

### Step 3: Define Nodes

```python
from langchain_core.messages import ToolMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
import json

tools_by_name = {tool.name: tool for tool in tools}

def agent_node(state: AgentState, config: RunnableConfig):
    """Call the LLM with tools bound."""
    system_prompt = SystemMessage(
        "You are a helpful assistant. Use tools when needed."
    )
    response = llm_with_tools.invoke(
        [system_prompt] + list(state["messages"]),
        config
    )
    return {"messages": [response]}

def tools_node(state: AgentState):
    """Execute tools and return results."""
    outputs = []
    for tool_call in state["messages"][-1].tool_calls:
        tool_result = tools_by_name[tool_call["name"]].invoke(
            tool_call["args"]
        )
        outputs.append(
            ToolMessage(
                content=json.dumps(tool_result),
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            )
        )
    return {"messages": outputs}

def should_continue(state: AgentState) -> str:
    """Determine if we should continue calling tools."""
    messages = state["messages"]
    last_message = messages[-1]

    # If no tool calls, we're done
    if not last_message.tool_calls:
        return "end"
    return "continue"
```

### Step 4: Build and Compile Graph

```python
from langgraph.graph import StateGraph, END

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)

# Set entry point
workflow.set_entry_point("agent")

# Add edges
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "tools",
        "end": END,
    },
)
workflow.add_edge("tools", "agent")

# Compile
graph = workflow.compile()
```

### Step 5: Execute Agent

```python
from langchain_core.messages import HumanMessage

# Synchronous execution
response = graph.invoke({
    "messages": [HumanMessage(content="What's the weather in SF?")]
})

# Access final messages
for message in response["messages"]:
    print(f"{message.__class__.__name__}: {message.content}")
```

---

## Structured Output with Pydantic

### Approach 1: Using create_react_agent with response_format (Simplest)

```python
from pydantic import BaseModel, Field
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

class WeatherResponse(BaseModel):
    location: str = Field(description="The location")
    conditions: str = Field(description="Weather conditions")
    temperature: int = Field(description="Temperature in Celsius")

llm = ChatOpenAI(model="gpt-4o-mini")

agent = create_react_agent(
    llm,
    tools=[get_weather],  # Your tools
    response_format=WeatherResponse
)

response = agent.invoke({
    "messages": [{"role": "user", "content": "What's the weather in SF?"}]
})

# Access structured output
structured = response.get("structured_response")
```

### Approach 2: Adding Response Node to Custom Graph

For full control, add a final node that formats output:

```python
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

class AnalysisResult(BaseModel):
    summary: str = Field(description="Summary of analysis")
    insights: list[str] = Field(description="Key insights")
    confidence: float = Field(description="Confidence level 0-1")

def response_node(state: AgentState) -> dict:
    """Format final response with structured output."""
    # Extract insights from messages
    last_message = state["messages"][-1]

    # Use LLM to structure the output
    llm_with_schema = llm.with_structured_output(AnalysisResult)
    result = llm_with_schema.invoke(last_message.content)

    return {
        "messages": [],  # or add a final message
        "structured_output": result.model_dump()
    }

# Update state to include structured output
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    structured_output: dict = {}

# Add response node before END
workflow.add_node("respond", response_node)
workflow.add_edge("tools", "agent")  # Keep looping for tools
workflow.add_edge("agent", "respond")  # Go to response before END
workflow.add_edge("respond", END)
```

### Approach 3: Using with_structured_output on LLM

```python
from pydantic import BaseModel

class FinalResponse(BaseModel):
    answer: str
    explanation: str
    confidence_score: float

# Create structured LLM
structured_llm = llm.with_structured_output(FinalResponse)

# Use in agent
result = structured_llm.invoke("Your query here")
# result is now a FinalResponse instance
print(result.answer)
print(result.explanation)
```

---

## Complete Working Example

### 6-Tool Analysis Agent with Structured Output

```python
"""
Complete example: 6-tool agent that analyzes text with structured output.
Each tool uses an internal LLM to generate insights.
"""

from pydantic import BaseModel, Field
from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.runnables import RunnableConfig
import json
import os

# ============================================================================
# 1. SETUP & CONFIGURATION
# ============================================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable not set")

# Main LLM for the agent
main_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=OPENAI_API_KEY)

# Secondary LLM for tool insights (can be same as main_llm)
insight_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, api_key=OPENAI_API_KEY)

# ============================================================================
# 2. TOOL DEFINITIONS (Factory Pattern with LLM Access)
# ============================================================================

def create_analysis_tools(llm_client: ChatOpenAI):
    """Factory function to create tools with internal LLM access."""

    @tool
    def sentiment_analysis(text: str) -> str:
        """Analyze emotional sentiment of the text.

        Returns string insight about the sentiment.
        """
        prompt = f"""Analyze the sentiment of this text and provide a brief insight:

{text}

Provide a one-line sentiment assessment (positive/negative/neutral) with a brief reason."""

        result = llm_client.invoke(prompt)
        return result.content

    @tool
    def entity_extraction(text: str) -> str:
        """Extract named entities (people, places, organizations) from text.

        Returns string with extracted entities and their types.
        """
        prompt = f"""Extract all named entities from this text:

{text}

List each entity with its type (PERSON, LOCATION, ORGANIZATION, DATE, etc.)"""

        result = llm_client.invoke(prompt)
        return result.content

    @tool
    def key_topics(text: str) -> str:
        """Identify key topics and themes discussed in the text.

        Returns string summary of main topics.
        """
        prompt = f"""Identify the key topics and themes in this text:

{text}

List the 3-5 most important topics with brief explanations."""

        result = llm_client.invoke(prompt)
        return result.content

    @tool
    def readability_analysis(text: str) -> str:
        """Analyze text readability and complexity.

        Returns string assessment of readability.
        """
        prompt = f"""Assess the readability and complexity of this text:

{text}

Provide assessment of: reading level, sentence complexity, vocabulary difficulty."""

        result = llm_client.invoke(prompt)
        return result.content

    @tool
    def content_summary(text: str) -> str:
        """Create a concise summary of the text content.

        Returns string with key points summarized.
        """
        prompt = f"""Summarize this text in 2-3 bullet points:

{text}"""

        result = llm_client.invoke(prompt)
        return result.content

    @tool
    def bias_detection(text: str) -> str:
        """Detect potential biases or one-sided perspectives in the text.

        Returns string assessment of any detected biases.
        """
        prompt = f"""Analyze this text for potential biases or one-sided perspectives:

{text}

Identify any apparent biases and suggest what alternative viewpoints might be missing."""

        result = llm_client.invoke(prompt)
        return result.content

    return [
        sentiment_analysis,
        entity_extraction,
        key_topics,
        readability_analysis,
        content_summary,
        bias_detection,
    ]

# Create tools with insight LLM
tools = create_analysis_tools(insight_llm)

# ============================================================================
# 3. STATE DEFINITION
# ============================================================================

class AgentState(TypedDict):
    """State of the analysis agent."""
    messages: Annotated[Sequence[BaseMessage], add_messages]

# ============================================================================
# 4. BIND TOOLS TO MAIN LLM
# ============================================================================

llm_with_tools = main_llm.bind_tools(tools)

# ============================================================================
# 5. NODE DEFINITIONS
# ============================================================================

tools_by_name = {tool.name: tool for tool in tools}

def agent_node(state: AgentState, config: RunnableConfig):
    """Call the agent LLM with available tools."""
    system_prompt = SystemMessage(
        """You are a comprehensive text analysis assistant.

You have access to 6 analysis tools:
1. sentiment_analysis - Analyze emotional tone
2. entity_extraction - Extract named entities
3. key_topics - Identify main topics
4. readability_analysis - Assess complexity
5. content_summary - Summarize content
6. bias_detection - Find biases

Use all available tools to thoroughly analyze the provided text.
Start by using each tool once to gather all insights."""
    )

    response = llm_with_tools.invoke(
        [system_prompt] + list(state["messages"]),
        config
    )

    print(f"Agent response: {response}")
    return {"messages": [response]}

def tools_node(state: AgentState):
    """Execute requested tools and return results."""
    outputs = []
    last_message = state["messages"][-1]

    if not hasattr(last_message, 'tool_calls'):
        return {"messages": outputs}

    for tool_call in last_message.tool_calls:
        print(f"Executing tool: {tool_call['name']} with args: {tool_call['args']}")

        tool_result = tools_by_name[tool_call["name"]].invoke(tool_call["args"])

        outputs.append(
            ToolMessage(
                content=tool_result,
                name=tool_call["name"],
                tool_call_id=tool_call["id"],
            )
        )

    return {"messages": outputs}

def should_continue(state: AgentState) -> str:
    """Determine if we should continue with tools or end."""
    messages = state["messages"]
    last_message = messages[-1]

    if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
        return "end"
    return "continue"

# ============================================================================
# 6. OUTPUT SCHEMA & RESPONSE FORMATTING
# ============================================================================

class TextAnalysisResult(BaseModel):
    """Structured output for text analysis."""
    original_text_preview: str = Field(
        description="First 100 characters of analyzed text"
    )
    sentiment: str = Field(description="Overall sentiment assessment")
    entities: list[str] = Field(description="List of extracted entities")
    key_topics: list[str] = Field(description="Main topics identified")
    readability_level: str = Field(description="Text readability assessment")
    summary: str = Field(description="Concise summary of content")
    potential_biases: list[str] = Field(description="Identified biases if any")

# ============================================================================
# 7. BUILD AND COMPILE GRAPH
# ============================================================================

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)

# Set entry point
workflow.set_entry_point("agent")

# Add edges
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "tools",
        "end": END,
    },
)
workflow.add_edge("tools", "agent")

# Compile the graph
graph = workflow.compile()

# ============================================================================
# 8. EXECUTION
# ============================================================================

def run_analysis(text: str):
    """Run the analysis agent on the provided text."""
    print("\n" + "="*70)
    print("STARTING TEXT ANALYSIS")
    print("="*70)

    # Invoke the agent synchronously
    response = graph.invoke({
        "messages": [HumanMessage(content=text)]
    })

    print("\n" + "="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)

    # Extract insights from messages
    messages = response["messages"]

    print("\nMessages exchanged:")
    for i, msg in enumerate(messages):
        print(f"\n[{i}] {msg.__class__.__name__}:")
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            print(f"    Tool calls: {[tc['name'] for tc in msg.tool_calls]}")
        elif hasattr(msg, 'content'):
            content_preview = msg.content[:200] if len(msg.content) > 200 else msg.content
            print(f"    {content_preview}")

    return response

# ============================================================================
# 9. EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    sample_text = """
    Artificial Intelligence is transforming the world. Machine learning models are becoming
    increasingly sophisticated and are being deployed in critical applications from healthcare
    to finance. However, concerns about AI bias and ethical implications are growing. Some argue
    that AI will replace human workers, while others believe it will create new opportunities.
    The truth is likely somewhere in between, though the debate remains politically charged with
    supporters and critics often talking past each other.
    """

    result = run_analysis(sample_text)

    # Print all tool results
    print("\n" + "="*70)
    print("TOOL RESULTS SUMMARY")
    print("="*70)

    for msg in result["messages"]:
        if isinstance(msg, ToolMessage):
            print(f"\n{msg.name}:\n{msg.content}\n")
```

### Running the Example

```bash
export OPENAI_API_KEY="sk-..."
python your_script.py
```

---

## Best Practices

### 1. Tool Design

**Do:**
- Return string insights, not structured data
- Include comprehensive docstrings with argument descriptions
- Use type hints for all parameters
- Make tools single-responsibility (one thing well)
- Include tool descriptions that help LLM decide when to use it

**Don't:**
- Return raw JSON or Python dicts
- Skip docstrings or type hints
- Create overly broad tools that do multiple things
- Use reserved parameter names (`config`, `runtime`)

### 2. LLM Access in Tools

**Best Practice: Use Closure Pattern**
```python
def create_tools(llm):
    @tool
    def my_tool(input: str) -> str:
        result = llm.invoke(input)
        return result.content
    return [my_tool]
```

**Why:** Clean separation, easy to test, no magic with ToolRuntime

### 3. State Management

**Use TypedDict for simple cases:**
```python
class State(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
```

**Use Pydantic for validation:**
```python
class State(BaseModel):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
```

### 4. Error Handling in Tools

```python
@tool
def safe_tool(input: str) -> str:
    """Tool with error handling."""
    try:
        result = process_input(input)
        return str(result)
    except Exception as e:
        # Return error as string insight
        return f"Error processing input: {str(e)}"
```

### 5. Logging

```python
import logging

logger = logging.getLogger(__name__)

def agent_node(state: AgentState, config: RunnableConfig):
    logger.info(f"Agent invoked with {len(state['messages'])} messages")
    response = llm_with_tools.invoke(state["messages"], config)
    logger.debug(f"Agent response: {response}")
    return {"messages": [response]}
```

### 6. Configuration for Azure OpenAI

```python
from langchain_openai import AzureChatOpenAI

llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
    api_version="2024-02-15-preview",
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
)

# Rest of code is identical
llm_with_tools = llm.bind_tools(tools)
```

---

## Error Handling & Troubleshooting

### Common Errors

#### 1. "AttributeError: 'OpenAI' object has no attribute 'bind_tools'"

**Cause:** Using `OpenAI` instead of `ChatOpenAI`

**Fix:**
```python
# Wrong
from langchain_openai import OpenAI
llm = OpenAI()

# Correct
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o-mini")
```

#### 2. "Tool 'x' is missing docstring"

**Cause:** Missing docstring on tool function

**Fix:**
```python
@tool  # Wrong - missing docstring
def my_tool(input: str) -> str:
    return input

@tool  # Correct - has docstring
def my_tool(input: str) -> str:
    """Process input and return result."""
    return input
```

#### 3. "reserved argument name 'config' or 'runtime'"

**Cause:** Using reserved parameter names

**Fix:**
```python
# Wrong
@tool
def my_tool(config: str) -> str:
    return config

# Correct - rename parameter
@tool
def my_tool(settings: str) -> str:
    return settings

# If you need ToolRuntime, use proper annotation
@tool
def my_tool(
    input: str,
    runtime: Annotated[ToolRuntime, "ToolRuntime"] = None
) -> str:
    return input
```

#### 4. Tool not appearing in agent calls

**Cause:** Tools not bound to LLM or not passed correctly

**Fix:**
```python
# Ensure tools are bound
llm_with_tools = llm.bind_tools(tools)

# Ensure they're used in agent node
response = llm_with_tools.invoke(state["messages"], config)
```

#### 5. "messages are not being reduced"

**Cause:** Not using `add_messages` reducer

**Fix:**
```python
# Wrong
class State(TypedDict):
    messages: Sequence[BaseMessage]

# Correct
class State(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
```

### Debugging Tips

1. **Enable LangSmith tracing** - Visualize agent execution
   ```python
   os.environ["LANGSMITH_API_KEY"] = "..."
   os.environ["LANGCHAIN_TRACING_V2"] = "true"
   ```

2. **Add extensive logging**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

3. **Print state at each node**
   ```python
   def agent_node(state: AgentState):
       print(f"Agent state: {state}")
       return response
   ```

4. **Test tools individually**
   ```python
   result = my_tool.invoke({"input": "test"})
   print(result)
   ```

---

## Additional Resources

### Official Documentation
- [LangGraph Official Documentation](https://langchain-ai.github.io/langgraph/)
- [LangChain Tools Reference](https://docs.langchain.com/oss/python/langchain/tools)
- [How to create a ReAct agent from scratch](https://langchain-ai.github.io/langgraph/how-tos/react-agent-from-scratch/)
- [How to force tool-calling agent to structure output](https://langchain-ai.github.io/langgraph/how-tos/react-agent-structured-output/)
- [Tool Runtime Documentation](https://python.langchain.com/docs/how_to/tool_runtime/)

### Key Concepts
- [ReAct Agent Pattern](https://langchain-ai.github.io/langgraph/concepts/agentic_concepts/)
- [StateGraph & Message Reducers](https://langchain-ai.github.io/langgraph/concepts/low_level/#reducers)
- [Structured Output with Pydantic](https://docs.langchain.com/oss/python/langchain/structured-output)

### Azure OpenAI Integration
- [Build Tool-Calling Agents with Azure OpenAI](https://techcommunity.microsoft.com/blog/educatordeveloperblog/how-to-build-tool-calling-agents-with-azure-openai-and-lang-graph/4391136)
- [AzureChatOpenAI API Reference](https://python.langchain.com/api_reference/openai/chat_models/langchain_openai.chat_models.azure.AzureChatOpenAI.html)

### Community Resources
- [Building Tool Calling Agents with LangGraph: A Complete Guide](https://sangeethasaravanan.medium.com/building-tool-calling-agents-with-langgraph-a-complete-guide-ebdcdea8f475)
- [Mastering LLM Tools in LangGraph: A Guide to the 3 Core Patterns](https://medium.com/@abhinavsaxena_17855/mastering-llm-tools-in-langgraph-a-guide-to-the-3-core-patterns-a48f31653f11)
- [LangGraph: Build Stateful AI Agents in Python](https://realpython.com/langgraph-python/)

---

## Quick Reference: Key Imports

```python
# Core LangGraph
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition, create_react_agent
from langgraph.types import Command

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

**Last Updated**: November 2024
**LangGraph Version**: 0.2+
**Status**: Production Ready
