# LangGraph Reference Implementation: Complete Agent with 6 Tools

This document provides a complete, production-ready reference implementation matching your exact requirements.

## Project Structure

```
project/
├── src/
│   ├── config.py              # Configuration management
│   ├── tools/                 # Tool implementations
│   │   ├── __init__.py
│   │   ├── base.py           # Base tool class
│   │   ├── comparison.py      # Tool 1
│   │   ├── analysis.py        # Tool 2
│   │   ├── research.py        # Tool 3
│   │   ├── extraction.py      # Tool 4
│   │   ├── recommendation.py  # Tool 5
│   │   └── sentiment.py       # Tool 6
│   ├── agent.py              # Main agent
│   ├── schemas.py            # Pydantic models
│   └── logging_utils.py      # Logging setup
├── tests/
│   ├── test_tools.py
│   ├── test_agent.py
│   └── test_integration.py
├── requirements.txt
└── main.py
```

## File 1: requirements.txt

```
langgraph==0.2.18
langchain-openai==0.2.0
langchain-core==0.3.0
pydantic==2.9.0
python-dotenv==1.0.0
tenacity==9.0.0
pytest==7.4.0
pytest-asyncio==0.23.0
```

## File 2: src/config.py

```python
"""Configuration management for the agent."""

from dataclasses import dataclass, field
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class LLMConfig:
    """LLM configuration."""
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    max_tokens: Optional[int] = 2000
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    api_version: Optional[str] = None
    azure_endpoint: Optional[str] = None

    def is_azure(self) -> bool:
        """Check if using Azure OpenAI."""
        return bool(self.azure_endpoint)

@dataclass
class AgentConfig:
    """Agent configuration."""
    max_iterations: int = 25
    debug: bool = True
    return_structured_output: bool = True

@dataclass
class ToolConfig:
    """Tool configuration."""
    timeout: int = 30
    retry_count: int = 3
    max_input_length: int = 5000

@dataclass
class AppConfig:
    """Complete application configuration."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    tool: ToolConfig = field(default_factory=ToolConfig)

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment."""
        return cls(
            llm=LLMConfig(
                model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_version=os.getenv("OPENAI_API_VERSION"),
            ),
            agent=AgentConfig(
                max_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", "25")),
                debug=os.getenv("DEBUG", "False").lower() == "true",
            ),
        )

# Global config
config = AppConfig.from_env()
```

## File 3: src/logging_utils.py

```python
"""Logging utilities."""

import logging
import logging.config
import json
from datetime import datetime
from typing import Any

# Configure structured logging
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": "agent.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
        },
    },
    "loggers": {
        "": {  # Root logger
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": True,
        },
        "urllib3": {  # Suppress verbose libs
            "level": "WARNING",
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)

def log_dict(logger: logging.Logger, level: int, data: dict, prefix: str = "") -> None:
    """Log dictionary with pretty formatting."""
    try:
        json_str = json.dumps(data, indent=2, default=str)
        for line in json_str.split("\n"):
            logger.log(level, f"{prefix}{line}")
    except Exception as e:
        logger.error(f"Failed to log dict: {e}")

def log_timing(logger: logging.Logger, operation: str, elapsed_seconds: float) -> None:
    """Log operation timing."""
    logger.info(f"[TIMING] {operation} completed in {elapsed_seconds:.2f}s")

def log_tool_invocation(logger: logging.Logger, tool_name: str, input_data: str) -> None:
    """Log tool invocation."""
    input_preview = input_data[:100] if len(input_data) > 100 else input_data
    logger.info(f"[TOOL] {tool_name} called with: {input_preview}...")

def log_tool_result(logger: logging.Logger, tool_name: str, result_length: int) -> None:
    """Log tool result."""
    logger.info(f"[TOOL] {tool_name} returned {result_length} chars")
```

## File 4: src/schemas.py

