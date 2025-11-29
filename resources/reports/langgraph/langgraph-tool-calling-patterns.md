# LangGraph Tool-Calling Patterns: Practical Code Examples

## Quick Reference Patterns

This document provides copy-paste ready patterns for common tool-calling scenarios in LangGraph.

---

## Pattern 1: Basic Tool Definition

### Single Tool with Simple Logic
```python
from langchain_core.tools import tool

@tool
def search_documents(query: str) -> str:
    """Search through documents for relevant information.

    Args:
        query: The search query string

    Returns:
        Search results as a formatted string
    """
    # Implementation
    results = perform_search(query)
    return f"Found {len(results)} results:\n" + "\n".join(results)
```

### Tool Returning Insights
```python
@tool
def extract_key_concepts(text: str) -> str:
    """Extract key concepts from text.

    Args:
        text: Input text to analyze

    Returns:
        Comma-separated list of key concepts
    """
    concepts = analyze_text(text)
    return ", ".join(concepts)
```

---

## Pattern 2: Tool With Internal LLM (Dependency Injection)

### Class-Based Tool (Recommended)
```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import logging

logger = logging.getLogger(__name__)

class SummarizationTool:
    """Tool that uses LLM internally to summarize text."""

    def __init__(self, llm):
        """Initialize with an LLM instance.

        Args:
            llm: LangChain chat model instance
        """
        self.llm = llm
        self.name = "summarize"
        self.description = "Summarize long text into key points"

    def __call__(self, text: str) -> str:
        """Execute the tool.

        Args:
            text: Text to summarize

        Returns:
            Summary as string
        """
        try:
            logger.info(f"Summarizing text of length {len(text)}")

            prompt = f"""Please summarize the following text into 3-5 key points:

{text}

Provide only the key points, one per line."""

            response = self.llm.invoke(prompt)
            summary = response.content

            logger.info(f"Summary generated: {len(summary)} chars")
            return summary

        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return f"Error: Could not summarize text - {str(e)}"


class AnalysisTool:
    """Tool that analyzes content using LLM."""

    def __init__(self, llm):
        self.llm = llm
        self.name = "analyze"
        self.description = "Perform deep analysis on content"

    def __call__(self, content: str) -> str:
        try:
            logger.info(f"Analyzing content of length {len(content)}")

            prompt = f"""Analyze the following content and provide insights:
1. Main themes
2. Potential risks
3. Opportunities

Content:
{content}"""

            response = self.llm.invoke(prompt)
            analysis = response.content

            return analysis

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return f"Error: Could not analyze - {str(e)}"


class ResearchTool:
    """Tool that researches topics using LLM."""

    def __init__(self, llm):
        self.llm = llm
        self.name = "research"
        self.description = "Research a topic and provide findings"

    def __call__(self, topic: str) -> str:
        try:
            logger.info(f"Researching topic: {topic}")

            prompt = f"""Research the topic: {topic}

Provide:
1. Definition/Overview
2. Current status/trends
3. Key players/resources
4. Challenges"""

            response = self.llm.invoke(prompt)
            findings = response.content

            return findings

        except Exception as e:
            logger.error(f"Research failed: {e}")
            return f"Error: Could not research - {str(e)}"
```

### Converting Tool Classes to LangChain Tools
```python
from langchain_core.tools import tool

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Create tool instances
summarize_tool = SummarizationTool(llm)
analysis_tool = AnalysisTool(llm)
research_tool = ResearchTool(llm)

# Convert to LangChain tools
tools = [
    tool(
        func=summarize_tool,
        name=summarize_tool.name,
        description=summarize_tool.description,
    ),
    tool(
        func=analysis_tool,
        name=analysis_tool.name,
        description=analysis_tool.description,
    ),
    tool(
        func=research_tool,
        name=research_tool.name,
        description=research_tool.description,
    ),
]
```

### Using functools.partial (Lightweight)
```python
from functools import partial
from langchain_core.tools import tool

def perform_summarization(text: str, llm) -> str:
    """Function-based tool implementation."""
    prompt = f"Summarize: {text}"
    response = llm.invoke(prompt)
    return response.content

def perform_classification(text: str, llm) -> str:
    """Classify text using LLM."""
    prompt = f"Classify this text and explain why: {text}"
    response = llm.invoke(prompt)
    return response.content

# Create bound functions
llm = ChatOpenAI(model="gpt-4o-mini")

summarize_partial = partial(perform_summarization, llm=llm)
classify_partial = partial(perform_classification, llm=llm)

# Register as tools
tools = [
    tool(
        func=summarize_partial,
        name="summarize",
        description="Summarize text into key points"
    ),
    tool(
        func=classify_partial,
        name="classify",
        description="Classify and explain text"
    ),
]
```

