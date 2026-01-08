"""Custom exceptions for proactive information flow.

This module defines custom exceptions used throughout the Alert Analyzer
to implement fail-fast error handling. These exceptions provide clear,
structured error information that can be easily converted to API error
responses.

Key Exceptions:
    - MissingToolDataError: Raised when required tool data is not provided
    - InvalidFormatError: Raised when tool data format is incorrect
    - AnalysisError: Raised when analysis fails during execution

Usage:
    from alerts.exceptions import MissingToolDataError, InvalidFormatError

    if data is None:
        raise MissingToolDataError("trader_profile")

    if format != "csv":
        raise InvalidFormatError("market_data", expected="csv", received=format)
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AlertAnalyzerError(Exception):
    """Base exception for all Alert Analyzer errors.

    All custom exceptions in this module inherit from this base class,
    allowing for easy catching of any analyzer-specific error.

    Attributes:
        message: Human-readable error message
    """

    def __init__(self, message: str):
        """Initialize the base exception.

        Args:
            message: Human-readable error message
        """
        self.message = message
        super().__init__(message)
        logger.error(f"{self.__class__.__name__}: {message}")


class MissingToolDataError(AlertAnalyzerError):
    """Raised when required tool data is not provided.

    This exception is raised during analysis when a tool expects
    data to be injected but the data is None or missing from
    the request's tool_data dictionary.

    Attributes:
        tool_name: Name of the tool that is missing data
        message: Human-readable error message

    Example:
        >>> raise MissingToolDataError("trader_profile")
        MissingToolDataError: Required tool data not provided: trader_profile
    """

    def __init__(self, tool_name: str):
        """Initialize MissingToolDataError.

        Args:
            tool_name: Name of the tool that is missing data
        """
        self.tool_name = tool_name
        message = f"Required tool data not provided: {tool_name}"
        super().__init__(message)

    def to_error_response_dict(self) -> dict:
        """Convert to ErrorResponse-compatible dictionary.

        Returns:
            Dictionary suitable for ErrorResponse model construction
        """
        return {
            "error": "MISSING_TOOL_DATA",
            "tool": self.tool_name,
            "message": self.message,
        }


class InvalidFormatError(AlertAnalyzerError):
    """Raised when tool data format is incorrect.

    This exception is raised when a tool receives data in a format
    that doesn't match its expected format (e.g., receiving JSON
    when CSV was expected).

    Attributes:
        tool_name: Name of the tool with incorrect format
        expected: Expected data format (csv, xml, txt)
        received: Received data format
        message: Human-readable error message

    Example:
        >>> raise InvalidFormatError("market_data", expected="csv", received="json")
        InvalidFormatError: Tool market_data: expected csv, got json
    """

    def __init__(self, tool_name: str, expected: str, received: str):
        """Initialize InvalidFormatError.

        Args:
            tool_name: Name of the tool with incorrect format
            expected: Expected data format
            received: Received data format
        """
        self.tool_name = tool_name
        self.expected = expected
        self.received = received
        message = f"Tool {tool_name}: expected {expected}, got {received}"
        super().__init__(message)

    def to_error_response_dict(self) -> dict:
        """Convert to ErrorResponse-compatible dictionary.

        Returns:
            Dictionary suitable for ErrorResponse model construction
        """
        return {
            "error": "INVALID_FORMAT",
            "tool": self.tool_name,
            "expected": self.expected,
            "received": self.received,
            "message": self.message,
        }


class AnalysisError(AlertAnalyzerError):
    """Raised when analysis fails during execution.

    This exception is raised when an error occurs during the analysis
    process that prevents successful completion. This is a general
    error for failures that don't fit the more specific error types.

    Attributes:
        stage: Stage of analysis where the error occurred
        details: Additional error details
        message: Human-readable error message

    Example:
        >>> raise AnalysisError("LLM synthesis failed", stage="final_synthesis")
        AnalysisError: Analysis failed: LLM synthesis failed (stage: final_synthesis)
    """

    def __init__(self, message: str, stage: Optional[str] = None, details: Optional[str] = None):
        """Initialize AnalysisError.

        Args:
            message: Human-readable error message
            stage: Stage of analysis where the error occurred
            details: Additional error details
        """
        self.stage = stage
        self.details = details
        full_message = f"Analysis failed: {message}"
        if stage:
            full_message += f" (stage: {stage})"
        super().__init__(full_message)

    def to_error_response_dict(self) -> dict:
        """Convert to ErrorResponse-compatible dictionary.

        Returns:
            Dictionary suitable for ErrorResponse model construction
        """
        return {
            "error": "ANALYSIS_FAILED",
            "message": self.message,
            "details": self.details,
        }


class UnknownAgentTypeError(AlertAnalyzerError):
    """Raised when an unknown agent type is requested.

    This exception is raised when the orchestrator receives a request
    for an agent type that doesn't exist.

    Attributes:
        agent_type: The unknown agent type that was requested
        message: Human-readable error message

    Example:
        >>> raise UnknownAgentTypeError("market_manipulation")
        UnknownAgentTypeError: Unknown agent type: market_manipulation
    """

    def __init__(self, agent_type: str):
        """Initialize UnknownAgentTypeError.

        Args:
            agent_type: The unknown agent type that was requested
        """
        self.agent_type = agent_type
        message = f"Unknown agent type: {agent_type}"
        super().__init__(message)

    def to_error_response_dict(self) -> dict:
        """Convert to ErrorResponse-compatible dictionary.

        Returns:
            Dictionary suitable for ErrorResponse model construction
        """
        return {
            "error": "UNKNOWN_AGENT_TYPE",
            "message": self.message,
        }


class ToolExecutionError(AlertAnalyzerError):
    """Raised when a tool fails to execute.

    This exception is raised when a specific tool encounters an error
    during execution that prevents it from returning valid insights.

    Attributes:
        tool_name: Name of the tool that failed
        original_error: The original exception that caused the failure
        message: Human-readable error message

    Example:
        >>> raise ToolExecutionError("market_data", ValueError("Invalid CSV"))
        ToolExecutionError: Tool execution failed: market_data - Invalid CSV
    """

    def __init__(self, tool_name: str, original_error: Optional[Exception] = None):
        """Initialize ToolExecutionError.

        Args:
            tool_name: Name of the tool that failed
            original_error: The original exception that caused the failure
        """
        self.tool_name = tool_name
        self.original_error = original_error
        error_detail = str(original_error) if original_error else "Unknown error"
        message = f"Tool execution failed: {tool_name} - {error_detail}"
        super().__init__(message)

    def to_error_response_dict(self) -> dict:
        """Convert to ErrorResponse-compatible dictionary.

        Returns:
            Dictionary suitable for ErrorResponse model construction
        """
        return {
            "error": "ANALYSIS_FAILED",
            "tool": self.tool_name,
            "message": self.message,
            "details": str(self.original_error) if self.original_error else None,
        }