```python
"""Pydantic schemas for structured output."""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class InsightPoint(BaseModel):
    """Single insight point."""
    title: str = Field(description="Short title of the insight")
    description: str = Field(description="Detailed description")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence level")

class AgentOutput(BaseModel):
    """Final structured output from agent."""

    summary: str = Field(
        description="Executive summary of the analysis",
        min_length=10,
        max_length=500
    )

    insights: List[InsightPoint] = Field(
        description="Key insights discovered",
        min_items=1,
        max_items=10
    )

    recommendations: List[str] = Field(
        description="Recommended actions",
        min_items=1,
        max_items=5
    )

    risks: Optional[List[str]] = Field(
        default=None,
        description="Identified risks or concerns"
    )

    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata about the analysis"
    )

    confidence_level: float = Field(
        ge=0.0,
        le=1.0,
        default=0.85,
        description="Overall confidence in the analysis"
    )

    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this analysis was generated"
    )

    def to_json(self) -> str:
        """Convert to JSON string."""
        return self.model_dump_json(indent=2, by_alias=True)

class ToolResult(BaseModel):
    """Result from a tool."""
    tool_name: str
    success: bool
    result: str
    error: Optional[str] = None
```

## File 5: src/tools/base.py

```python
"""Base tool class."""

from abc import ABC, abstractmethod
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class BaseTool(ABC):
    """Base class for all tools."""

    def __init__(self, llm, name: str, description: str):
        """Initialize tool.

        Args:
            llm: LangChain LLM instance
            name: Tool name
            description: Tool description
        """
        self.llm = llm
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"tool.{name}")
        self.call_count = 0
        self.total_processing_time = 0.0

    @abstractmethod
    def _execute(self, query: str) -> str:
        """Execute the tool logic.

        Args:
            query: Input query

        Returns:
            Result as string
        """
        pass

    def _validate_input(self, query: str) -> Optional[str]:
        """Validate input.

        Returns:
            Error message if invalid, None if valid
        """
        if not query or not isinstance(query, str):
            return "Input must be a non-empty string"

        if len(query) > 5000:
            return f"Input too long ({len(query)} > 5000 chars)"

        return None

    def __call__(self, query: str) -> str:
        """Call the tool.

        Args:
            query: Input query

        Returns:
            Result as string
        """
        self.call_count += 1
        start_time = datetime.utcnow()

        try:
            # Validate input
            error = self._validate_input(query)
            if error:
                self.logger.warning(f"Input validation failed: {error}")
                return f"Error: {error}"

            # Log invocation
            query_preview = query[:100] if len(query) > 100 else query
            self.logger.info(f"Invocation #{self.call_count}: {query_preview}...")

            # Execute
            result = self._execute(query)

            # Log result
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            self.total_processing_time += elapsed
            self.logger.info(
                f"Success in {elapsed:.2f}s. Result: {len(result)} chars"
            )

            return result

        except Exception as e:
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            self.logger.error(f"Execution failed after {elapsed:.2f}s: {e}", exc_info=True)
            return f"Error: {str(e)}"

    def get_stats(self) -> dict:
        """Get tool statistics."""
        return {
            "name": self.name,
            "call_count": self.call_count,
            "total_time_seconds": self.total_processing_time,
            "avg_time_per_call": (
                self.total_processing_time / self.call_count
                if self.call_count > 0
                else 0
            ),
        }
```

## File 6: src/tools/comparison.py

```python
"""Comparison tool implementation."""

from .base import BaseTool
import logging

logger = logging.getLogger(__name__)

class ComparisonTool(BaseTool):
    """Compare two or more items using LLM."""

    def __init__(self, llm):
        super().__init__(
            llm,
            name="compare",
            description="Compare items and highlight differences and similarities"
        )

    def _execute(self, query: str) -> str:
        """Execute comparison."""
        prompt = f"""Compare the following items in detail:

{query}

Provide:
1. Similarities
2. Key differences
3. Pros/cons of each
4. Use case recommendations"""

        response = self.llm.invoke(prompt)
        return response.content
```

## File 7: src/tools/analysis.py

```python
"""Analysis tool implementation."""

from .base import BaseTool

class AnalysisTool(BaseTool):
    """Deep analysis using LLM."""

    def __init__(self, llm):
        super().__init__(
            llm,
            name="analyze",
            description="Perform deep analysis on content"
        )

    def _execute(self, query: str) -> str:
        """Execute analysis."""
        prompt = f"""Provide detailed analysis of:

{query}

Include:
1. Current state assessment
2. Main drivers and causes
3. Potential impacts
4. Future trends
5. Critical factors"""

        response = self.llm.invoke(prompt)
        return response.content
```