---

## Pattern 3: Complete Agent Graph

### Minimal Agent
```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from typing import Literal

# 1. Define tools
@tool
def math_tool(expression: str) -> str:
    """Calculate a mathematical expression."""
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error: {e}"

# 2. Setup LLM and tools
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
tools = [math_tool]
llm_with_tools = llm.bind_tools(tools)

# 3. Define graph nodes
def agent(state: MessagesState) -> dict:
    """Main agent node."""
    messages = [
        SystemMessage(content="You are a helpful assistant.")
    ] + state["messages"]

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state: MessagesState) -> Literal["tools", END]:
    """Route based on tool calls."""
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

# 4. Build graph
builder = StateGraph(MessagesState)
builder.add_node("agent", agent)
builder.add_node("tools", ToolNode(tools))

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    END: END,
})
builder.add_edge("tools", "agent")

# 5. Compile
graph = builder.compile()

# 6. Run
result = graph.invoke({
    "messages": [HumanMessage(content="What is 15 * 4?")]
})

print("Final message:", result["messages"][-1])
```

### Agent with 6 Tools (Your Scenario)
```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from typing import Literal
import logging

logger = logging.getLogger(__name__)

# === Define 6 Tools ===

class ComparisonTool:
    def __init__(self, llm):
        self.llm = llm
        self.name = "compare"
        self.description = "Compare two items and provide insights"

    def __call__(self, items: str) -> str:
        prompt = f"Compare these items and explain differences: {items}"
        return self.llm.invoke(prompt).content

class TrendAnalyzerTool:
    def __init__(self, llm):
        self.llm = llm
        self.name = "analyze_trends"
        self.description = "Analyze trends in data"

    def __call__(self, data: str) -> str:
        prompt = f"Analyze trends in: {data}"
        return self.llm.invoke(prompt).content

class SentimentAnalyzerTool:
    def __init__(self, llm):
        self.llm = llm
        self.name = "sentiment"
        self.description = "Analyze sentiment"

    def __call__(self, text: str) -> str:
        prompt = f"Analyze sentiment: {text}"
        return self.llm.invoke(prompt).content

class RecommenderTool:
    def __init__(self, llm):
        self.llm = llm
        self.name = "recommend"
        self.description = "Make recommendations"

    def __call__(self, context: str) -> str:
        prompt = f"Make recommendations for: {context}"
        return self.llm.invoke(prompt).content

class ExplanationTool:
    def __init__(self, llm):
        self.llm = llm
        self.name = "explain"
        self.description = "Explain concepts"

    def __call__(self, concept: str) -> str:
        prompt = f"Explain: {concept}"
        return self.llm.invoke(prompt).content

class ExtractorTool:
    def __init__(self, llm):
        self.llm = llm
        self.name = "extract"
        self.description = "Extract key information"

    def __call__(self, text: str) -> str:
        prompt = f"Extract key information from: {text}"
        return self.llm.invoke(prompt).content

# === Setup ===

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Instantiate tools with LLM
tools_instances = [
    ComparisonTool(llm),
    TrendAnalyzerTool(llm),
    SentimentAnalyzerTool(llm),
    RecommenderTool(llm),
    ExplanationTool(llm),
    ExtractorTool(llm),
]

# Convert to LangChain tools
from langchain_core.tools import tool as create_tool

tools = [
    create_tool(
        func=t,
        name=t.name,
        description=t.description,
    )
    for t in tools_instances
]

llm_with_tools = llm.bind_tools(tools)

# === Define Graph Nodes ===

def agent_node(state: MessagesState) -> dict:
    """Agent decides what to do."""
    logger.info(f"Agent node: {len(state['messages'])} messages")

    messages = [
        SystemMessage(content="""You are an expert analyst with access to 6 tools:
1. compare - Compare items
2. analyze_trends - Analyze data trends
3. sentiment - Analyze sentiment
4. recommend - Make recommendations
5. explain - Explain concepts
6. extract - Extract information

Use these tools to help answer user queries comprehensively.""")
    ] + state["messages"]

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state: MessagesState) -> Literal["tools", "respond"]:
    """Route to tools or final response."""
    last_message = state["messages"][-1]

    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        logger.info(f"Agent wants to use tools: {[tc.get('name') for tc in last_message.tool_calls]}")
        return "tools"

    logger.info("Agent providing final response")
    return "respond"

def respond_node(state: MessagesState) -> dict:
    """Final response generation."""
    logger.info("Respond node: generating final answer")
    return {"messages": []}  # Graph ends

# === Build Graph ===

builder = StateGraph(MessagesState)

# Add nodes
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools))
builder.add_node("respond", respond_node)

# Add edges
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    "respond": "respond",
})
builder.add_edge("tools", "agent")
builder.add_edge("respond", END)

# === Compile and Run ===

graph = builder.compile()

# Enable tracing
result = graph.invoke(
    {"messages": [HumanMessage(content="Compare Python and JavaScript for web development")]},
    {"recursion_limit": 25}
)

print("\n=== Final Result ===")
for msg in result["messages"]:
    if isinstance(msg, HumanMessage):
        print(f"User: {msg.content}")
    elif isinstance(msg, AIMessage):
        print(f"Agent: {msg.content}")
```

