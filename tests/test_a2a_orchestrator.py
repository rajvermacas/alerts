"""Tests for A2A Orchestrator Agent.

This module tests the orchestrator agent's ability to read alerts,
determine their type, and route them to specialized agents.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from alerts.a2a.orchestrator import OrchestratorAgent, AlertInfo, AlertCategory

# Configure pytest-asyncio to use auto mode
pytestmark = pytest.mark.asyncio(loop_scope="function")


class TestAlertParsing:
    """Test alert XML parsing functionality."""

    def test_read_alert_valid_xml(self, tmp_path):
        """Test parsing valid alert XML."""
        # Create test XML with insider trading type
        alert_xml = tmp_path / "test_alert.xml"
        alert_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>TEST-001</AlertID>
    <AlertType>Insider Trading</AlertType>
    <RuleViolated>SMARTS-IT-001</RuleViolated>
</SMARTSAlert>
""")

        orchestrator = OrchestratorAgent()
        result = orchestrator.read_alert(alert_xml)

        assert result.alert_id == "TEST-001"
        assert result.alert_type == "Insider Trading"
        assert result.rule_violated == "SMARTS-IT-001"
        assert result.category == AlertCategory.INSIDER_TRADING
        assert result.is_insider_trading is True
        assert result.file_path == str(alert_xml)

    def test_read_alert_valid_xml_with_defaults(self, tmp_path):
        """Test parsing XML with missing optional fields."""
        # Create minimal XML
        alert_xml = tmp_path / "minimal_alert.xml"
        alert_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>MINIMAL-001</AlertID>
