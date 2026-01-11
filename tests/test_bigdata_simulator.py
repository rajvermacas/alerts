"""Tests for the BigDataSimulator mock component.

Tests cover:
- Request creation from file paths
- Request creation from XML content
- Alert type detection (insider_trading vs wash_trade)
- Tool data loading for each agent type
- XML parsing to AlertContext models

Architecture Note:
- AlertReaderTool REMOVED - alert_xml replaced with alert_context
- BigDataSimulator now parses XML to structured AlertContext
- See: .dev-resources/architecture/remove-alert-reader-tool.md
"""

import pytest
from pathlib import Path

from alerts.mock.bigdata_simulator import BigDataSimulator
from alerts.models.request import AnalysisRequest, ToolInput, REQUIRED_TOOLS_BY_AGENT
from alerts.models.alert_context import (
    InsiderTradingAlertContext,
    WashTradeAlertContext,
)


class TestBigDataSimulatorInit:
    """Tests for BigDataSimulator initialization."""

    def test_init_with_valid_path(self, test_data_dir):
        """BigDataSimulator initializes with valid data directory."""
        simulator = BigDataSimulator(str(test_data_dir))
        assert simulator.data_dir == test_data_dir

    def test_init_stores_path_as_pathlib(self):
        """BigDataSimulator stores path as pathlib.Path."""
        simulator = BigDataSimulator("/some/path")
        assert isinstance(simulator.data_dir, Path)


class TestAlertTypeDetection:
    """Tests for alert type detection logic."""

    def test_detect_insider_trading_keyword(self):
        """Detects insider trading from keyword."""
        simulator = BigDataSimulator("/tmp")
        xml = "<Alert>This is an insider trading alert</Alert>"
        result = simulator._determine_agent_type(xml)
        assert result == "insider_trading"

    def test_detect_insider_trading_mnpi(self):
        """Detects insider trading from MNPI keyword."""
        simulator = BigDataSimulator("/tmp")
        xml = "<Alert>MNPI violation detected</Alert>"
        result = simulator._determine_agent_type(xml)
        assert result == "insider_trading"

    def test_detect_insider_trading_rule_code(self):
        """Detects insider trading from rule code."""
        simulator = BigDataSimulator("/tmp")
        xml = "<Alert><RuleCode>SMARTS-IT-001</RuleCode></Alert>"
        result = simulator._determine_agent_type(xml)
        assert result == "insider_trading"

    def test_detect_wash_trade_keyword(self):
        """Detects wash trade from keyword."""
        simulator = BigDataSimulator("/tmp")
        xml = "<Alert>This is a wash trade alert</Alert>"
        result = simulator._determine_agent_type(xml)
        assert result == "wash_trade"

    def test_detect_wash_trade_self_trade(self):
        """Detects wash trade from self-trade keyword."""
        simulator = BigDataSimulator("/tmp")
        xml = "<Alert>Self-trade detected</Alert>"
        result = simulator._determine_agent_type(xml)
        assert result == "wash_trade"

    def test_detect_wash_trade_rule_code(self):
        """Detects wash trade from rule code."""
        simulator = BigDataSimulator("/tmp")
        xml = "<Alert><RuleCode>SMARTS-WT-001</RuleCode></Alert>"
        result = simulator._determine_agent_type(xml)
        assert result == "wash_trade"

    def test_default_to_insider_trading(self):
        """Defaults to insider trading when no indicators found."""
        simulator = BigDataSimulator("/tmp")
        xml = "<Alert>Generic alert without indicators</Alert>"
        result = simulator._determine_agent_type(xml)
        assert result == "insider_trading"

    def test_wash_trade_takes_priority(self):
        """Wash trade detection takes priority over insider trading."""
        simulator = BigDataSimulator("/tmp")
        # Both indicators present - wash trade should win (checked first)
        xml = "<Alert>This has wash trade and insider keywords</Alert>"
        result = simulator._determine_agent_type(xml)
        assert result == "wash_trade"