---

## Pattern 4: Structured Output

### Define Output Schema
```python
from pydantic import BaseModel, Field
from typing import List

class AnalysisResult(BaseModel):
    """Structured output from agent analysis."""

    summary: str = Field(
        description="Brief summary of findings",
        min_length=1,
        max_length=500
    )

    key_points: List[str] = Field(
        description="List of key insights discovered",
        min_items=1,
        max_items=10
    )

    risk_assessment: str = Field(
        description="Assessment of risks or concerns",
        default="No significant risks identified"
    )

    recommendations: List[str] = Field(
        description="Recommended actions",
        min_items=1,
        max_items=5
    )

    confidence_level: float = Field(
        description="Confidence in the analysis (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
        default=0.8
    )

    metadata: dict = Field(
        description="Additional metadata",
        default_factory=dict
    )
```

### Response Node with Structured Output
```python
from langchain_core.messages import HumanMessage

def respond_with_structure(state: MessagesState, llm) -> dict:
    """Generate structured response."""
    logger.info("Generating structured response")

    # Use LLM with structured output
    llm_structured = llm.with_structured_output(AnalysisResult)

    try:
        # Build a focused prompt for final response
        conversation = "\n".join([
            f"{'User' if isinstance(m, HumanMessage) else 'Agent'}: {m.content}"
            for m in state["messages"]
        ])

        final_prompt = f"""Based on the conversation below, provide a structured analysis:

{conversation}

Provide your response in the required JSON structure with all fields."""

        # Create a message for the LLM
        from langchain_core.messages import SystemMessage

        messages = [
            SystemMessage(content="You are an expert analyst. Provide structured insights."),
            HumanMessage(content=final_prompt)
        ]

        result = llm_structured.invoke(messages)

        logger.info(f"Structured response generated: {type(result)}")
        logger.info(f"Confidence: {result.confidence_level}")

        # Return as dict with JSON serialization
        return {
            "messages": [
                HumanMessage(content=result.model_dump_json(indent=2))
            ]
        }

    except Exception as e:
        logger.error(f"Failed to generate structured output: {e}")

        # Fallback response
        fallback = AnalysisResult(
            summary="Analysis encountered an error",
            key_points=["Unable to complete analysis"],
            recommendations=["Review and retry"],
            confidence_level=0.0,
            metadata={"error": str(e)}
        )

        return {
            "messages": [
                HumanMessage(content=fallback.model_dump_json(indent=2))
            ]
        }
```

### Use in Graph
```python
# In your graph setup
def should_continue(state: MessagesState) -> Literal["tools", "respond"]:
    last_message = state["messages"][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    return "respond"

builder = StateGraph(MessagesState)
# ... add other nodes ...

# Add structured response node
builder.add_node("respond", lambda state: respond_with_structure(state, llm))

builder.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    "respond": "respond",
})
```

---

## Pattern 5: Error Handling and Retry