</SMARTSAlert>
""")

        orchestrator = OrchestratorAgent()
        result = orchestrator.read_alert(alert_xml)

        assert result.alert_id == "MINIMAL-001"
        assert result.alert_type == ""
        assert result.rule_violated == ""
        assert result.category == AlertCategory.UNSUPPORTED
        assert result.is_insider_trading is False
        assert result.is_wash_trade is False

    def test_read_alert_missing_file(self):
        """Test handling of missing alert file."""
        orchestrator = OrchestratorAgent()
        nonexistent = Path("nonexistent.xml")

        with pytest.raises(FileNotFoundError, match="Alert file not found"):
            orchestrator.read_alert(nonexistent)

    def test_read_alert_malformed_xml(self, tmp_path):
        """Test handling of malformed XML."""
        bad_xml = tmp_path / "bad.xml"
        bad_xml.write_text("<Alert><NotClosed>")

        orchestrator = OrchestratorAgent()

        with pytest.raises(ValueError, match="Failed to parse alert XML"):
            orchestrator.read_alert(bad_xml)

    def test_read_alert_empty_file(self, tmp_path):
        """Test handling of empty XML file."""
        empty_xml = tmp_path / "empty.xml"
        empty_xml.write_text("")

        orchestrator = OrchestratorAgent()

        with pytest.raises(ValueError, match="Failed to parse alert XML"):
            orchestrator.read_alert(empty_xml)


class TestAlertTypeDetection:
    """Test alert type detection logic."""

    @pytest.mark.parametrize("alert_type,expected", [
        ("Pre-Announcement Trading", True),
        ("Insider Trading", True),
        ("Material Non-Public Information", True),
        ("MNPI Trading", True),
        ("Pre-Results Trading", True),
        ("Suspicious Trading Before Announcement", True),
        ("Market Manipulation", False),
        ("Wash Trading", False),
        ("Spoofing", False),
        ("", False),
    ])
    def test_is_insider_trading_by_type(self, alert_type, expected):
        """Test alert type detection by type name."""
        orchestrator = OrchestratorAgent()
        result = orchestrator._is_insider_trading_alert(alert_type, "")
        assert result == expected

    @pytest.mark.parametrize("rule,expected", [
        ("SMARTS-IT-001", True),
        ("SMARTS-IT-002", True),
        ("SMARTS-PAT-001", True),
        ("SMARTS-PAT-002", True),
        ("INSIDER_TRADING", True),
        ("PRE_ANNOUNCEMENT", True),
        ("SMARTS-MM-001", False),
        ("SMARTS-WW-001", False),
        ("OTHER-RULE", False),
        ("", False),
    ])
    def test_is_insider_trading_by_rule(self, rule, expected):
        """Test alert type detection by rule code."""
        orchestrator = OrchestratorAgent()
        result = orchestrator._is_insider_trading_alert("", rule)
        assert result == expected

    @pytest.mark.parametrize("alert_type,expected", [
        ("Potential insider activity detected", True),
        ("Pre-announcement suspicious pattern", True),
        ("Trading on MNPI suspected", True),
        ("Material information breach", True),
        ("Market manipulation pattern", False),
        ("Normal trading activity", False),
        ("Wash trade suspected", False),
    ])
    def test_is_insider_trading_by_keyword(self, alert_type, expected):
        """Test alert type detection by keywords in description."""
        orchestrator = OrchestratorAgent()
        result = orchestrator._is_insider_trading_alert(alert_type, "")
        assert result == expected

    def test_is_insider_trading_combined_logic(self):
        """Test that detection works with combination of type and rule."""
        orchestrator = OrchestratorAgent()

        # Should match on type even if rule doesn't match
        assert orchestrator._is_insider_trading_alert("Insider Trading", "SMARTS-MM-001") is True

        # Should match on rule even if type doesn't match
        assert orchestrator._is_insider_trading_alert("Market Manipulation", "SMARTS-IT-001") is True

        # Should not match if neither matches
        assert orchestrator._is_insider_trading_alert("Market Manipulation", "SMARTS-MM-001") is False


class TestAlertRouting:
    """Test alert routing functionality."""

    async def test_route_alert_insider_trading_success(self, tmp_path):
        """Test successful routing of insider trading alert."""
        # Create insider trading alert
        alert_xml = tmp_path / "insider_alert.xml"
        alert_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>IT-001</AlertID>
    <AlertType>Insider Trading</AlertType>
    <RuleViolated>SMARTS-IT-001</RuleViolated>
</SMARTSAlert>
""")

        orchestrator = OrchestratorAgent()

        # Mock the A2A communication
        with patch.object(orchestrator, '_send_to_insider_trading_agent', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {
                "status": "success",
                "response": {"determination": "ESCALATE"}
            }

            result = await orchestrator.route_alert(alert_xml)

            assert result["alert_id"] == "IT-001"
            assert result["alert_type"] == "Insider Trading"
            assert result["rule_violated"] == "SMARTS-IT-001"
            assert result["routed_to"] == "insider_trading_agent"
            assert result["agent_response"]["status"] == "success"
            mock_send.assert_called_once()

    async def test_route_alert_unsupported_type(self, tmp_path):
        """Test routing of unsupported alert type."""
        # Create non-insider trading alert
        alert_xml = tmp_path / "other_alert.xml"
        alert_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>MM-001</AlertID>
    <AlertType>Market Manipulation</AlertType>
    <RuleViolated>SMARTS-MM-001</RuleViolated>
</SMARTSAlert>
""")

        orchestrator = OrchestratorAgent()
        result = await orchestrator.route_alert(alert_xml)

        assert result["alert_id"] == "MM-001"
        assert result["alert_type"] == "Market Manipulation"
        assert result["routed_to"] is None
        assert "not currently supported" in result["message"]

    async def test_route_alert_agent_communication_error(self, tmp_path):
        """Test handling of agent communication error."""
        # Create insider trading alert
        alert_xml = tmp_path / "insider_alert.xml"
        alert_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>IT-002</AlertID>
    <AlertType>Insider Trading</AlertType>
    <RuleViolated>SMARTS-IT-001</RuleViolated>
</SMARTSAlert>
""")

        orchestrator = OrchestratorAgent()

        # Mock A2A communication failure
        with patch.object(orchestrator, '_send_to_insider_trading_agent', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {
                "status": "error",
                "error": "Connection refused"
            }

            result = await orchestrator.route_alert(alert_xml)

            assert result["routed_to"] == "insider_trading_agent"
            assert result["agent_response"]["status"] == "error"
            assert "Connection refused" in result["agent_response"]["error"]

    async def test_analyze_alert_string_path(self, tmp_path):
        """Test analyze_alert with string path input."""
        # Create alert
        alert_xml = tmp_path / "alert.xml"
        alert_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>TEST-STR</AlertID>
    <AlertType>Market Manipulation</AlertType>
</SMARTSAlert>
""")

        orchestrator = OrchestratorAgent()
        result = await orchestrator.analyze_alert(str(alert_xml))

        assert result["alert_id"] == "TEST-STR"
        assert result["routed_to"] is None

    async def test_analyze_alert_path_object(self, tmp_path):
        """Test analyze_alert with Path object input."""
        # Create alert
        alert_xml = tmp_path / "alert.xml"
        alert_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>TEST-PATH</AlertID>
    <AlertType>Market Manipulation</AlertType>
</SMARTSAlert>
""")

        orchestrator = OrchestratorAgent()
        result = await orchestrator.analyze_alert(alert_xml)

        assert result["alert_id"] == "TEST-PATH"
        assert result["routed_to"] is None


