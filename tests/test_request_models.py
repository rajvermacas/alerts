"""Tests for request/response models used in proactive information flow.

Tests cover:
- ToolInput model validation
- AnalysisRequest model validation and required tool checking
- ErrorResponse model
"""

import pytest
from pydantic import ValidationError

from alerts.models.request import (
    AnalysisRequest,
    ErrorResponse,
    ToolInput,
    REQUIRED_TOOLS_BY_AGENT,
)


class TestToolInput:
    """Tests for ToolInput model."""

    def test_valid_xml_format(self):
        """ToolInput accepts xml format."""
        tool_input = ToolInput(format="xml", data="<alert>test</alert>")
        assert tool_input.format == "xml"
        assert tool_input.data == "<alert>test</alert>"

    def test_valid_csv_format(self):
        """ToolInput accepts csv format."""
        tool_input = ToolInput(format="csv", data="col1,col2\na,b")
        assert tool_input.format == "csv"
        assert tool_input.data == "col1,col2\na,b"

    def test_valid_txt_format(self):
        """ToolInput accepts txt format."""
        tool_input = ToolInput(format="txt", data="plain text")
        assert tool_input.format == "txt"
        assert tool_input.data == "plain text"

    def test_invalid_format_raises_error(self):
        """ToolInput rejects invalid format."""
        with pytest.raises(ValidationError) as exc_info:
            ToolInput(format="invalid", data="test")
        assert "format" in str(exc_info.value)

    def test_empty_data_rejected(self):
        """ToolInput rejects empty data string (min_length=1)."""
        with pytest.raises(ValidationError) as exc_info:
            ToolInput(format="txt", data="")
        assert "data" in str(exc_info.value).lower()

    def test_missing_format_raises_error(self):
        """ToolInput requires format field."""
        with pytest.raises(ValidationError):
            ToolInput(data="test")  # type: ignore

    def test_missing_data_raises_error(self):
        """ToolInput requires data field."""
        with pytest.raises(ValidationError):
            ToolInput(format="txt")  # type: ignore


class TestAnalysisRequest:
    """Tests for AnalysisRequest model."""

    @pytest.fixture
    def complete_insider_trading_tool_data(self):
        """Return complete tool data for insider trading agent."""
        return {
            "alert_reader": ToolInput(format="xml", data="<alert>test</alert>"),
            "market_news": ToolInput(format="txt", data="news content"),
            "market_data": ToolInput(format="csv", data="col1,col2\na,b"),
            "trader_profile": ToolInput(format="csv", data="col1,col2\na,b"),
            "trader_history": ToolInput(format="csv", data="col1,col2\na,b"),
        }

    @pytest.fixture
    def complete_wash_trade_tool_data(self):
        """Return complete tool data for wash trade agent."""
        return {
            "alert_reader": ToolInput(format="xml", data="<alert>test</alert>"),
            "market_data": ToolInput(format="csv", data="col1,col2\na,b"),
            "account_relationships": ToolInput(format="csv", data="col1,col2\na,b"),
            "related_accounts_history": ToolInput(format="csv", data="col1,col2\na,b"),
            "trade_timing": ToolInput(format="csv", data="col1,col2\na,b"),
            "counterparty_analysis": ToolInput(format="csv", data="col1,col2\na,b"),
        }

    def test_valid_insider_trading_request(self, complete_insider_trading_tool_data):
        """AnalysisRequest validates with complete insider trading tools."""
        request = AnalysisRequest(
            alert_xml="<alert>test</alert>",
            agent_type="insider_trading",
            tool_data=complete_insider_trading_tool_data,
        )
        assert request.agent_type == "insider_trading"
        assert len(request.tool_data) == 5

    def test_valid_wash_trade_request(self, complete_wash_trade_tool_data):
        """AnalysisRequest validates with complete wash trade tools."""
        request = AnalysisRequest(
            alert_xml="<alert>test</alert>",
            agent_type="wash_trade",
            tool_data=complete_wash_trade_tool_data,
        )
        assert request.agent_type == "wash_trade"
        assert len(request.tool_data) == 6

    def test_missing_required_tool_raises_error(self, complete_insider_trading_tool_data):
        """AnalysisRequest rejects missing required tool."""
        del complete_insider_trading_tool_data["market_news"]

        with pytest.raises(ValidationError) as exc_info:
            AnalysisRequest(
                alert_xml="<alert>test</alert>",
                agent_type="insider_trading",
                tool_data=complete_insider_trading_tool_data,
            )
        assert "market_news" in str(exc_info.value)

    def test_invalid_agent_type_raises_error(self, complete_insider_trading_tool_data):
        """AnalysisRequest rejects invalid agent type."""
        with pytest.raises(ValidationError) as exc_info:
            AnalysisRequest(
                alert_xml="<alert>test</alert>",
                agent_type="unknown_agent",  # type: ignore
                tool_data=complete_insider_trading_tool_data,
            )
        assert "agent_type" in str(exc_info.value)

    def test_empty_alert_xml_raises_error(self, complete_insider_trading_tool_data):
        """AnalysisRequest rejects empty alert_xml."""
        with pytest.raises(ValidationError) as exc_info:
            AnalysisRequest(
                alert_xml="",
                agent_type="insider_trading",
                tool_data=complete_insider_trading_tool_data,
            )
        assert "alert_xml" in str(exc_info.value).lower()

    def test_extra_tools_allowed(self, complete_insider_trading_tool_data):
        """AnalysisRequest allows extra tools beyond required."""
        complete_insider_trading_tool_data["extra_tool"] = ToolInput(
            format="txt", data="extra"
        )
        request = AnalysisRequest(
            alert_xml="<alert>test</alert>",
            agent_type="insider_trading",
            tool_data=complete_insider_trading_tool_data,
        )
        assert "extra_tool" in request.tool_data

    def test_model_dump_serialization(self, complete_insider_trading_tool_data):
        """AnalysisRequest serializes correctly with model_dump."""
        request = AnalysisRequest(
            alert_xml="<alert>test</alert>",
            agent_type="insider_trading",
            tool_data=complete_insider_trading_tool_data,
        )
        data = request.model_dump()

        assert data["alert_xml"] == "<alert>test</alert>"
        assert data["agent_type"] == "insider_trading"
        assert "alert_reader" in data["tool_data"]
        assert data["tool_data"]["alert_reader"]["format"] == "xml"