class TestCreateRequestFromFile:
    """Tests for create_request() from file path."""

    def test_create_request_from_file(self, test_data_dir):
        """Creates AnalysisRequest from alert file."""
        simulator = BigDataSimulator(str(test_data_dir))
        alert_file = str(test_data_dir / "alerts" / "alert_genuine.xml")

        request = simulator.create_request(alert_file)

        assert isinstance(request, AnalysisRequest)
        assert request.agent_type == "insider_trading"
        # NOTE: alert_reader REMOVED - context now in alert_context
        assert "alert_reader" not in request.tool_data
        assert isinstance(request.alert_context, InsiderTradingAlertContext)

    def test_create_request_nonexistent_file_raises(self, test_data_dir):
        """Raises FileNotFoundError for nonexistent file."""
        simulator = BigDataSimulator(str(test_data_dir))

        with pytest.raises(FileNotFoundError):
            simulator.create_request("/nonexistent/file.xml")


class TestCreateRequestAlertContext:
    """Tests for alert context parsing in create_request()."""

    def test_insider_trading_context_parsed(self, test_data_dir):
        """Creates InsiderTradingAlertContext from IT alert."""
        simulator = BigDataSimulator(str(test_data_dir))
        alert_file = str(test_data_dir / "alerts" / "alert_genuine.xml")

        request = simulator.create_request(alert_file)

        assert isinstance(request.alert_context, InsiderTradingAlertContext)
        assert request.alert_context.context_type == "insider_trading"
        # Verify key fields are populated
        assert request.alert_context.alert_id is not None
        assert request.alert_context.trader is not None
        assert request.alert_context.trade is not None

    def test_wash_trade_context_parsed(self, test_data_dir):
        """Creates WashTradeAlertContext from WT alert."""
        simulator = BigDataSimulator(str(test_data_dir))
        alert_file = str(test_data_dir / "alerts" / "wash_trade" / "wash_genuine.xml")

        request = simulator.create_request(alert_file)

        assert isinstance(request.alert_context, WashTradeAlertContext)
        assert request.alert_context.context_type == "wash_trade"
        # Verify key fields are populated
        assert request.alert_context.alert_id is not None
        assert len(request.alert_context.flagged_trades) >= 2


class TestInsiderTradingToolData:
    """Tests for insider trading tool data loading."""

    def test_loads_all_required_tools(self, test_data_dir):
        """Loads all required tools for insider trading."""
        simulator = BigDataSimulator(str(test_data_dir))
        alert_file = str(test_data_dir / "alerts" / "alert_genuine.xml")

        request = simulator.create_request(alert_file)

        required_tools = REQUIRED_TOOLS_BY_AGENT["insider_trading"]
        for tool_name in required_tools:
            assert tool_name in request.tool_data, f"Missing tool: {tool_name}"
            assert isinstance(request.tool_data[tool_name], ToolInput)

    def test_no_alert_reader_in_tools(self, test_data_dir):
        """Alert reader tool is NOT in tool_data (REMOVED)."""
        simulator = BigDataSimulator(str(test_data_dir))
        alert_file = str(test_data_dir / "alerts" / "alert_genuine.xml")

        request = simulator.create_request(alert_file)

        # NOTE: alert_reader REMOVED from tool_data
        assert "alert_reader" not in request.tool_data

    def test_market_news_is_txt(self, test_data_dir):
        """Market news tool has txt format."""
        simulator = BigDataSimulator(str(test_data_dir))
        alert_file = str(test_data_dir / "alerts" / "alert_genuine.xml")

        request = simulator.create_request(alert_file)

        assert request.tool_data["market_news"].format == "txt"

    def test_market_data_is_csv(self, test_data_dir):
        """Market data tool has csv format."""
        simulator = BigDataSimulator(str(test_data_dir))
        alert_file = str(test_data_dir / "alerts" / "alert_genuine.xml")

        request = simulator.create_request(alert_file)

        assert request.tool_data["market_data"].format == "csv"

    def test_trader_profile_is_csv(self, test_data_dir):
        """Trader profile tool has csv format."""
        simulator = BigDataSimulator(str(test_data_dir))
        alert_file = str(test_data_dir / "alerts" / "alert_genuine.xml")

        request = simulator.create_request(alert_file)

        assert request.tool_data["trader_profile"].format == "csv"

    def test_trader_history_is_csv(self, test_data_dir):
        """Trader history tool has csv format."""
        simulator = BigDataSimulator(str(test_data_dir))
        alert_file = str(test_data_dir / "alerts" / "alert_genuine.xml")

        request = simulator.create_request(alert_file)

        assert request.tool_data["trader_history"].format == "csv"


