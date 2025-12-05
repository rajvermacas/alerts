"""Tests for SMARTS Alert Analyzer tools."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from alerts.tools.common.base import BaseTool, DataLoadingMixin
from alerts.tools.alert_reader import AlertReaderTool
from alerts.tools.trader_history import TraderHistoryTool
from alerts.tools.trader_profile import TraderProfileTool
from alerts.tools.market_news import MarketNewsTool
from alerts.tools.market_data import MarketDataTool
from alerts.tools.peer_trades import PeerTradesTool


class TestDataLoadingMixin:
    """Tests for DataLoadingMixin utilities."""

    def test_filter_csv_by_column(self, sample_trader_history_csv: str):
        """Test CSV filtering by column value."""
        result = DataLoadingMixin.filter_csv_by_column(
            sample_trader_history_csv,
            "trader_id",
            "T001"
        )

        assert "trader_id" in result  # Header included
        assert "T001" in result
        assert result.count("\n") >= 1

    def test_filter_csv_by_column_not_found(self, sample_trader_history_csv: str):
        """Test CSV filtering when column not found."""
        result = DataLoadingMixin.filter_csv_by_column(
            sample_trader_history_csv,
            "nonexistent_column",
            "value"
        )

        # Should return original content when column not found
        assert result == sample_trader_history_csv

    def test_filter_csv_by_date_range(self, sample_trader_history_csv: str):
        """Test CSV filtering by date range."""
        result = DataLoadingMixin.filter_csv_by_date_range(
            sample_trader_history_csv,
            "date",
            "2024-01-01",
            "2024-01-31"
        )

        assert "2024-01-05" in result
        assert "2024-01-12" in result
        # February date should be excluded
        assert "2024-02-09" not in result


class TestAlertReaderTool:
    """Tests for AlertReaderTool."""

    def test_initialization(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test tool initialization."""
        tool = AlertReaderTool(mock_llm, test_data_dir)

        assert tool.name == "read_alert"
        assert "alert" in tool.description.lower()
        assert tool.call_count == 0

    def test_validate_input_missing_path(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test validation fails without alert_file_path."""
        tool = AlertReaderTool(mock_llm, test_data_dir)

        error = tool._validate_input()
        assert error is not None
        assert "alert_file_path" in error.lower()

    def test_validate_input_file_not_found(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test validation fails for non-existent file."""
        tool = AlertReaderTool(mock_llm, test_data_dir)

        error = tool._validate_input(alert_file_path="/nonexistent/file.xml")
        assert error is not None
        assert "not found" in error.lower()

    def test_validate_input_wrong_extension(self, mock_llm: MagicMock, test_data_dir: Path, tmp_path: Path):
        """Test validation fails for non-XML file."""
        # Create a non-XML file
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not xml")

        tool = AlertReaderTool(mock_llm, test_data_dir)
        error = tool._validate_input(alert_file_path=str(txt_file))

        assert error is not None
        assert "xml" in error.lower()

    def test_load_data(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test loading alert XML data."""
        tool = AlertReaderTool(mock_llm, test_data_dir)
        alert_path = test_data_dir / "alerts" / "alert_genuine.xml"

        data = tool._load_data(alert_file_path=alert_path)

        assert "SMARTSAlert" in data
        assert "ITA-2024-001847" in data

    def test_build_interpretation_prompt(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test prompt building."""
        tool = AlertReaderTool(mock_llm, test_data_dir)
        raw_data = "<test>data</test>"

        prompt = tool._build_interpretation_prompt(raw_data)

        assert "compliance analyst" in prompt.lower()
        assert raw_data in prompt

    def test_full_execution(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test full tool execution."""
        tool = AlertReaderTool(mock_llm, test_data_dir)
        alert_path = test_data_dir / "alerts" / "alert_genuine.xml"

        result = tool(alert_file_path=alert_path)

        assert result == "Mock LLM response for testing"
        assert tool.call_count == 1
        assert mock_llm.invoke.called


class TestTraderHistoryTool:
    """Tests for TraderHistoryTool."""

    def test_initialization(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test tool initialization."""
        tool = TraderHistoryTool(mock_llm, test_data_dir)

        assert tool.name == "query_trader_history"
        assert "historical" in tool.description.lower()

    def test_validate_input_missing_fields(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test validation fails without required fields."""
        tool = TraderHistoryTool(mock_llm, test_data_dir)

        error = tool._validate_input(trader_id="T001")
        assert error is not None
        assert "symbol" in error.lower() or "trade_date" in error.lower()

    def test_full_execution(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test full tool execution."""
        tool = TraderHistoryTool(mock_llm, test_data_dir)

        result = tool(
            trader_id="T001",
            symbol="ACME",
            trade_date="2024-03-15"
        )

        assert result == "Mock LLM response for testing"
        assert tool.call_count == 1


class TestTraderProfileTool:
    """Tests for TraderProfileTool."""

    def test_initialization(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test tool initialization."""
        tool = TraderProfileTool(mock_llm, test_data_dir)

        assert tool.name == "query_trader_profile"
        assert "profile" in tool.description.lower()

    def test_full_execution(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test full tool execution."""
        tool = TraderProfileTool(mock_llm, test_data_dir)

        result = tool(trader_id="T001")

        assert result == "Mock LLM response for testing"
        assert tool.call_count == 1


class TestMarketNewsTool:
    """Tests for MarketNewsTool."""

    def test_initialization(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test tool initialization."""
        tool = MarketNewsTool(mock_llm, test_data_dir)

        assert tool.name == "query_market_news"
        assert "news" in tool.description.lower()

    def test_full_execution(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test full tool execution."""
        tool = MarketNewsTool(mock_llm, test_data_dir)

        result = tool(
            symbol="ACME",
            start_date="2024-03-08",
            end_date="2024-03-20"
        )

        assert result == "Mock LLM response for testing"
        assert tool.call_count == 1


class TestMarketDataTool:
    """Tests for MarketDataTool."""

    def test_initialization(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test tool initialization."""
        tool = MarketDataTool(mock_llm, test_data_dir)

        assert tool.name == "query_market_data"
        assert "market" in tool.description.lower()

    def test_full_execution(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test full tool execution."""
        tool = MarketDataTool(mock_llm, test_data_dir)

        result = tool(
            symbol="ACME",
            start_date="2024-03-08",
            end_date="2024-03-20"
        )

        assert result == "Mock LLM response for testing"
        assert tool.call_count == 1


class TestPeerTradesTool:
    """Tests for PeerTradesTool."""

    def test_initialization(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test tool initialization."""
        tool = PeerTradesTool(mock_llm, test_data_dir)

        assert tool.name == "query_peer_trades"
        assert "peer" in tool.description.lower()

    def test_full_execution(self, mock_llm: MagicMock, test_data_dir: Path):
        """Test full tool execution."""
        tool = PeerTradesTool(mock_llm, test_data_dir)

        result = tool(
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

        # Make multiple calls
        tool(trader_id="T001")
        tool(trader_id="T002")

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