class TestRequiredToolsConfig:
    """Tests for REQUIRED_TOOLS_BY_AGENT configuration."""

    def test_insider_trading_required_tools(self):
        """Verify insider trading required tools are defined."""
        assert "insider_trading" in REQUIRED_TOOLS_BY_AGENT
        required = REQUIRED_TOOLS_BY_AGENT["insider_trading"]
        assert "alert_reader" in required
        assert "market_news" in required
        assert "market_data" in required
        assert "trader_profile" in required
        assert "trader_history" in required

    def test_wash_trade_required_tools(self):
        """Verify wash trade required tools are defined."""
        assert "wash_trade" in REQUIRED_TOOLS_BY_AGENT
        required = REQUIRED_TOOLS_BY_AGENT["wash_trade"]
        assert "alert_reader" in required
        assert "market_data" in required
        assert "account_relationships" in required
        assert "related_accounts_history" in required
        assert "trade_timing" in required
        assert "counterparty_analysis" in required

    def test_wash_trade_does_not_require_trader_profile(self):
        """Verify trader_profile is NOT required for wash trade (per design decision)."""
        required = REQUIRED_TOOLS_BY_AGENT["wash_trade"]
        assert "trader_profile" not in required


class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_valid_error_response(self):
        """ErrorResponse accepts valid error data."""
        error = ErrorResponse(
            error="MISSING_TOOL_DATA",
            message="Required tool data not provided",
        )
        assert error.error == "MISSING_TOOL_DATA"
        assert error.message == "Required tool data not provided"
        assert error.details is None

    def test_error_response_with_details(self):
        """ErrorResponse accepts details field."""
        error = ErrorResponse(
            error="ANALYSIS_FAILED",
            message="Validation failed",
            details="Field 'agent_type' is required",
        )
        assert error.details == "Field 'agent_type' is required"

    def test_missing_error_raises(self):
        """ErrorResponse requires error field."""
        with pytest.raises(ValidationError):
            ErrorResponse(message="test")  # type: ignore

    def test_missing_message_raises(self):
        """ErrorResponse requires message field."""
        with pytest.raises(ValidationError):
            ErrorResponse(error="TEST")  # type: ignore
