"""Request models for Proactive Information Flow architecture.

This module defines the API contract between the Big Data Layer and the
Alert Analyzer system. The Big Data Layer is responsible for:
1. Aggregating all required data from production systems
2. Determining the agent_type from alert content
3. Constructing an AnalysisRequest with all tool data

These models are the source of truth for the OpenAPI specification
shared with the Big Data Team.
"""

import logging
from typing import Dict, Literal

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


# Tool requirements per agent type
# This is the canonical definition of which tools each agent needs
INSIDER_TRADING_REQUIRED_TOOLS = frozenset([
    "alert_reader",
    "market_news",
    "market_data",
    "trader_profile",
    "trader_history",
])

WASH_TRADE_REQUIRED_TOOLS = frozenset([
    "alert_reader",
    "market_data",
    "trader_profile",
    "account_relationships",
    "related_accounts_history",
    "trade_timing",
    "counterparty_analysis",
])

# Valid formats per tool
TOOL_FORMAT_REQUIREMENTS: Dict[str, str] = {
    "alert_reader": "xml",
    "market_news": "txt",
    "market_data": "csv",
    "trader_profile": "csv",
    "trader_history": "csv",
    "account_relationships": "csv",
    "related_accounts_history": "csv",
    "trade_timing": "csv",
    "counterparty_analysis": "csv",
}


class ToolInput(BaseModel):
    """Input data for a single tool.

    This represents the data that the Big Data Layer provides for each tool.
    The format must match the tool's expected input format.

    Attributes:
        format: Data format (xml, csv, or txt)
        data: Raw data content as string

    Example:
        >>> tool_input = ToolInput(format="csv", data="id,name\\n1,John")
    """

    format: Literal["xml", "csv", "txt"] = Field(
        description="Format of the data content"
    )
    data: str = Field(
        min_length=1,
        description="Raw data content (XML string, CSV string, or plain text)"
    )

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "format": "csv",
                    "data": "trader_id,name,role,department,mnpi_access\nT123,John Doe,Analyst,Research,HIGH"
                },
                {
                    "format": "xml",
                    "data": "<ALERT><RULE_ID>SMARTS-IT-001</RULE_ID></ALERT>"
                },
                {
                    "format": "txt",
                    "data": "2024-01-15: Company X announces Q4 earnings beat"
                }
            ]
        }


class MissingToolDataError(Exception):
    """Raised when required tool data is not provided.

    Attributes:
        tool_name: Name of the missing tool
        agent_type: Agent type that requires this tool
    """

    def __init__(self, tool_name: str, agent_type: str) -> None:
        self.tool_name = tool_name
        self.agent_type = agent_type
        super().__init__(
            f"Missing required tool data: '{tool_name}' for agent_type '{agent_type}'"
        )


class InvalidToolFormatError(Exception):
    """Raised when tool data has an invalid format.

    Attributes:
        tool_name: Name of the tool with invalid format
        expected_format: Expected format
        received_format: Received format
    """

    def __init__(self, tool_name: str, expected_format: str, received_format: str) -> None:
        self.tool_name = tool_name
        self.expected_format = expected_format
        self.received_format = received_format
        super().__init__(
            f"Invalid format for tool '{tool_name}': expected '{expected_format}', "
            f"got '{received_format}'"
        )