class TestA2ACommunication:
    """Test A2A protocol communication."""

    async def test_send_to_insider_trading_agent_success(self, tmp_path):
        """Test successful A2A communication."""
        alert_info = AlertInfo(
            alert_id="IT-TEST",
            alert_type="Insider Trading",
            rule_violated="SMARTS-IT-001",
            category=AlertCategory.INSIDER_TRADING,
            file_path=str(tmp_path / "test.xml")
        )

        orchestrator = OrchestratorAgent()

        # Mock httpx and A2A components
        with patch('alerts.a2a.orchestrator.httpx.AsyncClient') as mock_client_class, \
             patch('alerts.a2a.orchestrator.A2ACardResolver') as mock_resolver_class, \
             patch('alerts.a2a.orchestrator.A2AClient') as mock_a2a_client_class:

            # Setup mocks
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            mock_resolver = MagicMock()
            mock_agent_card = MagicMock()
            mock_agent_card.name = "Insider Trading Agent"
            mock_resolver.get_agent_card = AsyncMock(return_value=mock_agent_card)
            mock_resolver_class.return_value = mock_resolver

            mock_a2a_client = MagicMock()
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {"determination": "ESCALATE"}
            mock_a2a_client.send_message = AsyncMock(return_value=mock_response)
            mock_a2a_client_class.return_value = mock_a2a_client

            # Execute
            result = await orchestrator._send_to_insider_trading_agent(alert_info)

            # Assert
            assert result["status"] == "success"
            assert "response" in result
            mock_resolver.get_agent_card.assert_called_once()
            mock_a2a_client.send_message.assert_called_once()

    async def test_send_to_insider_trading_agent_connection_error(self, tmp_path):
        """Test A2A communication connection error."""
        alert_info = AlertInfo(
            alert_id="IT-TEST",
            alert_type="Insider Trading",
            rule_violated="SMARTS-IT-001",
            category=AlertCategory.INSIDER_TRADING,
            file_path=str(tmp_path / "test.xml")
        )

        orchestrator = OrchestratorAgent()

        # Mock connection failure
        with patch('alerts.a2a.orchestrator.httpx.AsyncClient') as mock_client_class, \
             patch('alerts.a2a.orchestrator.A2ACardResolver') as mock_resolver_class:

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            mock_resolver = MagicMock()
            mock_resolver.get_agent_card = AsyncMock(side_effect=Exception("Connection refused"))
            mock_resolver_class.return_value = mock_resolver

            # Execute
            result = await orchestrator._send_to_insider_trading_agent(alert_info)

            # Assert
            assert result["status"] == "error"
            assert "Failed to connect" in result["error"]

    async def test_send_to_insider_trading_agent_message_error(self, tmp_path):
        """Test A2A communication message sending error."""
        alert_info = AlertInfo(
            alert_id="IT-TEST",
            alert_type="Insider Trading",
            rule_violated="SMARTS-IT-001",
            category=AlertCategory.INSIDER_TRADING,
            file_path=str(tmp_path / "test.xml")
        )

        orchestrator = OrchestratorAgent()

        # Mock message sending failure
        with patch('alerts.a2a.orchestrator.httpx.AsyncClient') as mock_client_class, \
             patch('alerts.a2a.orchestrator.A2ACardResolver') as mock_resolver_class, \
             patch('alerts.a2a.orchestrator.A2AClient') as mock_a2a_client_class:

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            mock_resolver = MagicMock()
            mock_agent_card = MagicMock()
            mock_agent_card.name = "Insider Trading Agent"
            mock_resolver.get_agent_card = AsyncMock(return_value=mock_agent_card)
            mock_resolver_class.return_value = mock_resolver

            mock_a2a_client = MagicMock()
            mock_a2a_client.send_message = AsyncMock(side_effect=Exception("Timeout"))
            mock_a2a_client_class.return_value = mock_a2a_client

            # Execute
            result = await orchestrator._send_to_insider_trading_agent(alert_info)

            # Assert
            assert result["status"] == "error"
            assert "Failed to communicate" in result["error"]


