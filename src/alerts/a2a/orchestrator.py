"""Orchestrator Agent for routing alerts to specialized agents.

This module implements an orchestrator that reads alerts and routes them
to specialized agents (Insider Trading or Wash Trade) using the A2A protocol.
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

logger = logging.getLogger(__name__)


class AlertCategory(Enum):
    """Categories of alerts for routing."""
    INSIDER_TRADING = "insider_trading"
    WASH_TRADE = "wash_trade"
    UNSUPPORTED = "unsupported"


@dataclass
class AlertInfo:
    """Information extracted from an alert XML file."""

    alert_id: str
    alert_type: str
    rule_violated: str
    category: AlertCategory
    file_path: str

    @property
    def is_insider_trading(self) -> bool:
        """Check if this is an insider trading alert."""
        return self.category == AlertCategory.INSIDER_TRADING

    @property
    def is_wash_trade(self) -> bool:
        """Check if this is a wash trade alert."""
        return self.category == AlertCategory.WASH_TRADE


class OrchestratorAgent:
    """Orchestrator agent that routes alerts to specialized agents.

    This agent reads an alert file, determines its type, and routes it
    to the appropriate specialized agent via A2A protocol.

    Attributes:
        insider_trading_agent_url: URL of the insider trading agent A2A server
        wash_trade_agent_url: URL of the wash trade agent A2A server
        data_dir: Path to data directory
    """

    # Alert types that should be routed to the insider trading agent
    INSIDER_TRADING_ALERT_TYPES = {
        "Pre-Announcement Trading",
        "Insider Trading",
        "Material Non-Public Information",
        "MNPI Trading",
        "Pre-Results Trading",
        "Suspicious Trading Before Announcement",
    }

    # Rule codes associated with insider trading
    INSIDER_TRADING_RULES = {
        "SMARTS-IT-001",
        "SMARTS-IT-002",
        "SMARTS-PAT-001",
        "SMARTS-PAT-002",
        "INSIDER_TRADING",
        "PRE_ANNOUNCEMENT",
    }

    # Alert types that should be routed to the wash trade agent
    WASH_TRADE_ALERT_TYPES = {
        "WashTrade",
        "Wash Trade",
        "Self-Trade",
        "Matched Orders",
        "Circular Trading",
        "Layered Wash Trade",
    }

    # Rule codes associated with wash trading
    WASH_TRADE_RULES = {
        "WT-001",
        "WT-002",
        "WASH_TRADE",
        "SELF_TRADE",
        "MATCHED_ORDERS",
        "SMARTS-WT-001",
        "SMARTS-WT-002",
    }

    def __init__(
        self,
        insider_trading_agent_url: str = "http://localhost:10001",
        wash_trade_agent_url: str = "http://localhost:10002",
        data_dir: Path | None = None,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            insider_trading_agent_url: URL of the insider trading agent A2A server
            wash_trade_agent_url: URL of the wash trade agent A2A server
            data_dir: Path to data directory (optional)
        """
        self.insider_trading_agent_url = insider_trading_agent_url
        self.wash_trade_agent_url = wash_trade_agent_url
        self.data_dir = data_dir or Path("test_data")
        logger.info("OrchestratorAgent initialized")
        logger.info(f"Insider trading agent URL: {insider_trading_agent_url}")
        logger.info(f"Wash trade agent URL: {wash_trade_agent_url}")

    def read_alert(self, alert_path: Path) -> AlertInfo:
        """Read and parse an alert XML file to determine its type.

        Args:
            alert_path: Path to the alert XML file

        Returns:
            AlertInfo with extracted alert information

        Raises:
            FileNotFoundError: If alert file doesn't exist
            ValueError: If alert file cannot be parsed
        """
        if not alert_path.exists():
            raise FileNotFoundError(f"Alert file not found: {alert_path}")

        logger.info(f"Reading alert file: {alert_path}")

        try:
            tree = ET.parse(alert_path)
            root = tree.getroot()

            # Extract alert information
            alert_id = self._get_text(root, ".//AlertID", "UNKNOWN")
            alert_type = self._get_text(root, ".//AlertType", "")
            rule_violated = self._get_text(root, ".//RuleViolated", "")

            # Determine alert category
            category = self._categorize_alert(alert_type, rule_violated)

            alert_info = AlertInfo(
                alert_id=alert_id,
                alert_type=alert_type,
                rule_violated=rule_violated,
                category=category,
                file_path=str(alert_path),
            )

            logger.info(
                f"Alert parsed: ID={alert_id}, Type={alert_type}, "
                f"Rule={rule_violated}, Category={category.value}"
            )

            return alert_info

        except ET.ParseError as e:
            raise ValueError(f"Failed to parse alert XML: {e}") from e

    def _get_text(self, root: ET.Element, xpath: str, default: str) -> str:
        """Get text from an XML element safely.

        Args:
            root: Root element to search from
            xpath: XPath expression
            default: Default value if element not found

        Returns:
            Text content or default value
        """
        element = root.find(xpath)
        if element is not None and element.text:
            return element.text.strip()
        return default

    def _categorize_alert(self, alert_type: str, rule_violated: str) -> AlertCategory:
        """Categorize an alert for routing to the appropriate agent.

        Args:
            alert_type: The type of alert
            rule_violated: The rule code that was violated

        Returns:
            AlertCategory indicating which agent should handle this alert
        """
        # Check wash trade first (more specific)
        if self._is_wash_trade_alert(alert_type, rule_violated):
            return AlertCategory.WASH_TRADE

        # Check insider trading
        if self._is_insider_trading_alert(alert_type, rule_violated):
            return AlertCategory.INSIDER_TRADING

        return AlertCategory.UNSUPPORTED

    def _is_insider_trading_alert(self, alert_type: str, rule_violated: str) -> bool:
        """Determine if an alert is related to insider trading.

        Args:
            alert_type: The type of alert
            rule_violated: The rule code that was violated

        Returns:
            True if this is an insider trading alert
        """
        # Check alert type
        if alert_type in self.INSIDER_TRADING_ALERT_TYPES:
            return True

        # Check rule violated
        if rule_violated in self.INSIDER_TRADING_RULES:
            return True

        # Check for keywords in alert type
        alert_type_lower = alert_type.lower()
        insider_keywords = ["insider", "pre-announcement", "mnpi", "material"]
        if any(keyword in alert_type_lower for keyword in insider_keywords):
            return True

        return False

    def _is_wash_trade_alert(self, alert_type: str, rule_violated: str) -> bool:
        """Determine if an alert is related to wash trading.

        Args:
            alert_type: The type of alert
            rule_violated: The rule code that was violated

        Returns:
            True if this is a wash trade alert
        """
        # Check alert type
        if alert_type in self.WASH_TRADE_ALERT_TYPES:
            return True

        # Check rule violated
        if rule_violated in self.WASH_TRADE_RULES:
            return True

        # Check for keywords in alert type
        alert_type_lower = alert_type.lower()
        wash_keywords = ["wash", "self-trade", "matched order", "circular"]
        if any(keyword in alert_type_lower for keyword in wash_keywords):
            return True

        return False

    async def route_alert(self, alert_path: Path) -> dict[str, Any]:
        """Route an alert to the appropriate specialized agent.

        Args:
            alert_path: Path to the alert XML file

        Returns:
            Dictionary with routing result and agent response

        Raises:
            FileNotFoundError: If alert file doesn't exist
            ValueError: If alert type is not supported
        """
        # Read and parse the alert
        alert_info = self.read_alert(alert_path)

        result = {
            "alert_id": alert_info.alert_id,
            "alert_type": alert_info.alert_type,
            "rule_violated": alert_info.rule_violated,
            "file_path": alert_info.file_path,
        }

        if alert_info.is_insider_trading:
            logger.info(
                f"Routing alert {alert_info.alert_id} to Insider Trading Agent"
            )
            result["routed_to"] = "insider_trading_agent"
            result["category"] = AlertCategory.INSIDER_TRADING.value

            # Send to insider trading agent via A2A
            response = await self._send_to_insider_trading_agent(alert_info)
            result["agent_response"] = response

        elif alert_info.is_wash_trade:
            logger.info(
                f"Routing alert {alert_info.alert_id} to Wash Trade Agent"
            )
            result["routed_to"] = "wash_trade_agent"
            result["category"] = AlertCategory.WASH_TRADE.value

            # Send to wash trade agent via A2A
            response = await self._send_to_wash_trade_agent(alert_info)
            result["agent_response"] = response

        else:
            logger.warning(
                f"Alert {alert_info.alert_id} has unsupported type. "
                f"Type: {alert_info.alert_type}, Rule: {alert_info.rule_violated}"
            )
            result["routed_to"] = None
            result["category"] = AlertCategory.UNSUPPORTED.value
            result["message"] = (
                f"Alert type '{alert_info.alert_type}' is not currently supported. "
                "Supported alert types: Insider Trading, Wash Trade."
            )

        return result

    async def _send_to_insider_trading_agent(
        self, alert_info: AlertInfo
    ) -> dict[str, Any]:
        """Send an alert to the insider trading agent via A2A.

        Args:
            alert_info: Information about the alert to analyze

        Returns:
            Response from the insider trading agent
        """
        logger.info(f"Sending alert to insider trading agent: {alert_info.file_path}")

        async with httpx.AsyncClient(timeout=300.0) as httpx_client:
            # Get agent card
            resolver = A2ACardResolver(
                httpx_client=httpx_client,
                base_url=self.insider_trading_agent_url,
            )

            try:
                agent_card = await resolver.get_agent_card()
                logger.info(f"Connected to agent: {agent_card.name}")
            except Exception as e:
                logger.error(f"Failed to connect to insider trading agent: {e}")
                return {
                    "status": "error",
                    "error": f"Failed to connect to insider trading agent: {str(e)}",
                }

            # Create client
            client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)

            # Create message
            message_payload = {
                "message": {
                    "role": "user",
                    "parts": [
                        {
                            "kind": "text",
                            "text": f"Analyze the insider trading alert at: {alert_info.file_path}",
                        }
                    ],
                    "messageId": uuid4().hex,
                },
            }

            request = SendMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(**message_payload),
            )

            try:
                # Send message and get response
                response = await client.send_message(request)
                response_data = response.model_dump(mode="json", exclude_none=True)
                logger.info("Received response from insider trading agent")
                return {
                    "status": "success",
                    "response": response_data,
                }
            except Exception as e:
                logger.error(f"Failed to send message to insider trading agent: {e}")
                return {
                    "status": "error",
                    "error": f"Failed to communicate with insider trading agent: {str(e)}",
                }

    async def _send_to_wash_trade_agent(
        self, alert_info: AlertInfo
    ) -> dict[str, Any]:
        """Send an alert to the wash trade agent via A2A.

        Args:
            alert_info: Information about the alert to analyze

        Returns:
            Response from the wash trade agent
        """
        logger.info(f"Sending alert to wash trade agent: {alert_info.file_path}")

        async with httpx.AsyncClient(timeout=300.0) as httpx_client:
            # Get agent card
            resolver = A2ACardResolver(
                httpx_client=httpx_client,
                base_url=self.wash_trade_agent_url,
            )

            try:
                agent_card = await resolver.get_agent_card()
                logger.info(f"Connected to agent: {agent_card.name}")
            except Exception as e:
                logger.error(f"Failed to connect to wash trade agent: {e}")
                return {
                    "status": "error",
                    "error": f"Failed to connect to wash trade agent: {str(e)}",
                }

            # Create client
            client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)

            # Create message
            message_payload = {
                "message": {
                    "role": "user",
                    "parts": [
                        {
                            "kind": "text",
                            "text": f"Analyze the wash trade alert at: {alert_info.file_path}",
                        }
                    ],
                    "messageId": uuid4().hex,
                },
            }

            request = SendMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(**message_payload),
            )

            try:
                # Send message and get response
                response = await client.send_message(request)
                response_data = response.model_dump(mode="json", exclude_none=True)
                logger.info("Received response from wash trade agent")
                return {
                    "status": "success",
                    "response": response_data,
                }
            except Exception as e:
                logger.error(f"Failed to send message to wash trade agent: {e}")
                return {
                    "status": "error",
                    "error": f"Failed to communicate with wash trade agent: {str(e)}",
                }

    async def analyze_alert(self, alert_path: str | Path) -> dict[str, Any]:
        """Main entry point to analyze an alert.

        This method reads the alert, determines its type, and routes it
        to the appropriate specialized agent.

        Args:
            alert_path: Path to the alert XML file (string or Path)

        Returns:
            Dictionary containing the analysis result
        """
        if isinstance(alert_path, str):
            alert_path = Path(alert_path)

        logger.info("=" * 60)
        logger.info(f"Orchestrator: Analyzing alert {alert_path}")
        logger.info("=" * 60)

        return await self.route_alert(alert_path)
