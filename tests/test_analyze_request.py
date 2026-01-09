"""Tests for analyze_request() context parameter flow.

Tests cover:
- Context parameter extraction from alert XML
- Context parameter passing to tools
- End-to-end analyze_request flow with context params
"""

import pytest

from alerts.tools.common.alert_reader import AlertReaderTool
from alerts.agents.wash_trade.agent import WashTradeAnalyzerAgent


class TestAlertReaderParseContext:
    """Tests for AlertReaderTool.parse_alert_context() method."""

    def test_parse_insider_trading_alert_xml(self, sample_alert_xml):
        """Parses insider trading alert XML to extract context."""
        context = AlertReaderTool.parse_alert_context(sample_alert_xml)

        assert context["trader_id"] == "T001"
        assert context["symbol"] == "TEST"
        assert context["trade_date"] == "2024-03-15"
        # Verify date range calculation
        assert context["start_date"] == "2024-02-14"  # 30 days before
        assert context["end_date"] == "2024-03-22"  # 7 days after

    def test_parse_context_with_genuine_alert(self, test_data_dir):
        """Parses real alert file to extract context."""
        alert_path = test_data_dir / "alerts" / "alert_genuine.xml"
        xml_content = alert_path.read_text()

        context = AlertReaderTool.parse_alert_context(xml_content)

        assert context["trader_id"] == "T001"
        assert context["symbol"] == "ACME"
        assert context["trade_date"] == "2024-03-15"

    def test_parse_context_missing_trader_id_raises(self):
        """Raises ValueError when TraderID is missing."""
        xml = """<?xml version="1.0"?>
        <Alert>
            <Symbol>TEST</Symbol>
            <TradeDate>2024-03-15</TradeDate>
        </Alert>
        """
        with pytest.raises(ValueError, match="TraderID"):
            AlertReaderTool.parse_alert_context(xml)

    def test_parse_context_missing_symbol_raises(self):
        """Raises ValueError when Symbol is missing."""
        xml = """<?xml version="1.0"?>
        <Alert>
            <TraderID>T001</TraderID>
            <TradeDate>2024-03-15</TradeDate>
        </Alert>
        """
        with pytest.raises(ValueError, match="Symbol"):
            AlertReaderTool.parse_alert_context(xml)

    def test_parse_context_missing_trade_date_raises(self):
        """Raises ValueError when TradeDate is missing."""
        xml = """<?xml version="1.0"?>
        <Alert>
            <TraderID>T001</TraderID>
            <Symbol>TEST</Symbol>
        </Alert>
        """
        with pytest.raises(ValueError, match="TradeDate"):
            AlertReaderTool.parse_alert_context(xml)

    def test_parse_context_invalid_date_format_raises(self):
        """Raises ValueError for invalid date format."""
        xml = """<?xml version="1.0"?>
        <Alert>
            <TraderID>T001</TraderID>
            <Symbol>TEST</Symbol>
            <TradeDate>15-03-2024</TradeDate>
        </Alert>
        """
        with pytest.raises(ValueError, match="Invalid trade date format"):
            AlertReaderTool.parse_alert_context(xml)


class TestWashTradeParseContext:
    """Tests for WashTradeAnalyzerAgent.parse_wash_trade_context() method."""

    @pytest.fixture
    def sample_wash_trade_xml(self):
        """Return sample wash trade alert XML."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<SmartsAlert>
    <AlertMetadata>
        <AlertID>WT-2024-TEST</AlertID>
        <AlertType>WashTrade</AlertType>
    </AlertMetadata>
    <FlaggedTrades>
        <Trade sequence="1">
            <AccountID>ACC-001</AccountID>
            <TradeDate>2024-01-15</TradeDate>
            <TradeTime>14:32:15.123</TradeTime>
            <Symbol>AAPL</Symbol>
            <Quantity>10000</Quantity>
        </Trade>
        <Trade sequence="2">
            <AccountID>ACC-002</AccountID>
            <TradeDate>2024-01-15</TradeDate>
            <TradeTime>14:32:15.625</TradeTime>
            <Symbol>AAPL</Symbol>
            <Quantity>10000</Quantity>
        </Trade>
    </FlaggedTrades>
</SmartsAlert>
"""

    def test_parse_wash_trade_context(self, sample_wash_trade_xml):
        """Parses wash trade alert XML to extract context."""
        context = WashTradeAnalyzerAgent.parse_wash_trade_context(sample_wash_trade_xml)

        assert context["account_ids"] == "ACC-001,ACC-002"
        assert context["symbol"] == "AAPL"
        assert context["trade_date"] == "2024-01-15"
        assert context["trade1_timestamp"] == "14:32:15.123"
        assert context["trade2_timestamp"] == "14:32:15.625"
        assert context["trade_quantity"] == "10000"
        # Verify date range
        assert context["start_date"] == "2023-12-16"  # 30 days before
        assert context["end_date"] == "2024-01-22"  # 7 days after

    def test_parse_wash_trade_context_from_file(self, test_data_dir):
        """Parses real wash trade alert file."""
        alert_path = test_data_dir / "alerts" / "wash_trade" / "wash_genuine.xml"
        xml_content = alert_path.read_text()

        context = WashTradeAnalyzerAgent.parse_wash_trade_context(xml_content)

        assert context["symbol"] == "AAPL"
        assert "ACC-001" in context["account_ids"]
        assert context["trade_date"] == "2024-01-15"

    def test_parse_wash_trade_missing_account_id_raises(self):
        """Raises ValueError when AccountID is missing."""
        xml = """<Alert>
            <Symbol>AAPL</Symbol>
            <TradeDate>2024-01-15</TradeDate>
        </Alert>"""
        with pytest.raises(ValueError, match="AccountID"):
            WashTradeAnalyzerAgent.parse_wash_trade_context(xml)

    def test_parse_wash_trade_single_account(self):
        """Handles single account ID."""
        xml = """<Alert>
            <AccountID>ACC-001</AccountID>
            <Symbol>AAPL</Symbol>
            <TradeDate>2024-01-15</TradeDate>
        </Alert>"""
        context = WashTradeAnalyzerAgent.parse_wash_trade_context(xml)
        assert context["account_ids"] == "ACC-001"

    def test_parse_wash_trade_no_timestamps(self):
        """Handles missing timestamps gracefully."""
        xml = """<Alert>
            <AccountID>ACC-001</AccountID>
            <Symbol>AAPL</Symbol>
            <TradeDate>2024-01-15</TradeDate>
        </Alert>"""
        context = WashTradeAnalyzerAgent.parse_wash_trade_context(xml)
        assert context["trade1_timestamp"] == ""
        assert context["trade2_timestamp"] == ""