### Robust Tool Wrapper
```python
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

logger = logging.getLogger(__name__)

class RobustAnalysisTool:
    """Tool with comprehensive error handling."""

    def __init__(self, llm, max_retries: int = 3):
        self.llm = llm
        self.max_retries = max_retries
        self.name = "robust_analyze"
        self.description = "Analyze with error handling"
        self.call_count = 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _invoke_llm(self, prompt: str) -> str:
        """Call LLM with retry logic."""
        response = self.llm.invoke(prompt)
        return response.content

    def __call__(self, text: str) -> str:
        """Execute with error handling."""
        self.call_count += 1

        try:
            # Input validation
            if not text or not isinstance(text, str):
                logger.warning("Invalid input: empty or non-string")
                return "Error: Input must be non-empty string"

            if len(text) > 10000:
                logger.warning(f"Input truncated from {len(text)} to 10000 chars")
                text = text[:10000]

            logger.info(f"Tool call #{self.call_count}: analyzing {len(text)} chars")

            # Invoke with retry
            prompt = f"Analyze: {text}"
            result = self._invoke_llm(prompt)

            # Output validation
            if not result or len(result) == 0:
                logger.warning("Empty result from LLM")
                return "No meaningful analysis produced"

            logger.info(f"Analysis successful: {len(result)} chars output")
            return result

        except Exception as e:
            logger.error(f"Tool execution failed after retries: {e}")
            return f"Error: Analysis failed - {str(e)}"
```

### Agent with Error Handling
```python
def agent_with_fallback(state: MessagesState) -> dict:
    """Agent node with fallback."""
    try:
        logger.info("Agent invocation started")
        response = llm_with_tools.invoke(state["messages"])
        logger.info("Agent response generated")
        return {"messages": [response]}

    except Exception as e:
        logger.error(f"Agent failed: {e}")

        from langchain_core.messages import AIMessage

        fallback_response = AIMessage(
            content="I encountered an error while processing. Please try again."
        )
        return {"messages": [fallback_response]}
```

---

## Pattern 6: Testing

### Unit Test Tools
```python
import pytest
from unittest.mock import MagicMock, patch

class TestAnalysisTool:
    """Test suite for analysis tool."""

    def test_tool_with_mock_llm(self):
        """Test tool with mocked LLM."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value.content = "Analysis result"

        tool = AnalysisTool(mock_llm)
        result = tool("test input")

        assert result == "Analysis result"
        assert mock_llm.invoke.called

    def test_tool_error_handling(self):
        """Test tool handles errors."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM failed")

        tool = AnalysisTool(mock_llm)
        result = tool("test input")

        assert "Error" in result

    def test_tool_validates_input(self):
        """Test tool validates input."""
        mock_llm = MagicMock()
        tool = AnalysisTool(mock_llm)

        result = tool("")  # Empty input
        assert "Error" in result
        assert not mock_llm.invoke.called

    def test_tool_truncates_long_input(self):
        """Test tool truncates long input."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value.content = "Result"

        tool = AnalysisTool(mock_llm)
        long_text = "x" * 20000
        result = tool(long_text)

        # Verify truncation
        called_text = mock_llm.invoke.call_args[0][0]
        assert len(called_text) <= 10100  # Prompt + truncated text
```

### Integration Test Graph
```python
def test_agent_graph_end_to_end():
    """Test full agent graph."""
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model="gpt-4o-mini")
    tools_instances = [AnalysisTool(llm)]

    from langchain_core.tools import tool as create_tool

    tools = [
        create_tool(
            func=t,
            name=t.name,
            description=t.description,
        )
        for t in tools_instances
    ]

    llm_with_tools = llm.bind_tools(tools)

    # Build graph
    builder = StateGraph(MessagesState)
    # ... add nodes and edges ...
    graph = builder.compile()

    # Run
    result = graph.invoke({
        "messages": [HumanMessage(content="Test query")]
    })

    assert "messages" in result
    assert len(result["messages"]) > 0

def test_structured_output():
    """Test structured output validation."""
    output = AnalysisResult(
        summary="Test summary",
        key_points=["Point 1", "Point 2"],
        recommendations=["Action 1"],
        confidence_level=0.95
    )

    # Validate Pydantic model
    json_str = output.model_dump_json()
    assert "summary" in json_str
    assert "0.95" in json_str

    # Verify schema
    schema = output.model_json_schema()
    assert "properties" in schema
    assert "summary" in schema["properties"]
```