class TestWashTradeToolData:
    """Tests for wash trade tool data loading."""

    @pytest.fixture
    def wash_trade_alert_file(self, test_data_dir):
        """Return path to a wash trade alert file."""
        return str(test_data_dir / "alerts" / "wash_trade" / "wash_genuine.xml")

    def test_loads_all_required_tools(self, test_data_dir, wash_trade_alert_file):
        """Loads all required tools for wash trade."""
        simulator = BigDataSimulator(str(test_data_dir))

        request = simulator.create_request(wash_trade_alert_file)

        required_tools = REQUIRED_TOOLS_BY_AGENT["wash_trade"]
        for tool_name in required_tools:
            assert tool_name in request.tool_data, f"Missing tool: {tool_name}"
            assert isinstance(request.tool_data[tool_name], ToolInput)

    def test_does_not_include_trader_profile(self, test_data_dir, wash_trade_alert_file):
        """Wash trade does NOT include trader_profile (per design decision)."""
        simulator = BigDataSimulator(str(test_data_dir))

        request = simulator.create_request(wash_trade_alert_file)

        # trader_profile should NOT be in wash_trade tool data
        assert "trader_profile" not in request.tool_data

    def test_account_relationships_is_csv(self, test_data_dir, wash_trade_alert_file):
        """Account relationships tool has csv format."""
        simulator = BigDataSimulator(str(test_data_dir))

        request = simulator.create_request(wash_trade_alert_file)

        assert request.tool_data["account_relationships"].format == "csv"

    def test_trade_timing_is_csv(self, test_data_dir, wash_trade_alert_file):
        """Trade timing tool has csv format."""
        simulator = BigDataSimulator(str(test_data_dir))

        request = simulator.create_request(wash_trade_alert_file)

        assert request.tool_data["trade_timing"].format == "csv"


