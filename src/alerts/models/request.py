"""Request models for proactive information flow.

This module defines the API contract for the Big Data Layer to send
aggregated data to the Alert Analyzer. It implements the proactive
information flow pattern where all tool data is pre-aggregated and
injected into the analysis request.

Key Models:
    - ToolInput: Container for tool-specific data with format validation
    - AnalysisRequest: Main request model with all required tool data
    - ErrorResponse: Standardized error response schema

Usage:
    from alerts.models.request import AnalysisRequest, ToolInput

    request = AnalysisRequest(
        alert_xml="<ALERT>...</ALERT>",
        agent_type="insider_trading",
        tool_data={
            "alert_reader": ToolInput(format="xml", data="<ALERT>..."),
            "market_news": ToolInput(format="txt", data="2024-01-15: ..."),
            ...
        }
    )
"""

import logging
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


# Required tools for each agent type
# These define the contract with the Big Data Layer
REQUIRED_TOOLS_BY_AGENT: Dict[str, List[str]] = {
    "insider_trading": [
        "alert_reader",    # xml - parsed alert content
        "market_news",     # txt - news timeline
        "market_data",     # csv - market conditions
        "trader_profile",  # csv - trader MNPI access
        "trader_history",  # csv - baseline behavior
    ],
    "wash_trade": [
        "alert_reader",              # xml - parsed alert content
        "market_data",               # csv - market conditions
        "account_relationships",     # csv - ownership network
        "related_accounts_history",  # csv - coordinated activity
        "trade_timing",              # csv - sub-second patterns
        "counterparty_analysis",     # csv - beneficial ownership overlap
    ],
}

# Expected formats for each tool
TOOL_FORMATS: Dict[str, str] = {
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
    """Container for tool-specific data.

    Each tool receives its data through this model, which includes
    both the raw data content and its format specification.

    Attributes:
        format: Data format identifier (xml, csv, or txt)
        data: Raw data content as a string

    Example:
        >>> tool_input = ToolInput(format="csv", data="col1,col2\\n1,2")
    """

    format: Literal["xml", "csv", "txt"] = Field(
        ...,
        description="Format of the data content (xml, csv, or txt)"
    )
    data: str = Field(
        ...,
        description="Raw data content as string",
        min_length=1
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "format": "csv",
                    "data": "trader_id,name,role\nT123,John Doe,Analyst"
                },
                {
                    "format": "xml",
                    "data": "<ALERT><RULE_ID>SMARTS-IT-001</RULE_ID></ALERT>"
                },
                {
                    "format": "txt",
                    "data": "2024-01-15: Company announces Q4 earnings"
                }
            ]
        }
    }