class AnalysisRequest(BaseModel):
    """Request payload for alert analysis.

    This is the primary API contract between the Big Data Layer and the
    Alert Analyzer. The Big Data Layer must:
    1. Provide the full alert XML
    2. Determine and specify the agent_type
    3. Aggregate and provide all required tool data

    Attributes:
        alert_xml: Full XML content of the SMARTS alert
        agent_type: Type of analysis to perform (pre-determined by Big Data Layer)
        tool_data: Pre-aggregated data for each tool, keyed by tool name

    Raises:
        ValueError: If validation fails (missing tools, invalid formats)

    Example:
        >>> request = AnalysisRequest(
        ...     alert_xml="<ALERT>...</ALERT>",
        ...     agent_type="insider_trading",
        ...     tool_data={
        ...         "alert_reader": ToolInput(format="xml", data="<ALERT>...</ALERT>"),
        ...         "market_news": ToolInput(format="txt", data="2024-01-15: ..."),
        ...         "market_data": ToolInput(format="csv", data="timestamp,price..."),
        ...         "trader_profile": ToolInput(format="csv", data="trader_id,name..."),
        ...         "trader_history": ToolInput(format="csv", data="date,symbol..."),
        ...     }
        ... )
    """

    alert_xml: str = Field(
        min_length=1,
        description="Full XML content of the SMARTS alert"
    )

    agent_type: Literal["insider_trading", "wash_trade"] = Field(
        description="Type of analysis to perform (determined by Big Data Layer)"
    )

    tool_data: Dict[str, ToolInput] = Field(
        description="Pre-aggregated data for each tool, keyed by tool name"
    )

    @model_validator(mode="after")
    def validate_required_tools(self) -> "AnalysisRequest":
        """Validate that all required tools for the agent_type are provided.

        Raises:
            ValueError: If required tools are missing or have invalid formats
        """
        # Determine required tools based on agent_type
        if self.agent_type == "insider_trading":
            required_tools = INSIDER_TRADING_REQUIRED_TOOLS
        elif self.agent_type == "wash_trade":
            required_tools = WASH_TRADE_REQUIRED_TOOLS
        else:
            # This shouldn't happen due to Literal type, but defensive
            raise ValueError(f"Unknown agent_type: {self.agent_type}")

        # Check for missing tools
        provided_tools = set(self.tool_data.keys())
        missing_tools = required_tools - provided_tools

        if missing_tools:
            missing_list = ", ".join(sorted(missing_tools))
            raise ValueError(
                f"Missing required tool data for agent_type '{self.agent_type}': "
                f"{missing_list}"
            )

        # Validate formats for each tool
        for tool_name, tool_input in self.tool_data.items():
            expected_format = TOOL_FORMAT_REQUIREMENTS.get(tool_name)
            if expected_format and tool_input.format != expected_format:
                raise ValueError(
                    f"Invalid format for tool '{tool_name}': "
                    f"expected '{expected_format}', got '{tool_input.format}'"
                )

        logger.debug(
            f"Validated AnalysisRequest: agent_type={self.agent_type}, "
            f"tools={list(self.tool_data.keys())}"
        )

        return self

    def get_tool_data(self, tool_name: str) -> ToolInput:
        """Get tool data by name, raising if not found.

        Args:
            tool_name: Name of the tool

        Returns:
            ToolInput for the specified tool

        Raises:
            MissingToolDataError: If tool data not found
        """
        tool_input = self.tool_data.get(tool_name)
        if tool_input is None:
            raise MissingToolDataError(tool_name, self.agent_type)
        return tool_input

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "examples": [
                {
                    "alert_xml": "<ALERT><RULE_ID>SMARTS-IT-001</RULE_ID>...</ALERT>",
                    "agent_type": "insider_trading",
                    "tool_data": {
                        "alert_reader": {
                            "format": "xml",
                            "data": "<ALERT><RULE_ID>SMARTS-IT-001</RULE_ID>...</ALERT>"
                        },
                        "market_news": {
                            "format": "txt",
                            "data": "2024-01-15: Company X announces Q4 earnings beat"
                        },
                        "market_data": {
                            "format": "csv",
                            "data": "timestamp,symbol,price,volume\n2024-01-15,AAPL,185.50,1000000"
                        },
                        "trader_profile": {
                            "format": "csv",
                            "data": "trader_id,name,role,department,mnpi_access\nT123,John,Analyst,Research,HIGH"
                        },
                        "trader_history": {
                            "format": "csv",
                            "data": "date,symbol,action,quantity,price\n2024-01-10,AAPL,BUY,100,180.00"
                        }
                    }
                }
            ]
        }


class AnalysisError(BaseModel):
    """Error response from analysis API.

    Attributes:
        error: Error code
        tool: Tool name (for tool-specific errors)
        expected: Expected value (for format errors)
        received: Received value (for format errors)
        message: Human-readable error message
        details: Additional error details
    """

    error: Literal[
        "MISSING_TOOL_DATA",
        "INVALID_FORMAT",
        "UNKNOWN_AGENT_TYPE",
        "ANALYSIS_FAILED",
        "VALIDATION_ERROR"
    ] = Field(description="Error code")

    tool: str | None = Field(
        default=None,
        description="Tool name (for tool-specific errors)"
    )

    expected: str | None = Field(
        default=None,
        description="Expected value (for format errors)"
    )

    received: str | None = Field(
        default=None,
        description="Received value (for format errors)"
    )

    message: str = Field(
        description="Human-readable error message"
    )

    details: str | None = Field(
        default=None,
        description="Additional error details"
    )

    @classmethod
    def from_missing_tool(cls, tool_name: str, agent_type: str) -> "AnalysisError":
        """Create error for missing tool data.

        Args:
            tool_name: Name of the missing tool
            agent_type: Agent type that requires this tool

        Returns:
            AnalysisError instance
        """
        return cls(
            error="MISSING_TOOL_DATA",
            tool=tool_name,
            message=f"Required tool data not provided: {tool_name}",
            details=f"agent_type '{agent_type}' requires tool '{tool_name}'"
        )

    @classmethod
    def from_invalid_format(
        cls,
        tool_name: str,
        expected: str,
        received: str
    ) -> "AnalysisError":
        """Create error for invalid tool format.

        Args:
            tool_name: Name of the tool with invalid format
            expected: Expected format
            received: Received format

        Returns:
            AnalysisError instance
        """
        return cls(
            error="INVALID_FORMAT",
            tool=tool_name,
            expected=expected,
            received=received,
            message=f"Invalid format for tool '{tool_name}'"
        )

    @classmethod
    def from_exception(cls, exception: Exception) -> "AnalysisError":
        """Create error from exception.

        Args:
            exception: The exception that occurred

        Returns:
            AnalysisError instance
        """
        return cls(
            error="ANALYSIS_FAILED",
            message=str(exception),
            details=type(exception).__name__
        )