class TestOrchestratorConfiguration:
    """Test orchestrator configuration and initialization."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        orchestrator = OrchestratorAgent()

        assert orchestrator.insider_trading_agent_url == "http://localhost:10001"
        assert orchestrator.data_dir == Path("test_data")

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        custom_url = "http://remote-host:9999"
        custom_data_dir = Path("/custom/data")

        orchestrator = OrchestratorAgent(
            insider_trading_agent_url=custom_url,
            data_dir=custom_data_dir
        )

        assert orchestrator.insider_trading_agent_url == custom_url
        assert orchestrator.data_dir == custom_data_dir

    def test_get_text_helper_with_value(self, tmp_path):
        """Test _get_text helper method with valid element."""
        import xml.etree.ElementTree as ET

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Root>
    <Field>Test Value</Field>
</Root>
"""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(xml_content)

        tree = ET.parse(xml_file)
        root = tree.getroot()

        orchestrator = OrchestratorAgent()
        result = orchestrator._get_text(root, ".//Field", "default")

        assert result == "Test Value"

    def test_get_text_helper_with_missing_element(self, tmp_path):
        """Test _get_text helper method with missing element."""
        import xml.etree.ElementTree as ET

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Root>
    <OtherField>Value</OtherField>
</Root>
"""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(xml_content)

        tree = ET.parse(xml_file)
        root = tree.getroot()

        orchestrator = OrchestratorAgent()
        result = orchestrator._get_text(root, ".//MissingField", "default_value")

        assert result == "default_value"

    def test_get_text_helper_with_empty_element(self, tmp_path):
        """Test _get_text helper method with empty element."""
        import xml.etree.ElementTree as ET

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Root>
    <Field></Field>
</Root>
"""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(xml_content)

        tree = ET.parse(xml_file)
        root = tree.getroot()

        orchestrator = OrchestratorAgent()
        result = orchestrator._get_text(root, ".//Field", "default_value")

        assert result == "default_value"


class TestWashTradeDetection:
    """Test wash trade alert type detection logic."""

    @pytest.mark.parametrize("alert_type,expected", [
        ("WashTrade", True),
        ("Wash Trade", True),
        ("Self-Trade", True),
        ("Matched Orders", True),
        ("Circular Trading", True),
        ("Layered Wash Trade", True),
        ("Insider Trading", False),
        ("Market Manipulation", False),
        ("Spoofing", False),
        ("", False),
    ])
    def test_is_wash_trade_by_type(self, alert_type, expected):
        """Test wash trade detection by type name."""
        orchestrator = OrchestratorAgent()
        result = orchestrator._is_wash_trade_alert(alert_type, "")
        assert result == expected

    @pytest.mark.parametrize("rule,expected", [
        ("WT-001", True),
        ("WT-002", True),
        ("WASH_TRADE", True),
        ("SELF_TRADE", True),
        ("MATCHED_ORDERS", True),
        ("SMARTS-WT-001", True),
        ("SMARTS-WT-002", True),
        ("SMARTS-IT-001", False),
        ("SMARTS-MM-001", False),
        ("OTHER-RULE", False),
        ("", False),
    ])
    def test_is_wash_trade_by_rule(self, rule, expected):
        """Test wash trade detection by rule code."""
        orchestrator = OrchestratorAgent()
        result = orchestrator._is_wash_trade_alert("", rule)
        assert result == expected

    @pytest.mark.parametrize("alert_type,expected", [
        ("Potential wash trading detected", True),
        ("Self-trade pattern observed", True),
        ("Matched order violation", True),
        ("Circular trade flow identified", True),
        ("Market manipulation pattern", False),
        ("Normal trading activity", False),
        ("Insider trading suspected", False),
    ])
    def test_is_wash_trade_by_keyword(self, alert_type, expected):
        """Test wash trade detection by keywords in description."""
        orchestrator = OrchestratorAgent()
        result = orchestrator._is_wash_trade_alert(alert_type, "")
        assert result == expected