class TestMissingFilesHandling:
    """Tests for handling missing data files (fail-fast behavior)."""

    def test_missing_market_news_raises_error(self, tmp_path):
        """Missing market news file raises FileNotFoundError (fail-fast)."""
        # Create minimal test data structure with proper XML
        alerts_dir = tmp_path / "alerts"
        alerts_dir.mkdir(parents=True)
        alert_file = alerts_dir / "test.xml"
        # Create a proper insider trading XML matching actual structure
        # Uses: <AlertID>, <AlertType>, <RuleViolated>, <GeneratedTimestamp>,
        #       <Trader>, <SuspiciousActivity> (not <Trade>!)
        alert_file.write_text("""<?xml version="1.0"?>
<SMARTSAlert>
    <AlertID>TEST-001</AlertID>
    <AlertType>Pre-Announcement Trading</AlertType>
    <RuleViolated>SMARTS-IT-001</RuleViolated>
    <GeneratedTimestamp>2024-03-15T10:30:00Z</GeneratedTimestamp>
    <Trader>
        <TraderID>T001</TraderID>
        <Name>Test Trader</Name>
        <Department>Trading</Department>
    </Trader>
    <SuspiciousActivity>
        <Symbol>TEST</Symbol>
        <TradeDate>2024-03-15</TradeDate>
        <Side>BUY</Side>
        <Quantity>1000</Quantity>
        <Price>100.00</Price>
        <TotalValue>100000</TotalValue>
    </SuspiciousActivity>
</SMARTSAlert>""")

        simulator = BigDataSimulator(str(tmp_path))

        with pytest.raises(FileNotFoundError) as exc_info:
            simulator.create_request(str(alert_file))
        assert "market_news" in str(exc_info.value)

    def test_missing_market_data_raises_error(self, tmp_path):
        """Missing market data file raises FileNotFoundError (fail-fast)."""
        alerts_dir = tmp_path / "alerts"
        alerts_dir.mkdir(parents=True)
        alert_file = alerts_dir / "test.xml"
        # Create a proper insider trading XML matching actual structure
        alert_file.write_text("""<?xml version="1.0"?>
<SMARTSAlert>
    <AlertID>TEST-001</AlertID>
    <AlertType>Pre-Announcement Trading</AlertType>
    <RuleViolated>SMARTS-IT-001</RuleViolated>
    <GeneratedTimestamp>2024-03-15T10:30:00Z</GeneratedTimestamp>
    <Trader>
        <TraderID>T001</TraderID>
        <Name>Test Trader</Name>
        <Department>Trading</Department>
    </Trader>
    <SuspiciousActivity>
        <Symbol>TEST</Symbol>
        <TradeDate>2024-03-15</TradeDate>
        <Side>BUY</Side>
        <Quantity>1000</Quantity>
        <Price>100.00</Price>
        <TotalValue>100000</TotalValue>
    </SuspiciousActivity>
</SMARTSAlert>""")
        # Create market_news but not market_data
        (tmp_path / "market_news.txt").write_text("Test news")

        simulator = BigDataSimulator(str(tmp_path))

        with pytest.raises(FileNotFoundError) as exc_info:
            simulator.create_request(str(alert_file))
        assert "market_data" in str(exc_info.value)

    def test_missing_wash_trade_data_raises_error(self, tmp_path):
        """Missing wash trade data files raise FileNotFoundError (fail-fast)."""
        alerts_dir = tmp_path / "alerts" / "wash_trade"
        alerts_dir.mkdir(parents=True)
        alert_file = alerts_dir / "test.xml"
        # Create a proper wash trade XML that can be parsed
        alert_file.write_text("""<?xml version="1.0"?>
<Alert>
    <AlertMetadata>
        <AlertID>WT-TEST-001</AlertID>
        <AlertType>Self-Trade</AlertType>
        <RuleViolated>SMARTS-WT-001</RuleViolated>
        <GeneratedTimestamp>2024-03-15T10:30:00Z</GeneratedTimestamp>
        <Severity>HIGH</Severity>
    </AlertMetadata>
    <FlaggedTrades>
        <Trade sequence="1">
            <AccountID>ACC-001</AccountID>
            <AccountName>Test Account 1</AccountName>
            <TradeDate>2024-03-15</TradeDate>
            <TradeTime>10:30:00.123</TradeTime>
            <Symbol>TEST</Symbol>
            <Side>BUY</Side>
            <Quantity>1000</Quantity>
            <Price>100.00</Price>
            <TotalValue>100000</TotalValue>
            <CounterpartyAccount>ACC-002</CounterpartyAccount>
            <OrderID>ORD001</OrderID>
        </Trade>
        <Trade sequence="2">
            <AccountID>ACC-002</AccountID>
            <AccountName>Test Account 2</AccountName>
            <TradeDate>2024-03-15</TradeDate>
            <TradeTime>10:30:00.456</TradeTime>
            <Symbol>TEST</Symbol>
            <Side>SELL</Side>
            <Quantity>1000</Quantity>
            <Price>100.00</Price>
            <TotalValue>100000</TotalValue>
            <CounterpartyAccount>ACC-001</CounterpartyAccount>
            <OrderID>ORD002</OrderID>
        </Trade>
    </FlaggedTrades>
</Alert>""")
        # Create market_data but not wash trade specific files
        (tmp_path / "market_data.csv").write_text("col1,col2\na,b")

        simulator = BigDataSimulator(str(tmp_path))

        with pytest.raises(FileNotFoundError) as exc_info:
            simulator.create_request(str(alert_file))
        assert "account_relationships" in str(exc_info.value)