class TestBuildContextParams:
    """Tests for _build_context_params() methods in agents."""

    def test_insider_trading_context_params(self, test_data_dir, mock_llm, output_dir):
        """IT agent builds correct context params for each tool."""
        from alerts.agents.insider_trading.agent import InsiderTradingAnalyzerAgent

        agent = InsiderTradingAnalyzerAgent(
            llm=mock_llm,
            data_dir=test_data_dir,
            output_dir=output_dir,
        )

        context = {
            "trader_id": "T001",
            "symbol": "ACME",
            "trade_date": "2024-03-15",
            "start_date": "2024-02-14",
            "end_date": "2024-03-22",
        }

        params = agent._build_context_params(context)

        # Verify market_news params
        assert params["query_market_news"]["symbol"] == "ACME"
        assert params["query_market_news"]["start_date"] == "2024-02-14"
        assert params["query_market_news"]["end_date"] == "2024-03-22"

        # Verify market_data params
        assert params["query_market_data"]["symbol"] == "ACME"

        # Verify trader_profile params
        assert params["query_trader_profile"]["trader_id"] == "T001"

        # Verify trader_history params
        assert params["query_trader_history"]["trader_id"] == "T001"
        assert params["query_trader_history"]["symbol"] == "ACME"
        assert params["query_trader_history"]["trade_date"] == "2024-03-15"

    def test_wash_trade_context_params(self, test_data_dir, mock_llm, output_dir):
        """WT agent builds correct context params for each tool."""
        agent = WashTradeAnalyzerAgent(
            llm=mock_llm,
            data_dir=test_data_dir,
            output_dir=output_dir,
        )

        context = {
            "account_ids": "ACC-001,ACC-002",
            "symbol": "AAPL",
            "trade_date": "2024-01-15",
            "trade1_timestamp": "14:32:15.123",
            "trade2_timestamp": "14:32:15.625",
            "trade_quantity": "10000",
            "start_date": "2023-12-16",
            "end_date": "2024-01-22",
        }

        params = agent._build_context_params(context)

        # Verify market_data params
        assert params["query_market_data"]["symbol"] == "AAPL"
        assert params["query_market_data"]["start_date"] == "2023-12-16"

        # Verify account_relationships params
        assert params["account_relationships"]["account_ids"] == "ACC-001,ACC-002"

        # Verify related_accounts_history params
        assert params["related_accounts_history"]["account_ids"] == "ACC-001,ACC-002"
        assert params["related_accounts_history"]["symbol"] == "AAPL"

        # Verify trade_timing params
        assert params["trade_timing"]["trade1_timestamp"] == "14:32:15.123"
        assert params["trade_timing"]["trade2_timestamp"] == "14:32:15.625"
        assert params["trade_timing"]["symbol"] == "AAPL"
        assert params["trade_timing"]["trade_quantity"] == "10000"


class TestDateRangeCalculation:
    """Tests for date range calculation in context parsing."""

    def test_date_range_30_days_before(self):
        """Start date is 30 days before trade date."""
        xml = """<Alert>
            <TraderID>T001</TraderID>
            <Symbol>TEST</Symbol>
            <TradeDate>2024-03-31</TradeDate>
        </Alert>"""
        context = AlertReaderTool.parse_alert_context(xml)

        # March 31 - 30 days = March 1
        assert context["start_date"] == "2024-03-01"

    def test_date_range_7_days_after(self):
        """End date is 7 days after trade date."""
        xml = """<Alert>
            <TraderID>T001</TraderID>
            <Symbol>TEST</Symbol>
            <TradeDate>2024-03-25</TradeDate>
        </Alert>"""
        context = AlertReaderTool.parse_alert_context(xml)

        # March 25 + 7 days = April 1
        assert context["end_date"] == "2024-04-01"

    def test_date_range_crosses_year_boundary(self):
        """Handles date range crossing year boundary."""
        xml = """<Alert>
            <TraderID>T001</TraderID>
            <Symbol>TEST</Symbol>
            <TradeDate>2024-01-15</TradeDate>
        </Alert>"""
        context = AlertReaderTool.parse_alert_context(xml)

        # Jan 15 - 30 days = Dec 16 (previous year)
        assert context["start_date"] == "2023-12-16"
        assert context["end_date"] == "2024-01-22"