class TestWashTradeRouting:
    """Test wash trade alert routing functionality."""

    async def test_route_alert_wash_trade_success(self, tmp_path):
        """Test successful routing of wash trade alert."""
        # Create wash trade alert
        alert_xml = tmp_path / "wash_trade_alert.xml"
        alert_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>WT-001</AlertID>
    <AlertType>WashTrade</AlertType>
    <RuleViolated>SMARTS-WT-001</RuleViolated>
</SMARTSAlert>
""")

        orchestrator = OrchestratorAgent()

        # Mock the A2A communication
        with patch.object(orchestrator, '_send_to_wash_trade_agent', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {
                "status": "success",
                "response": {"determination": "ESCALATE"}
            }

            result = await orchestrator.route_alert(alert_xml)

            assert result["alert_id"] == "WT-001"
            assert result["alert_type"] == "WashTrade"
            assert result["rule_violated"] == "SMARTS-WT-001"
            assert result["routed_to"] == "wash_trade_agent"
            assert result["category"] == "wash_trade"
            assert result["agent_response"]["status"] == "success"
            mock_send.assert_called_once()

    async def test_route_alert_wash_trade_agent_error(self, tmp_path):
        """Test handling of wash trade agent communication error."""
        # Create wash trade alert
        alert_xml = tmp_path / "wash_trade_alert.xml"
        alert_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>WT-002</AlertID>
    <AlertType>Wash Trade</AlertType>
    <RuleViolated>WT-001</RuleViolated>
</SMARTSAlert>
""")

        orchestrator = OrchestratorAgent()

        # Mock A2A communication failure
        with patch.object(orchestrator, '_send_to_wash_trade_agent', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {
                "status": "error",
                "error": "Connection refused"
            }

            result = await orchestrator.route_alert(alert_xml)

            assert result["routed_to"] == "wash_trade_agent"
            assert result["category"] == "wash_trade"
            assert result["agent_response"]["status"] == "error"
            assert "Connection refused" in result["agent_response"]["error"]

    def test_read_wash_trade_alert(self, tmp_path):
        """Test parsing wash trade alert XML."""
        alert_xml = tmp_path / "wash_alert.xml"
        alert_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
    <AlertID>WT-TEST</AlertID>
    <AlertType>Self-Trade</AlertType>
    <RuleViolated>SELF_TRADE</RuleViolated>
</SMARTSAlert>
""")

        orchestrator = OrchestratorAgent()
        result = orchestrator.read_alert(alert_xml)

        assert result.alert_id == "WT-TEST"
        assert result.alert_type == "Self-Trade"
        assert result.category == AlertCategory.WASH_TRADE
        assert result.is_wash_trade is True
        assert result.is_insider_trading is False


class TestWashTradeA2ACommunication:
    """Test A2A protocol communication for wash trade agent."""

    async def test_send_to_wash_trade_agent_success(self, tmp_path):
        """Test successful A2A communication to wash trade agent."""
        alert_info = AlertInfo(
            alert_id="WT-TEST",
            alert_type="WashTrade",
            rule_violated="SMARTS-WT-001",
            category=AlertCategory.WASH_TRADE,
            file_path=str(tmp_path / "test.xml")
        )

        orchestrator = OrchestratorAgent()

        # Mock httpx and A2A components
        with patch('alerts.a2a.orchestrator.httpx.AsyncClient') as mock_client_class, \
             patch('alerts.a2a.orchestrator.A2ACardResolver') as mock_resolver_class, \
             patch('alerts.a2a.orchestrator.A2AClient') as mock_a2a_client_class:

            # Setup mocks
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            mock_resolver = MagicMock()
            mock_agent_card = MagicMock()
            mock_agent_card.name = "Wash Trade Agent"
            mock_resolver.get_agent_card = AsyncMock(return_value=mock_agent_card)
            mock_resolver_class.return_value = mock_resolver

            mock_a2a_client = MagicMock()
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {"determination": "ESCALATE"}
            mock_a2a_client.send_message = AsyncMock(return_value=mock_response)
            mock_a2a_client_class.return_value = mock_a2a_client

            # Execute
            result = await orchestrator._send_to_wash_trade_agent(alert_info)

            # Assert
            assert result["status"] == "success"
            assert "response" in result
            mock_resolver.get_agent_card.assert_called_once()
            mock_a2a_client.send_message.assert_called_once()

    async def test_send_to_wash_trade_agent_connection_error(self, tmp_path):
        """Test A2A communication connection error to wash trade agent."""
        alert_info = AlertInfo(
            alert_id="WT-TEST",
            alert_type="WashTrade",
            rule_violated="SMARTS-WT-001",
            category=AlertCategory.WASH_TRADE,
            file_path=str(tmp_path / "test.xml")
        )

        orchestrator = OrchestratorAgent()

        # Mock connection failure
        with patch('alerts.a2a.orchestrator.httpx.AsyncClient') as mock_client_class, \
             patch('alerts.a2a.orchestrator.A2ACardResolver') as mock_resolver_class:

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            mock_resolver = MagicMock()
            mock_resolver.get_agent_card = AsyncMock(side_effect=Exception("Connection refused"))
            mock_resolver_class.return_value = mock_resolver

            # Execute
            result = await orchestrator._send_to_wash_trade_agent(alert_info)

            # Assert
            assert result["status"] == "error"
            assert "Failed to connect" in result["error"]


class TestAlertCategorization:
    """Test the alert categorization logic."""

    def test_categorize_wash_trade_over_insider(self):
        """Test that wash trade is detected before insider trading when both match."""
        orchestrator = OrchestratorAgent()

        # This type could match both (if we had "wash insider" as a keyword)
        # But wash trade should be checked first
        result = orchestrator._categorize_alert("WashTrade", "")
        assert result == AlertCategory.WASH_TRADE

    def test_categorize_insider_trading(self):
        """Test insider trading categorization."""
        orchestrator = OrchestratorAgent()

        result = orchestrator._categorize_alert("Insider Trading", "SMARTS-IT-001")
        assert result == AlertCategory.INSIDER_TRADING

    def test_categorize_unsupported(self):
        """Test unsupported alert categorization."""
        orchestrator = OrchestratorAgent()

        result = orchestrator._categorize_alert("Market Manipulation", "SMARTS-MM-001")
        assert result == AlertCategory.UNSUPPORTED

    def test_alert_info_properties(self):
        """Test AlertInfo computed properties."""
        # Insider trading alert
        insider_info = AlertInfo(
            alert_id="IT-001",
            alert_type="Insider Trading",
            rule_violated="SMARTS-IT-001",
            category=AlertCategory.INSIDER_TRADING,
            file_path="/path/to/alert.xml"
        )
        assert insider_info.is_insider_trading is True
        assert insider_info.is_wash_trade is False

        # Wash trade alert
        wash_info = AlertInfo(
            alert_id="WT-001",
            alert_type="WashTrade",
            rule_violated="SMARTS-WT-001",
            category=AlertCategory.WASH_TRADE,
            file_path="/path/to/alert.xml"
        )
        assert wash_info.is_insider_trading is False
        assert wash_info.is_wash_trade is True

        # Unsupported alert
        unsupported_info = AlertInfo(
            alert_id="MM-001",
            alert_type="Market Manipulation",
            rule_violated="SMARTS-MM-001",
            category=AlertCategory.UNSUPPORTED,
            file_path="/path/to/alert.xml"
        )
        assert unsupported_info.is_insider_trading is False
        assert unsupported_info.is_wash_trade is False