## File 8: src/tools/research.py

```python
"""Research tool implementation."""

from .base import BaseTool

class ResearchTool(BaseTool):
    """Research topics using LLM."""

    def __init__(self, llm):
        super().__init__(
            llm,
            name="research",
            description="Research a topic comprehensively"
        )

    def _execute(self, query: str) -> str:
        """Execute research."""
        prompt = f"""Research the following topic thoroughly:

{query}

Provide:
1. Definition and background
2. Current state and developments
3. Key players and stakeholders
4. Challenges and opportunities
5. Future outlook
6. Recommended resources"""

        response = self.llm.invoke(prompt)
        return response.content
```

## File 9: src/tools/extraction.py

```python
"""Extraction tool implementation."""

from .base import BaseTool

class ExtractionTool(BaseTool):
    """Extract key information using LLM."""

    def __init__(self, llm):
        super().__init__(
            llm,
            name="extract",
            description="Extract key information and entities"
        )

    def _execute(self, query: str) -> str:
        """Execute extraction."""
        prompt = f"""Extract key information from the following:

{query}

Identify and extract:
1. Main entities (people, organizations, places)
2. Key facts and data points
3. Important dates and timelines
4. Relationships between entities
5. Critical insights
6. Action items"""

        response = self.llm.invoke(prompt)
        return response.content
```

## File 10: src/tools/recommendation.py

```python
"""Recommendation tool implementation."""

from .base import BaseTool

class RecommendationTool(BaseTool):
    """Generate recommendations using LLM."""

    def __init__(self, llm):
        super().__init__(
            llm,
            name="recommend",
            description="Generate actionable recommendations"
        )

    def _execute(self, query: str) -> str:
        """Execute recommendation generation."""
        prompt = f"""Based on the following context:

{query}

Provide:
1. Immediate actions (next 30 days)
2. Short-term strategies (1-3 months)
3. Long-term initiatives (6-12 months)
4. Resource requirements
5. Success metrics
6. Risk mitigation strategies"""

        response = self.llm.invoke(prompt)
        return response.content
```

## File 11: src/tools/sentiment.py

```python
"""Sentiment analysis tool implementation."""

from .base import BaseTool

class SentimentTool(BaseTool):
    """Analyze sentiment using LLM."""

    def __init__(self, llm):
        super().__init__(
            llm,
            name="sentiment",
            description="Analyze sentiment and emotional tone"
        )

    def _execute(self, query: str) -> str:
        """Execute sentiment analysis."""
        prompt = f"""Analyze the sentiment and emotional tone of:

{query}

Provide:
1. Overall sentiment (positive/negative/neutral/mixed)
2. Emotional indicators and keywords
3. Intensity level (1-10)
4. Subjectivity assessment
5. Context and nuances
6. Implications and significance"""

        response = self.llm.invoke(prompt)
        return response.content
```

## File 12: src/tools/__init__.py

```python
"""Tools package."""

from .comparison import ComparisonTool
from .analysis import AnalysisTool
from .research import ResearchTool
from .extraction import ExtractionTool
from .recommendation import RecommendationTool
from .sentiment import SentimentTool

__all__ = [
    "ComparisonTool",
    "AnalysisTool",
    "ResearchTool",
    "ExtractionTool",
    "RecommendationTool",
    "SentimentTool",
]
```

## File 13: src/agent.py