### Mock LLM for Testing
```python
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.callbacks.manager import CallbackManagerForLLMRun

class MockChatModel(BaseChatModel):
    """Mock LLM for testing."""

    _llm_type = "mock"

    def _generate(
        self,
        messages,
        stop=None,
        run_manager=None,
        **kwargs,
    ):
        """Generate mock response."""
        from langchain_core.outputs import ChatGeneration

        return ChatGeneration(
            message=AIMessage(content="Mock response")
        )

    @property
    def _llm_type(self) -> str:
        return "mock"

    def _call(self, prompt: str, **kwargs) -> str:
        return "Mock response"

# Usage
mock_llm = MockChatModel()
tool = AnalysisTool(mock_llm)
result = tool("test")
```

---

## Pattern 7: Logging Best Practices

### Comprehensive Logging Setup
```python
import logging
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class LoggingToolWrapper:
    """Wrap tools with comprehensive logging."""

    def __init__(self, tool_instance, tool_name: str):
        self.tool = tool_instance
        self.tool_name = tool_name
        self.logger = logging.getLogger(f"tool.{tool_name}")

    def __call__(self, *args, **kwargs) -> str:
        """Execute with logging."""
        start_time = datetime.now()

        self.logger.info(f"Tool invoked with args={args}, kwargs={kwargs}")

        try:
            result = self.tool(*args, **kwargs)

            elapsed = (datetime.now() - start_time).total_seconds()
            self.logger.info(
                f"Tool succeeded in {elapsed:.2f}s. "
                f"Result length: {len(result)} chars"
            )

            return result

        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            self.logger.error(
                f"Tool failed after {elapsed:.2f}s: {str(e)}",
                exc_info=True
            )
            raise

def log_graph_state(state: MessagesState) -> None:
    """Log agent state."""
    logger.info(f"Graph state: {len(state['messages'])} messages")

    for i, msg in enumerate(state["messages"][-3:]):  # Last 3
        msg_type = type(msg).__name__
        content_preview = msg.content[:100] if msg.content else "No content"
        logger.debug(f"  Message {i}: {msg_type} - {content_preview}")

def log_tool_calls(message) -> None:
    """Log tool calls from LLM message."""
    if hasattr(message, 'tool_calls') and message.tool_calls:
        for tc in message.tool_calls:
            logger.info(f"Tool call: {tc.get('name')} with args {tc.get('args')}")
```

---

## Pattern 8: Configuration Management

### Config Class
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class AgentConfig:
    """Configuration for agent."""

    # LLM settings
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: Optional[int] = 1000

    # Agent settings
    max_iterations: int = 25
    debug: bool = False

    # Tool settings
    tool_timeout: int = 30
    tool_retry_count: int = 3

    # Output settings
    return_structured_output: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "llm_model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "max_iterations": self.max_iterations,
            "debug": self.debug,
            "tool_timeout": self.tool_timeout,
            "tool_retry_count": self.tool_retry_count,
            "return_structured_output": self.return_structured_output,
        }

# Usage
config = AgentConfig(
    model="gpt-4o-mini",
    temperature=0.2,
    debug=True
)

llm = ChatOpenAI(
    model=config.model,
    temperature=config.temperature,
    max_tokens=config.max_tokens
)
```

---

## Quick Tips

### Don't Do This
```python
# BAD: Global LLM
LLM = ChatOpenAI()

def tool_func(query):
    return LLM.invoke(query)  # Hard to test, can't swap models
```

### Do This Instead
```python
# GOOD: Injected LLM
class MyTool:
    def __init__(self, llm):
        self.llm = llm

    def __call__(self, query):
        return self.llm.invoke(query)  # Easy to test, flexible

# Usage
llm = ChatOpenAI()
tool = MyTool(llm)
```

### State Management

```python
# DON'T: Manual message tracking
state = {
    "messages": [],
    "tool_results": []
}

# DO: Use MessagesState with automatic accumulation
from langgraph.graph import MessagesState

# MessagesState handles messages automatically
```

### Tool Binding

```python
# DON'T: Forget to bind tools
model = ChatOpenAI()
model.invoke(user_input)  # Model doesn't know about tools

# DO: Bind tools first
model = ChatOpenAI()
model_with_tools = model.bind_tools(tools)
model_with_tools.invoke(user_input)  # Model has tool awareness
```