class AnalysisRequest(BaseModel):
    """Main request model for alert analysis.

    This model represents the contract between the Big Data Layer and
    the Alert Analyzer. The Big Data Layer is responsible for:
    1. Determining the agent_type from alert content
    2. Aggregating all required data for each tool
    3. Providing data in the correct format

    The analyzer will fail-fast if any required tool data is missing
    or in the wrong format.

    Attributes:
        alert_xml: Full XML content of the SMARTS alert
        agent_type: Type of analysis to perform (determined by Big Data Layer)
        tool_data: Pre-aggregated data for each tool, keyed by tool name

    Example:
        >>> request = AnalysisRequest(
        ...     alert_xml="<ALERT>...</ALERT>",
        ...     agent_type="insider_trading",
        ...     tool_data={
        ...         "alert_reader": ToolInput(format="xml", data="..."),
        ...         "market_news": ToolInput(format="txt", data="..."),
        ...         "market_data": ToolInput(format="csv", data="..."),
        ...         "trader_profile": ToolInput(format="csv", data="..."),
        ...         "trader_history": ToolInput(format="csv", data="..."),
        ...     }
        ... )
    """

    alert_xml: str = Field(
        ...,
        description="Full XML content of the SMARTS alert",
        min_length=1
    )
    agent_type: Literal["insider_trading", "wash_trade"] = Field(
        ...,
        description="Type of analysis to perform (determined by Big Data Layer)"
    )
    tool_data: Dict[str, ToolInput] = Field(
        ...,
        description="Pre-aggregated data for each tool, keyed by tool name"
    )

    @model_validator(mode="after")
    def validate_required_tools(self) -> "AnalysisRequest":
        """Validate that all required tools for the agent type are provided.

        Raises:
            ValueError: If any required tool data is missing
            ValueError: If any tool data has an incorrect format
        """
        required_tools = REQUIRED_TOOLS_BY_AGENT.get(self.agent_type, [])
        provided_tools = set(self.tool_data.keys())

        # Check for missing tools
        missing_tools = [t for t in required_tools if t not in provided_tools]
        if missing_tools:
            logger.error(
                f"Missing required tool data for {self.agent_type}: {missing_tools}"
            )
            raise ValueError(
                f"Missing required tool data for {self.agent_type}: {missing_tools}"
            )

        # Check for incorrect formats
        for tool_name in required_tools:
            tool_input = self.tool_data[tool_name]
            expected_format = TOOL_FORMATS.get(tool_name)
            if expected_format and tool_input.format != expected_format:
                logger.error(
                    f"Tool '{tool_name}' has incorrect format: "
                    f"expected '{expected_format}', got '{tool_input.format}'"
                )
                raise ValueError(
                    f"Tool '{tool_name}' has incorrect format: "
                    f"expected '{expected_format}', got '{tool_input.format}'"
                )

        logger.debug(
            f"Validated AnalysisRequest for {self.agent_type} "
            f"with {len(self.tool_data)} tools"
        )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "alert_xml": "<ALERT><RULE_ID>SMARTS-IT-001</RULE_ID></ALERT>",
                    "agent_type": "insider_trading",
                    "tool_data": {
                        "alert_reader": {
                            "format": "xml",
                            "data": "<ALERT>...</ALERT>"
                        },
                        "market_news": {
                            "format": "txt",
                            "data": "2024-01-15: Company announces Q4 earnings"
                        },
                        "market_data": {
                            "format": "csv",
                            "data": "timestamp,symbol,price,volume\n..."
                        },
                        "trader_profile": {
                            "format": "csv",
                            "data": "trader_id,name,role,mnpi_access\n..."
                        },
                        "trader_history": {
                            "format": "csv",
                            "data": "date,symbol,action,quantity\n..."
                        }
                    }
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """Standardized error response schema.

    This model defines the error response format for the API,
    enabling consistent error handling across clients.

    Attributes:
        error: Error code identifier
        tool: Tool name (for tool-specific errors)
        expected: Expected value (for format errors)
        received: Received value (for format errors)
        message: Human-readable error message
        details: Additional error details

    Example:
        >>> error = ErrorResponse(
        ...     error="MISSING_TOOL_DATA",
        ...     tool="trader_profile",
        ...     message="Required tool data not provided"
        ... )
    """

    error: Literal[
        "MISSING_TOOL_DATA",
        "INVALID_FORMAT",
        "UNKNOWN_AGENT_TYPE",
        "ANALYSIS_FAILED"
    ] = Field(
        ...,
        description="Error code identifier"
    )
    tool: Optional[str] = Field(
        None,
        description="Tool name (for tool-specific errors)"
    )
    expected: Optional[str] = Field(
        None,
        description="Expected value (for format errors)"
    )
    received: Optional[str] = Field(
        None,
        description="Received value (for format errors)"
    )
    message: str = Field(
        ...,
        description="Human-readable error message"
    )
    details: Optional[str] = Field(
        None,
        description="Additional error details"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": "MISSING_TOOL_DATA",
                    "tool": "trader_profile",
                    "message": "Required tool data not provided"
                },
                {
                    "error": "INVALID_FORMAT",
                    "tool": "market_data",
                    "expected": "csv",
                    "received": "json",
                    "message": "Tool market_data: expected csv, got json"
                },
                {
                    "error": "UNKNOWN_AGENT_TYPE",
                    "message": "Unknown agent type: unknown_type"
                }
            ]
        }
    }


# Type alias for convenience
AgentType = Literal["insider_trading", "wash_trade"]
DataFormat = Literal["xml", "csv", "txt"]