```python
"""Main agent implementation."""

import logging
from typing import Literal
from datetime import datetime

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import tool as create_tool

from .config import config
from .schemas import AgentOutput, InsightPoint
from .tools import (
    ComparisonTool,
    AnalysisTool,
    ResearchTool,
    ExtractionTool,
    RecommendationTool,
    SentimentTool,
)

logger = logging.getLogger(__name__)

class Agent:
    """Main LangGraph agent."""

    def __init__(self, llm):
        """Initialize agent.

        Args:
            llm: LangChain LLM instance
        """
        self.llm = llm
        self.logger = logger

        # Create tool instances
        self.tool_instances = [
            ComparisonTool(llm),
            AnalysisTool(llm),
            ResearchTool(llm),
            ExtractionTool(llm),
            RecommendationTool(llm),
            SentimentTool(llm),
        ]

        # Convert to LangChain tools
        self.tools = [
            create_tool(
                func=t,
                name=t.name,
                description=t.description,
            )
            for t in self.tool_instances
        ]

        # Bind tools to LLM
        self.llm_with_tools = llm.bind_tools(self.tools)

        # Build graph
        self.graph = self._build_graph()

    def _build_graph(self):
        """Build the LangGraph."""
        builder = StateGraph(MessagesState)

        # Add nodes
        builder.add_node("agent", self._agent_node)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_node("respond", self._respond_node)

        # Add edges
        builder.add_edge(START, "agent")
        builder.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "tools": "tools",
                "respond": "respond",
            }
        )
        builder.add_edge("tools", "agent")
        builder.add_edge("respond", END)

        return builder.compile()

    def _agent_node(self, state: MessagesState) -> dict:
        """Main agent node."""
        self.logger.info(f"Agent node: processing {len(state['messages'])} messages")

        system_prompt = SystemMessage(
            content="""You are an expert analyst with access to 6 specialized tools:
1. compare - Compare items and highlight differences/similarities
2. analyze - Perform deep analysis
3. research - Research topics comprehensively
4. extract - Extract key information and entities
5. recommend - Generate actionable recommendations
6. sentiment - Analyze sentiment and emotional tone

Use these tools strategically to provide comprehensive insights. Call tools when needed to gather information, then synthesize findings into clear, actionable insights."""
        )

        messages = [system_prompt] + state["messages"]
        response = self.llm_with_tools.invoke(messages)

        if hasattr(response, 'tool_calls') and response.tool_calls:
            self.logger.info(
                f"LLM called {len(response.tool_calls)} tools: "
                f"{[tc.get('name') for tc in response.tool_calls]}"
            )

        return {"messages": [response]}

    def _should_continue(self, state: MessagesState) -> Literal["tools", "respond"]:
        """Decide whether to continue with tools or respond."""
        last_message = state["messages"][-1]

        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"

        return "respond"

    def _respond_node(self, state: MessagesState) -> dict:
        """Generate structured final response."""
        self.logger.info("Response node: generating structured output")

        try:
            # Use LLM with structured output
            llm_structured = self.llm.with_structured_output(AgentOutput)

            # Build focused prompt from conversation
            messages = [
                SystemMessage(
                    content="You are an expert analyst. Generate structured insights based on the conversation."
                )
            ] + state["messages"]

            # Get structured response
            result = llm_structured.invoke(messages)

            self.logger.info(
                f"Structured response: {len(result.insights)} insights, "
                f"confidence {result.confidence_level}"
            )

            # Return as JSON in message
            json_output = result.model_dump_json(indent=2)
            return {"messages": [AIMessage(content=json_output)]}

        except Exception as e:
            self.logger.error(f"Failed to generate structured output: {e}")

            # Fallback response
            fallback = AgentOutput(
                summary="Analysis encountered an error",
                insights=[
                    InsightPoint(
                        title="Error Occurred",
                        description=str(e),
                        confidence=0.0
                    )
                ],
                recommendations=["Retry the analysis"],
                confidence_level=0.0,
                metadata={"error": str(e)}
            )

            return {
                "messages": [AIMessage(content=fallback.model_dump_json(indent=2))]
            }

    def invoke(self, user_input: str, config=None) -> AgentOutput:
        """Run the agent.

        Args:
            user_input: User query
            config: Optional graph configuration

        Returns:
            Structured output from agent
        """
        if config is None:
            config = {"recursion_limit": config.agent.max_iterations}

        self.logger.info(f"Agent invocation: {user_input[:100]}...")

        try:
            result = self.graph.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                config=config
            )

            # Extract and parse final response
            last_message = result["messages"][-1]

            if isinstance(last_message.content, str) and last_message.content.startswith('{'):
                try:
                    import json
                    data = json.loads(last_message.content)
                    output = AgentOutput(**data)
                    self.logger.info("Successfully parsed structured output")
                    return output
                except Exception as parse_error:
                    self.logger.warning(f"Failed to parse JSON: {parse_error}")

            # Fallback
            return AgentOutput(
                summary=last_message.content,
                insights=[
                    InsightPoint(
                        title="Analysis Complete",
                        description=last_message.content,
                        confidence=0.7
                    )
                ],
                recommendations=["Review the analysis above"],
            )

        except Exception as e:
            self.logger.error(f"Agent invocation failed: {e}", exc_info=True)
            raise

    def get_tool_stats(self) -> dict:
        """Get statistics about tool usage."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "tools": [t.get_stats() for t in self.tool_instances]
        }
```

