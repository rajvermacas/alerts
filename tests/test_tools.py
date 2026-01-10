"""Tests for SMARTS Alert Analyzer tools.

Tests the proactive information flow pattern where tools receive
data via execute() method rather than loading their own data.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from alerts.tools.common.alert_reader import AlertReaderTool
from alerts.agents.insider_trading.tools.trader_history import TraderHistoryTool
from alerts.tools.common.trader_profile import TraderProfileTool
from alerts.agents.insider_trading.tools.market_news import MarketNewsTool
from alerts.tools.common.market_data import MarketDataTool


class TestAlertReaderTool:
    """Tests for AlertReaderTool using proactive execute() pattern."""

    def test_initialization(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test tool initialization."""
        tool = AlertReaderTool(mock_llm, test_data_dir)

        assert tool.name == "read_alert"
        assert "alert" in tool.description.lower()
        assert tool.call_count == 0
        assert tool.expected_format == "xml"

    def test_build_interpretation_prompt(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test prompt building."""
        tool = AlertReaderTool(mock_llm, test_data_dir)
        raw_data = "<test>data</test>"

        prompt = tool._build_interpretation_prompt(raw_data)

        assert "compliance analyst" in prompt.lower()
        assert raw_data in prompt

    def test_execute_with_xml_data(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test execute() with injected XML data."""
        tool = AlertReaderTool(mock_llm, test_data_dir)
        xml_data = "<Alert><AlertID>TEST-001</AlertID></Alert>"

        result = tool.execute(data=xml_data, format="xml")

        assert result == "Mock LLM response for testing"
        assert tool.call_count == 1
        assert mock_llm.invoke.called

    def test_execute_wrong_format_raises(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test execute() raises error for wrong format."""
        from alerts.exceptions import InvalidFormatError
        tool = AlertReaderTool(mock_llm, test_data_dir)

        with pytest.raises(InvalidFormatError):
            tool.execute(data="some data", format="csv")

    def test_execute_empty_data_raises(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test execute() raises error for empty data."""
        from alerts.exceptions import MissingToolDataError
        tool = AlertReaderTool(mock_llm, test_data_dir)

        with pytest.raises(MissingToolDataError):
            tool.execute(data="", format="xml")


class TestTraderHistoryTool:
    """Tests for TraderHistoryTool using proactive execute() pattern."""

    def test_initialization(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test tool initialization."""
        tool = TraderHistoryTool(mock_llm, test_data_dir)

        assert tool.name == "query_trader_history"
        assert "historical" in tool.description.lower()
        assert tool.expected_format == "csv"

    def test_execute_with_csv_data(self, mock_llm: MagicMock, test_data_dir: Path, sample_trader_history_csv: str):
        """Test execute() with injected CSV data."""
        tool = TraderHistoryTool(mock_llm, test_data_dir)

        result = tool.execute(
            data=sample_trader_history_csv,
            format="csv",
            trader_id="T001",
            symbol="ACME",
            trade_date="2024-03-15"
        )

        assert result == "Mock LLM response for testing"
        assert tool.call_count == 1

    def test_build_interpretation_prompt_includes_context(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test prompt includes trader context."""
        tool = TraderHistoryTool(mock_llm, test_data_dir)

        prompt = tool._build_interpretation_prompt(
            "test data",
            trader_id="T001",
            symbol="ACME",
            trade_date="2024-03-15"
        )

        assert "T001" in prompt
        assert "ACME" in prompt
        assert "2024-03-15" in prompt


class TestTraderProfileTool:
    """Tests for TraderProfileTool using proactive execute() pattern."""

    def test_initialization(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test tool initialization."""
        tool = TraderProfileTool(mock_llm, test_data_dir)

        assert tool.name == "query_trader_profile"
        assert "profile" in tool.description.lower()
        assert tool.expected_format == "csv"

    def test_execute_with_csv_data(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test execute() with injected CSV data."""
        tool = TraderProfileTool(mock_llm, test_data_dir)
        csv_data = "trader_id,role,department\nT001,TRADER,Equities"

        result = tool.execute(data=csv_data, format="csv", trader_id="T001")

        assert result == "Mock LLM response for testing"
        assert tool.call_count == 1


class TestMarketNewsTool:
    """Tests for MarketNewsTool using proactive execute() pattern."""

    def test_initialization(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test tool initialization."""
        tool = MarketNewsTool(mock_llm, test_data_dir)

        assert tool.name == "query_market_news"
        assert "news" in tool.description.lower()
        assert tool.expected_format == "txt"

    def test_execute_with_txt_data(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test execute() with injected text data."""
        tool = MarketNewsTool(mock_llm, test_data_dir)
        news_data = "2024-03-15: ACME announces Q1 earnings beat"

        result = tool.execute(
            data=news_data,
            format="txt",
            symbol="ACME",
            start_date="2024-03-08",
            end_date="2024-03-20"
        )

        assert result == "Mock LLM response for testing"
        assert tool.call_count == 1


class TestMarketDataTool:
    """Tests for MarketDataTool using proactive execute() pattern."""

    def test_initialization(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test tool initialization."""
        tool = MarketDataTool(mock_llm, test_data_dir)

        assert tool.name == "query_market_data"
        assert "market" in tool.description.lower()
        assert tool.expected_format == "csv"

    def test_execute_with_csv_data(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test execute() with injected CSV data."""
        tool = MarketDataTool(mock_llm, test_data_dir)
        csv_data = "symbol,date,open,high,low,close,volume\nACME,2024-03-15,100,105,99,103,50000"

        result = tool.execute(
            data=csv_data,
            format="csv",
            symbol="ACME",
            start_date="2024-03-08",
            end_date="2024-03-20"
        )

        assert result == "Mock LLM response for testing"
        assert tool.call_count == 1


class TestToolStatistics:
    """Tests for tool statistics tracking."""

    def test_stats_tracking(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test that tools track call statistics."""
        tool = TraderProfileTool(mock_llm, test_data_dir)
        csv_data = "trader_id,role,department\nT001,TRADER,Equities"

        # Make multiple calls using execute()
        tool.execute(data=csv_data, format="csv", trader_id="T001")
        tool.execute(data=csv_data, format="csv", trader_id="T002")

        stats = tool.get_stats()

        assert stats["name"] == "query_trader_profile"
        assert stats["call_count"] == 2
        assert stats["total_time_seconds"] >= 0
        assert stats["avg_time_per_call"] >= 0

    def test_stats_initial_state(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test statistics start at zero."""
        tool = TraderProfileTool(mock_llm, test_data_dir)

        stats = tool.get_stats()

        assert stats["call_count"] == 0
        assert stats["total_time_seconds"] == 0
        assert stats["avg_time_per_call"] == 0


class TestToolExecution:
    """Tests for proactive execution pattern features."""

    def test_execute_with_stream_writer(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test execute() emits events via stream_writer."""
        tool = TraderProfileTool(mock_llm, test_data_dir)
        csv_data = "trader_id,role,department\nT001,TRADER,Equities"

        events = []
        def capture_event(event):
            events.append(event)

        result = tool.execute(
            data=csv_data,
            format="csv",
            config={"stream_writer": capture_event},
            trader_id="T001"
        )

        assert result == "Mock LLM response for testing"
        # Should have emitted tool_started, tool_progress, tool_completed events
        event_types = [e["event_type"] for e in events]
        assert "tool_started" in event_types
        assert "tool_completed" in event_types

    def test_execute_without_stream_writer(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test execute() works without stream_writer."""
        tool = TraderProfileTool(mock_llm, test_data_dir)
        csv_data = "trader_id,role,department\nT001,TRADER,Equities"

        # Should not raise even without stream_writer
        result = tool.execute(data=csv_data, format="csv", trader_id="T001")

        assert result == "Mock LLM response for testing"
