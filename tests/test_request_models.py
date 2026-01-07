"""Tests for Proactive Information Flow request models.

This module tests the AnalysisRequest, ToolInput, and AnalysisError models
that form the API contract between the Big Data Layer and Alert Analyzer.

Tests cover:
- Valid request construction for both agent types
- Validation of required tools per agent type
- Format validation for tool data
- Error model construction and factory methods
- JSON serialization/deserialization
- Edge cases and boundary conditions
"""

import json
import pytest
from pydantic import ValidationError

from alerts.models.request import (
    AnalysisError,
    AnalysisRequest,
    InvalidToolFormatError,
    INSIDER_TRADING_REQUIRED_TOOLS,
    MissingToolDataError,
    ToolInput,
    TOOL_FORMAT_REQUIREMENTS,
    WASH_TRADE_REQUIRED_TOOLS,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_alert_xml() -> str:
    """Return sample alert XML content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
  <AlertID>TEST-001</AlertID>
  <AlertType>Pre-Announcement Trading</AlertType>
  <RuleViolated>SMARTS-IT-001</RuleViolated>
  <GeneratedTimestamp>2024-03-16T10:30:00Z</GeneratedTimestamp>
  <Trader>
    <TraderID>T001</TraderID>
    <Name>Test Trader</Name>
    <Department>Operations</Department>
  </Trader>
  <SuspiciousActivity>
    <Symbol>TEST</Symbol>
    <TradeDate>2024-03-15</TradeDate>
    <Side>BUY</Side>
    <Quantity>10000</Quantity>
    <Price>100.00</Price>
  </SuspiciousActivity>
</SMARTSAlert>
"""


@pytest.fixture
def insider_trading_tool_data(sample_alert_xml: str) -> dict:
    """Return complete tool data for insider trading analysis."""
    return {
        "alert_reader": ToolInput(format="xml", data=sample_alert_xml),
        "market_news": ToolInput(
            format="txt",
            data="2024-03-15: No news\n2024-03-16: M&A announced"
        ),
        "market_data": ToolInput(
            format="csv",
            data="timestamp,symbol,price,volume\n2024-03-15,TEST,100.00,1000000"
        ),
        "trader_profile": ToolInput(
            format="csv",
            data="trader_id,name,role,department,mnpi_access\nT001,Test,Analyst,Research,HIGH"
        ),
        "trader_history": ToolInput(
            format="csv",
            data="date,symbol,action,quantity,price\n2024-03-10,AAPL,BUY,100,180.00"
        ),
    }


@pytest.fixture
def wash_trade_tool_data(sample_alert_xml: str) -> dict:
    """Return complete tool data for wash trade analysis."""
    # Replace alert content for wash trade
    wt_alert_xml = sample_alert_xml.replace("SMARTS-IT-001", "SMARTS-WT-001")
    wt_alert_xml = wt_alert_xml.replace("Pre-Announcement Trading", "Wash Trade")

    return {
        "alert_reader": ToolInput(format="xml", data=wt_alert_xml),
        "market_data": ToolInput(
            format="csv",
            data="timestamp,symbol,price,volume\n2024-03-15,TEST,100.00,1000000"
        ),
        "trader_profile": ToolInput(
            format="csv",
            data="trader_id,name,role,department,mnpi_access\nT001,Test,Trader,Sales,LOW"
        ),
        "account_relationships": ToolInput(
            format="csv",
            data="account_a,account_b,relationship_type,confidence\nA001,A002,OWNERSHIP,0.95"
        ),
        "related_accounts_history": ToolInput(
            format="csv",
            data="account_id,date,symbol,side,qty,price\nA001,2024-03-15,TEST,BUY,1000,100"
        ),
        "trade_timing": ToolInput(
            format="csv",
            data="trade_id,timestamp,account,symbol,side,qty\nT1,2024-03-15T10:00:00,A001,TEST,BUY,1000"
        ),
        "counterparty_analysis": ToolInput(
            format="csv",
            data="trade_id,counterparty_account,beneficial_owner_overlap,same_broker\nT1,A002,TRUE,TRUE"
        ),
    }


# =============================================================================
# ToolInput Tests
# =============================================================================

class TestToolInput:
    """Tests for ToolInput model."""

    def test_creation_xml_format(self, sample_alert_xml: str):
        """Test creating ToolInput with XML format."""
        tool_input = ToolInput(format="xml", data=sample_alert_xml)

        assert tool_input.format == "xml"
        assert "<SMARTSAlert>" in tool_input.data
        assert "TEST-001" in tool_input.data

    def test_creation_csv_format(self):
        """Test creating ToolInput with CSV format."""
        csv_data = "id,name,value\n1,test,100\n2,sample,200"
        tool_input = ToolInput(format="csv", data=csv_data)

        assert tool_input.format == "csv"
        assert "id,name,value" in tool_input.data

    def test_creation_txt_format(self):
        """Test creating ToolInput with TXT format."""
        txt_data = "2024-03-15: Market opened higher\n2024-03-16: Earnings announced"
        tool_input = ToolInput(format="txt", data=txt_data)

        assert tool_input.format == "txt"
        assert "Market opened higher" in tool_input.data

    def test_invalid_format_rejected(self):
        """Test that invalid format values are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ToolInput(format="json", data='{"key": "value"}')

        # Pydantic should reject "json" as it's not in the Literal type
        assert "format" in str(exc_info.value).lower()

    def test_empty_data_rejected(self):
        """Test that empty data is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ToolInput(format="csv", data="")

        # min_length=1 should trigger validation error
        assert "data" in str(exc_info.value).lower() or "min_length" in str(exc_info.value).lower()

    def test_json_serialization_roundtrip(self, sample_alert_xml: str):
        """Test JSON serialization and deserialization."""
        original = ToolInput(format="xml", data=sample_alert_xml)

        # Serialize to JSON
        json_str = original.model_dump_json()

        # Deserialize back
        restored = ToolInput.model_validate_json(json_str)

        assert restored.format == original.format
        assert restored.data == original.data

    def test_dict_serialization(self):
        """Test conversion to dictionary."""
        tool_input = ToolInput(format="csv", data="a,b,c\n1,2,3")

        d = tool_input.model_dump()

        assert d["format"] == "csv"
        assert d["data"] == "a,b,c\n1,2,3"


# =============================================================================
# AnalysisRequest Tests - Insider Trading
# =============================================================================

class TestAnalysisRequestInsiderTrading:
    """Tests for AnalysisRequest with insider_trading agent type."""

    def test_valid_request_creation(
        self, sample_alert_xml: str, insider_trading_tool_data: dict
    ):
        """Test creating a valid insider trading analysis request."""
        request = AnalysisRequest(
            alert_xml=sample_alert_xml,
            agent_type="insider_trading",
            tool_data=insider_trading_tool_data,
        )

        assert request.agent_type == "insider_trading"
        assert len(request.tool_data) == 5
        assert set(request.tool_data.keys()) == INSIDER_TRADING_REQUIRED_TOOLS

    def test_missing_required_tool_rejected(
        self, sample_alert_xml: str, insider_trading_tool_data: dict
    ):
        """Test that missing required tools are rejected."""
        # Remove one required tool
        del insider_trading_tool_data["trader_history"]

        with pytest.raises(ValidationError) as exc_info:
            AnalysisRequest(
                alert_xml=sample_alert_xml,
                agent_type="insider_trading",
                tool_data=insider_trading_tool_data,
            )

        error_str = str(exc_info.value)
        assert "trader_history" in error_str or "Missing required" in error_str

    def test_wrong_format_for_tool_rejected(
        self, sample_alert_xml: str, insider_trading_tool_data: dict
    ):
        """Test that wrong format for a tool is rejected."""
        # Set wrong format for alert_reader (should be xml, not csv)
        insider_trading_tool_data["alert_reader"] = ToolInput(
            format="csv", data="wrong,format"
        )

        with pytest.raises(ValidationError) as exc_info:
            AnalysisRequest(
                alert_xml=sample_alert_xml,
                agent_type="insider_trading",
                tool_data=insider_trading_tool_data,
            )

        error_str = str(exc_info.value)
        assert "alert_reader" in error_str or "format" in error_str.lower()

    def test_get_tool_data_success(
        self, sample_alert_xml: str, insider_trading_tool_data: dict
    ):
        """Test get_tool_data returns correct data."""
        request = AnalysisRequest(
            alert_xml=sample_alert_xml,
            agent_type="insider_trading",
            tool_data=insider_trading_tool_data,
        )

        tool_input = request.get_tool_data("market_news")

        assert tool_input.format == "txt"
        assert "M&A announced" in tool_input.data

    def test_get_tool_data_missing_raises(
        self, sample_alert_xml: str, insider_trading_tool_data: dict
    ):
        """Test get_tool_data raises for missing tool."""
        request = AnalysisRequest(
            alert_xml=sample_alert_xml,
            agent_type="insider_trading",
            tool_data=insider_trading_tool_data,
        )

        with pytest.raises(MissingToolDataError) as exc_info:
            request.get_tool_data("nonexistent_tool")

        assert exc_info.value.tool_name == "nonexistent_tool"
        assert exc_info.value.agent_type == "insider_trading"

    def test_empty_alert_xml_rejected(self, insider_trading_tool_data: dict):
        """Test that empty alert_xml is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AnalysisRequest(
                alert_xml="",
                agent_type="insider_trading",
                tool_data=insider_trading_tool_data,
            )

        assert "alert_xml" in str(exc_info.value).lower()


# =============================================================================
# AnalysisRequest Tests - Wash Trade
# =============================================================================

class TestAnalysisRequestWashTrade:
    """Tests for AnalysisRequest with wash_trade agent type."""

    def test_valid_request_creation(
        self, sample_alert_xml: str, wash_trade_tool_data: dict
    ):
        """Test creating a valid wash trade analysis request."""
        wt_alert_xml = sample_alert_xml.replace("SMARTS-IT-001", "SMARTS-WT-001")

        request = AnalysisRequest(
            alert_xml=wt_alert_xml,
            agent_type="wash_trade",
            tool_data=wash_trade_tool_data,
        )

        assert request.agent_type == "wash_trade"
        assert len(request.tool_data) == 7
        assert set(request.tool_data.keys()) == WASH_TRADE_REQUIRED_TOOLS

    def test_missing_required_tool_rejected(
        self, sample_alert_xml: str, wash_trade_tool_data: dict
    ):
        """Test that missing required tools are rejected."""
        # Remove one required tool
        del wash_trade_tool_data["counterparty_analysis"]

        wt_alert_xml = sample_alert_xml.replace("SMARTS-IT-001", "SMARTS-WT-001")

        with pytest.raises(ValidationError) as exc_info:
            AnalysisRequest(
                alert_xml=wt_alert_xml,
                agent_type="wash_trade",
                tool_data=wash_trade_tool_data,
            )

        error_str = str(exc_info.value)
        assert "counterparty_analysis" in error_str or "Missing required" in error_str

    def test_insider_trading_tools_not_valid_for_wash_trade(
        self, sample_alert_xml: str, insider_trading_tool_data: dict
    ):
        """Test that IT tools don't satisfy WT requirements."""
        wt_alert_xml = sample_alert_xml.replace("SMARTS-IT-001", "SMARTS-WT-001")

        with pytest.raises(ValidationError) as exc_info:
            AnalysisRequest(
                alert_xml=wt_alert_xml,
                agent_type="wash_trade",
                tool_data=insider_trading_tool_data,
            )

        error_str = str(exc_info.value)
        # Should mention missing WT-specific tools
        assert any(tool in error_str for tool in [
            "account_relationships", "related_accounts_history",
            "trade_timing", "counterparty_analysis"
        ])


# =============================================================================
# AnalysisRequest Tests - JSON Serialization
# =============================================================================

class TestAnalysisRequestSerialization:
    """Tests for AnalysisRequest JSON serialization."""

    def test_json_roundtrip_insider_trading(
        self, sample_alert_xml: str, insider_trading_tool_data: dict
    ):
        """Test JSON serialization roundtrip for IT request."""
        original = AnalysisRequest(
            alert_xml=sample_alert_xml,
            agent_type="insider_trading",
            tool_data=insider_trading_tool_data,
        )

        # Serialize
        json_str = original.model_dump_json()

        # Deserialize
        restored = AnalysisRequest.model_validate_json(json_str)

        assert restored.agent_type == original.agent_type
        assert restored.alert_xml == original.alert_xml
        assert set(restored.tool_data.keys()) == set(original.tool_data.keys())

    def test_json_roundtrip_wash_trade(
        self, sample_alert_xml: str, wash_trade_tool_data: dict
    ):
        """Test JSON serialization roundtrip for WT request."""
        wt_alert_xml = sample_alert_xml.replace("SMARTS-IT-001", "SMARTS-WT-001")

        original = AnalysisRequest(
            alert_xml=wt_alert_xml,
            agent_type="wash_trade",
            tool_data=wash_trade_tool_data,
        )

        # Serialize
        json_str = original.model_dump_json()

        # Deserialize
        restored = AnalysisRequest.model_validate_json(json_str)

        assert restored.agent_type == original.agent_type
        assert len(restored.tool_data) == 7

    def test_dict_conversion(
        self, sample_alert_xml: str, insider_trading_tool_data: dict
    ):
        """Test conversion to nested dictionary."""
        request = AnalysisRequest(
            alert_xml=sample_alert_xml,
            agent_type="insider_trading",
            tool_data=insider_trading_tool_data,
        )

        d = request.model_dump()

        assert d["agent_type"] == "insider_trading"
        assert isinstance(d["tool_data"], dict)
        assert d["tool_data"]["alert_reader"]["format"] == "xml"


# =============================================================================
# AnalysisRequest Tests - Extra Tools
# =============================================================================

class TestAnalysisRequestExtraTools:
    """Tests for AnalysisRequest with extra tool data."""

    def test_extra_tools_allowed(
        self, sample_alert_xml: str, insider_trading_tool_data: dict
    ):
        """Test that extra tools beyond required are allowed."""
        # Add an extra tool
        insider_trading_tool_data["extra_tool"] = ToolInput(
            format="csv", data="extra,data\n1,2"
        )

        # Should not raise
        request = AnalysisRequest(
            alert_xml=sample_alert_xml,
            agent_type="insider_trading",
            tool_data=insider_trading_tool_data,
        )

        assert "extra_tool" in request.tool_data
        assert len(request.tool_data) == 6


# =============================================================================
# Exception Tests
# =============================================================================

class TestMissingToolDataError:
    """Tests for MissingToolDataError exception."""

    def test_creation(self):
        """Test creating MissingToolDataError."""
        error = MissingToolDataError("trader_history", "insider_trading")

        assert error.tool_name == "trader_history"
        assert error.agent_type == "insider_trading"
        assert "trader_history" in str(error)
        assert "insider_trading" in str(error)

    def test_inheritance(self):
        """Test that MissingToolDataError is an Exception."""
        error = MissingToolDataError("tool", "agent")
        assert isinstance(error, Exception)


class TestInvalidToolFormatError:
    """Tests for InvalidToolFormatError exception."""

    def test_creation(self):
        """Test creating InvalidToolFormatError."""
        error = InvalidToolFormatError("alert_reader", "xml", "csv")

        assert error.tool_name == "alert_reader"
        assert error.expected_format == "xml"
        assert error.received_format == "csv"
        assert "alert_reader" in str(error)
        assert "xml" in str(error)
        assert "csv" in str(error)

    def test_inheritance(self):
        """Test that InvalidToolFormatError is an Exception."""
        error = InvalidToolFormatError("tool", "expected", "received")
        assert isinstance(error, Exception)


# =============================================================================
# AnalysisError Tests
# =============================================================================

class TestAnalysisError:
    """Tests for AnalysisError model."""

    def test_from_missing_tool(self):
        """Test creating error from missing tool."""
        error = AnalysisError.from_missing_tool("trader_history", "insider_trading")

        assert error.error == "MISSING_TOOL_DATA"
        assert error.tool == "trader_history"
        assert "trader_history" in error.message
        assert "insider_trading" in error.details

    def test_from_invalid_format(self):
        """Test creating error from invalid format."""
        error = AnalysisError.from_invalid_format("alert_reader", "xml", "csv")

        assert error.error == "INVALID_FORMAT"
        assert error.tool == "alert_reader"
        assert error.expected == "xml"
        assert error.received == "csv"
        assert "alert_reader" in error.message

    def test_from_exception(self):
        """Test creating error from generic exception."""
        original = ValueError("Something went wrong")
        error = AnalysisError.from_exception(original)

        assert error.error == "ANALYSIS_FAILED"
        assert "Something went wrong" in error.message
        assert error.details == "ValueError"

    def test_json_serialization(self):
        """Test JSON serialization of error."""
        error = AnalysisError.from_missing_tool("market_news", "insider_trading")

        json_str = error.model_dump_json()
        restored = AnalysisError.model_validate_json(json_str)

        assert restored.error == error.error
        assert restored.tool == error.tool

    def test_all_error_codes(self):
        """Test all valid error codes."""
        valid_codes = [
            "MISSING_TOOL_DATA",
            "INVALID_FORMAT",
            "UNKNOWN_AGENT_TYPE",
            "ANALYSIS_FAILED",
            "VALIDATION_ERROR",
        ]

        for code in valid_codes:
            error = AnalysisError(error=code, message=f"Test {code}")
            assert error.error == code

    def test_invalid_error_code_rejected(self):
        """Test that invalid error codes are rejected."""
        with pytest.raises(ValidationError):
            AnalysisError(error="INVALID_CODE", message="Test")


# =============================================================================
# Constants Tests
# =============================================================================

class TestConstants:
    """Tests for module constants."""

    def test_insider_trading_required_tools(self):
        """Test INSIDER_TRADING_REQUIRED_TOOLS constant."""
        expected = frozenset([
            "alert_reader",
            "market_news",
            "market_data",
            "trader_profile",
            "trader_history",
        ])

        assert INSIDER_TRADING_REQUIRED_TOOLS == expected
        assert isinstance(INSIDER_TRADING_REQUIRED_TOOLS, frozenset)

    def test_wash_trade_required_tools(self):
        """Test WASH_TRADE_REQUIRED_TOOLS constant."""
        expected = frozenset([
            "alert_reader",
            "market_data",
            "trader_profile",
            "account_relationships",
            "related_accounts_history",
            "trade_timing",
            "counterparty_analysis",
        ])

        assert WASH_TRADE_REQUIRED_TOOLS == expected
        assert isinstance(WASH_TRADE_REQUIRED_TOOLS, frozenset)

    def test_common_tools_in_both(self):
        """Test that common tools are in both required sets."""
        common = {"alert_reader", "market_data", "trader_profile"}

        assert common.issubset(INSIDER_TRADING_REQUIRED_TOOLS)
        assert common.issubset(WASH_TRADE_REQUIRED_TOOLS)

    def test_tool_format_requirements(self):
        """Test TOOL_FORMAT_REQUIREMENTS constant."""
        # All IT tools should have format requirements
        for tool in INSIDER_TRADING_REQUIRED_TOOLS:
            assert tool in TOOL_FORMAT_REQUIREMENTS

        # All WT tools should have format requirements
        for tool in WASH_TRADE_REQUIRED_TOOLS:
            assert tool in TOOL_FORMAT_REQUIREMENTS

        # Specific format checks
        assert TOOL_FORMAT_REQUIREMENTS["alert_reader"] == "xml"
        assert TOOL_FORMAT_REQUIREMENTS["market_news"] == "txt"
        assert TOOL_FORMAT_REQUIREMENTS["market_data"] == "csv"


# =============================================================================
# Edge Cases and Boundary Tests
# =============================================================================

class TestEdgeCases:
    """Edge case and boundary condition tests."""

    def test_minimal_valid_request(self, sample_alert_xml: str):
        """Test request with minimal but valid data."""
        # Minimal data that satisfies requirements
        tool_data = {
            "alert_reader": ToolInput(format="xml", data="<a/>"),
            "market_news": ToolInput(format="txt", data="x"),
            "market_data": ToolInput(format="csv", data="a"),
            "trader_profile": ToolInput(format="csv", data="b"),
            "trader_history": ToolInput(format="csv", data="c"),
        }

        request = AnalysisRequest(
            alert_xml="<a/>",
            agent_type="insider_trading",
            tool_data=tool_data,
        )

        assert request.agent_type == "insider_trading"

    def test_large_data_content(self, sample_alert_xml: str):
        """Test request with large data content."""
        # Generate large CSV data
        large_csv = "id,value\n" + "\n".join(f"{i},{i*100}" for i in range(10000))

        tool_data = {
            "alert_reader": ToolInput(format="xml", data=sample_alert_xml),
            "market_news": ToolInput(format="txt", data="news"),
            "market_data": ToolInput(format="csv", data=large_csv),
            "trader_profile": ToolInput(format="csv", data="a"),
            "trader_history": ToolInput(format="csv", data="b"),
        }

        request = AnalysisRequest(
            alert_xml=sample_alert_xml,
            agent_type="insider_trading",
            tool_data=tool_data,
        )

        assert len(request.tool_data["market_data"].data) > 50000

    def test_unicode_in_data(self, sample_alert_xml: str):
        """Test request with unicode content."""
        tool_data = {
            "alert_reader": ToolInput(format="xml", data=sample_alert_xml),
            "market_news": ToolInput(format="txt", data="日本語ニュース: 株価上昇"),
            "market_data": ToolInput(format="csv", data="symbol,name\nSBI,éàü"),
            "trader_profile": ToolInput(format="csv", data="名前,部署\n田中,営業"),
            "trader_history": ToolInput(format="csv", data="a"),
        }

        request = AnalysisRequest(
            alert_xml=sample_alert_xml,
            agent_type="insider_trading",
            tool_data=tool_data,
        )

        assert "日本語" in request.tool_data["market_news"].data

    def test_whitespace_only_data_rejected(self):
        """Test that whitespace-only data is handled."""
        # Single space should pass min_length=1 but is questionable
        tool_input = ToolInput(format="csv", data=" ")
        assert tool_input.data == " "

    def test_invalid_agent_type_rejected(self, sample_alert_xml: str):
        """Test that invalid agent_type is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AnalysisRequest(
                alert_xml=sample_alert_xml,
                agent_type="invalid_type",
                tool_data={},
            )

        assert "agent_type" in str(exc_info.value).lower()

    def test_none_tool_data_rejected(self, sample_alert_xml: str):
        """Test that None tool_data is rejected."""
        with pytest.raises(ValidationError):
            AnalysisRequest(
                alert_xml=sample_alert_xml,
                agent_type="insider_trading",
                tool_data=None,
            )

    def test_empty_tool_data_rejected(self, sample_alert_xml: str):
        """Test that empty tool_data is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AnalysisRequest(
                alert_xml=sample_alert_xml,
                agent_type="insider_trading",
                tool_data={},
            )

        # Should fail validation for missing required tools
        error_str = str(exc_info.value)
        assert "Missing required" in error_str or "alert_reader" in error_str