## File 14: main.py

```python
"""Main entry point."""

import logging
from langchain_openai import ChatOpenAI
from src.config import config
from src.agent import Agent
from src.logging_utils import get_logger, log_dict

logger = get_logger(__name__)

def main():
    """Main function."""
    logger.info("=" * 60)
    logger.info("LangGraph Agent Starting")
    logger.info("=" * 60)

    try:
        # Initialize LLM
        logger.info(f"Initializing LLM: {config.llm.model}")
        llm = ChatOpenAI(
            model=config.llm.model,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )

        # Create agent
        logger.info("Creating agent with 6 tools")
        agent = Agent(llm)

        # Example query
        user_query = """Compare Python and JavaScript for building web APIs.
        What are the trade-offs?"""

        logger.info(f"Processing query: {user_query[:100]}...")

        # Run agent
        output = agent.invoke(user_query)

        # Display output
        logger.info("\n" + "=" * 60)
        logger.info("AGENT OUTPUT")
        logger.info("=" * 60)
        print(output.to_json())

        # Display stats
        stats = agent.get_tool_stats()
        logger.info("\n" + "=" * 60)
        logger.info("TOOL STATISTICS")
        logger.info("=" * 60)
        log_dict(logger, logging.INFO, stats)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
```

## File 15: tests/test_tools.py

```python
"""Test tool implementations."""

import pytest
from unittest.mock import MagicMock

from src.tools import ComparisonTool, AnalysisTool

def test_tool_input_validation():
    """Test tool validates input."""
    mock_llm = MagicMock()
    tool = ComparisonTool(mock_llm)

    # Empty input
    result = tool("")
    assert "Error" in result

    # Long input
    result = tool("x" * 10000)
    assert "Error" in result or "truncated" in result.lower()

def test_tool_executes_successfully():
    """Test tool executes successfully."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "Comparison result"

    tool = ComparisonTool(mock_llm)
    result = tool("Compare A and B")

    assert result == "Comparison result"
    assert mock_llm.invoke.called

def test_tool_error_handling():
    """Test tool handles errors."""
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = Exception("LLM error")

    tool = AnalysisTool(mock_llm)
    result = tool("test")

    assert "Error" in result
    assert "LLM error" in result

def test_tool_statistics():
    """Test tool statistics tracking."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "Result"

    tool = ComparisonTool(mock_llm)
    tool("Query 1")
    tool("Query 2")

    stats = tool.get_stats()
    assert stats["call_count"] == 2
    assert stats["name"] == "compare"
```

## File 16: tests/test_agent.py

```python
"""Test agent."""

from langchain_openai import ChatOpenAI
from src.agent import Agent
from src.schemas import AgentOutput

def test_agent_initialization():
    """Test agent initializes correctly."""
    llm = ChatOpenAI(model="gpt-4o-mini")
    agent = Agent(llm)

    assert len(agent.tools) == 6
    assert agent.graph is not None

def test_agent_runs():
    """Test agent can run."""
    llm = ChatOpenAI(model="gpt-4o-mini")
    agent = Agent(llm)

    result = agent.invoke("What is machine learning?")

    assert isinstance(result, AgentOutput)
    assert result.summary
    assert len(result.insights) > 0
```

## Usage

### Installation

```bash
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

### Testing

```bash
pytest tests/
```

## Key Features

1. **6 Specialized Tools**: Each with its own LLM access for focused analysis
2. **Dependency Injection**: Tools receive LLM via constructor
3. **Structured Output**: Pydantic models ensure valid output
4. **Comprehensive Logging**: Track agent execution at each step
5. **Error Handling**: Graceful fallbacks for all failure modes
6. **Statistics**: Track tool usage and performance
7. **Testing**: Unit and integration test patterns included
8. **Configuration**: Environment-based configuration

