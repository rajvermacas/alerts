"""Mock Big Data Layer Simulator.

This module simulates the production Big Data Layer for POC testing and
contract validation. It reads from test_data/ and constructs AnalysisRequest
objects exactly as the real Big Data Layer would.

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                   BigDataSimulator                       │
    │  Reads test_data/ files and assembles AnalysisRequest   │
    └─────────────────────────────┬───────────────────────────┘
                                  │
                                  │ create_request(alert_file)
                                  ▼
    ┌─────────────────────────────────────────────────────────┐
    │                    AnalysisRequest                       │
    │  - alert_xml: str                                        │
    │  - agent_type: "insider_trading" | "wash_trade"          │
    │  - tool_data: Dict[str, ToolInput]                       │
    └─────────────────────────────────────────────────────────┘
"""

import logging
import os
from pathlib import Path
from typing import Dict, Literal

from alerts.models.request import AnalysisRequest, ToolInput

logger = logging.getLogger(__name__)


class BigDataSimulator:
    """Simulates the production Big Data Layer for testing.

    This class reads from test_data/ files and constructs AnalysisRequest
    objects that match the contract expected by the orchestrator and agents.

    In production, the Big Data Layer would:
    1. Receive an alert from the surveillance system
    2. Query relevant data sources (databases, APIs)
    3. Determine the alert type (insider_trading vs wash_trade)
    4. Package all data into an AnalysisRequest
    5. Send to the orchestrator

    This simulator mimics that behavior using local test files.

    Attributes:
        data_dir: Path to the test_data directory
    """

    # Keywords for alert type detection (from existing orchestrator logic)
    INSIDER_TRADING_KEYWORDS = ["insider", "pre-announcement", "mnpi"]
    INSIDER_TRADING_RULE_CODES = ["SMARTS-IT-", "SMARTS-PAT-"]
    WASH_TRADE_KEYWORDS = ["wash", "self-trade", "circular"]
    WASH_TRADE_RULE_CODES = ["SMARTS-WT-", "WT-", "WASH_TRADE"]

    def __init__(self, data_dir: str) -> None:
        """Initialize the BigDataSimulator.

        Args:
            data_dir: Path to the test_data directory
        """
        self.data_dir = Path(data_dir)
        self.logger = logger
        self.logger.info(f"BigDataSimulator initialized with data_dir: {data_dir}")

    def create_request(self, alert_file: str) -> AnalysisRequest:
        """Create an AnalysisRequest from an alert file.

        This method reads the alert XML, determines the alert type,
        and loads all required tool data files.

        Args:
            alert_file: Path to the alert XML file

        Returns:
            AnalysisRequest with all required tool data

        Raises:
            FileNotFoundError: If alert file or required data files don't exist
        """
        self.logger.info(f"Creating request from alert file: {alert_file}")

        # Read alert XML content
        alert_xml = self._read_file(alert_file)

        # Determine alert type from XML content
        agent_type = self._determine_agent_type(alert_xml)
        self.logger.info(f"Determined agent type: {agent_type}")

        # Load tool data for this agent type
        tool_data = self._load_tool_data(agent_type, alert_xml)
        self.logger.info(f"Loaded {len(tool_data)} tool data items")

        return AnalysisRequest(
            alert_xml=alert_xml,
            agent_type=agent_type,
            tool_data=tool_data,
        )

    def create_request_from_content(
        self,
        xml_content: str,
    ) -> AnalysisRequest:
        """Create an AnalysisRequest from XML content (for frontend integration).

        This method is used when the frontend uploads an XML file directly,
        rather than passing a file path.

        Args:
            xml_content: Raw XML content of the alert

        Returns:
            AnalysisRequest with all required tool data
        """
        self.logger.info("Creating request from XML content")

        # Determine alert type from content
        agent_type = self._determine_agent_type(xml_content)
        self.logger.info(f"Determined agent type: {agent_type}")

        # Load tool data, using the provided XML for alert_reader
        tool_data = self._load_tool_data(agent_type, xml_content)
        self.logger.info(f"Loaded {len(tool_data)} tool data items")

        return AnalysisRequest(
            alert_xml=xml_content,
            agent_type=agent_type,
            tool_data=tool_data,
        )

    def _determine_agent_type(
        self,
        alert_xml: str,
    ) -> Literal["insider_trading", "wash_trade"]:
        """Determine the alert type from XML content.

        Uses keyword and rule code matching to classify the alert.

        Args:
            alert_xml: Raw XML content of the alert

        Returns:
            Agent type ("insider_trading" or "wash_trade")
        """
        xml_lower = alert_xml.lower()

        # Check for wash trade indicators first (more specific)
        for keyword in self.WASH_TRADE_KEYWORDS:
            if keyword in xml_lower:
                return "wash_trade"

        for rule_code in self.WASH_TRADE_RULE_CODES:
            if rule_code.lower() in xml_lower:
                return "wash_trade"

        # Check for insider trading indicators
        for keyword in self.INSIDER_TRADING_KEYWORDS:
            if keyword in xml_lower:
                return "insider_trading"

        for rule_code in self.INSIDER_TRADING_RULE_CODES:
            if rule_code.lower() in xml_lower:
                return "insider_trading"

        # Default to insider trading if no clear indicators
        self.logger.warning(
            "No clear alert type indicators found, defaulting to insider_trading"
        )
        return "insider_trading"

    def _load_tool_data(
        self,
        agent_type: Literal["insider_trading", "wash_trade"],
        alert_xml: str,
    ) -> Dict[str, ToolInput]:
        """Load tool data files for the specified agent type.

        Args:
            agent_type: Type of agent ("insider_trading" or "wash_trade")
            alert_xml: Alert XML content to include for alert_reader

        Returns:
            Dict mapping tool names to ToolInput objects
        """
        tool_data: Dict[str, ToolInput] = {}

        # Alert reader always gets the XML content
        tool_data["alert_reader"] = ToolInput(
            format="xml",
            data=alert_xml,
        )

        if agent_type == "insider_trading":
            tool_data.update(self._load_insider_trading_data())
        elif agent_type == "wash_trade":
            tool_data.update(self._load_wash_trade_data())

        return tool_data

    def _load_insider_trading_data(self) -> Dict[str, ToolInput]:
        """Load tool data for insider trading analysis.

        Returns:
            Dict mapping tool names to ToolInput objects
        """
        data: Dict[str, ToolInput] = {}

        # Market news (text format)
        news_path = self.data_dir / "market_news.txt"
        if news_path.exists():
            data["market_news"] = ToolInput(
                format="txt",
                data=self._read_file(str(news_path)),
            )
        else:
            self.logger.error(f"Required market news file not found: {news_path}")
            raise FileNotFoundError(f"Required market news file not found: {news_path}")

        # Market data (CSV format)
        market_data_path = self.data_dir / "market_data.csv"
        if market_data_path.exists():
            data["market_data"] = ToolInput(
                format="csv",
                data=self._read_file(str(market_data_path)),
            )
        else:
            self.logger.error(f"Required market data file not found: {market_data_path}")
            raise FileNotFoundError(f"Required market data file not found: {market_data_path}")

        # Trader profile (CSV format)
        profile_path = self.data_dir / "trader_profiles.csv"
        if profile_path.exists():
            data["trader_profile"] = ToolInput(
                format="csv",
                data=self._read_file(str(profile_path)),
            )
        else:
            self.logger.error(f"Required trader profiles file not found: {profile_path}")
            raise FileNotFoundError(f"Required trader profiles file not found: {profile_path}")

        # Trader history (CSV format)
        history_path = self.data_dir / "trader_history.csv"
        if history_path.exists():
            data["trader_history"] = ToolInput(
                format="csv",
                data=self._read_file(str(history_path)),
            )
        else:
            self.logger.error(f"Required trader history file not found: {history_path}")
            raise FileNotFoundError(f"Required trader history file not found: {history_path}")

        return data

    def _load_wash_trade_data(self) -> Dict[str, ToolInput]:
        """Load tool data for wash trade analysis.

        Note: trader_profile is NOT included for wash trade (per user decision).

        Returns:
            Dict mapping tool names to ToolInput objects
        """
        data: Dict[str, ToolInput] = {}

        # Market data (CSV format) - common tool
        market_data_path = self.data_dir / "market_data.csv"
        if market_data_path.exists():
            data["market_data"] = ToolInput(
                format="csv",
                data=self._read_file(str(market_data_path)),
            )
        else:
            self.logger.error(f"Required market data file not found: {market_data_path}")
            raise FileNotFoundError(f"Required market data file not found: {market_data_path}")

        # Wash trade specific tools - from wash_trade subdirectory
        wt_dir = self.data_dir / "wash_trade"

        # Account relationships
        relationships_path = wt_dir / "account_relationships.csv"
        if relationships_path.exists():
            data["account_relationships"] = ToolInput(
                format="csv",
                data=self._read_file(str(relationships_path)),
            )
        else:
            self.logger.error(f"Required account relationships file not found: {relationships_path}")
            raise FileNotFoundError(f"Required account relationships file not found: {relationships_path}")

        # Related accounts history
        history_path = wt_dir / "related_accounts_history.csv"
        if history_path.exists():
            data["related_accounts_history"] = ToolInput(
                format="csv",
                data=self._read_file(str(history_path)),
            )
        else:
            self.logger.error(f"Required related accounts history file not found: {history_path}")
            raise FileNotFoundError(f"Required related accounts history file not found: {history_path}")

        # Trade timing
        timing_path = wt_dir / "trade_timing.csv"
        if timing_path.exists():
            data["trade_timing"] = ToolInput(
                format="csv",
                data=self._read_file(str(timing_path)),
            )
        else:
            self.logger.error(f"Required trade timing file not found: {timing_path}")
            raise FileNotFoundError(f"Required trade timing file not found: {timing_path}")

        # Counterparty analysis
        counterparty_path = wt_dir / "counterparty_analysis.csv"
        if counterparty_path.exists():
            data["counterparty_analysis"] = ToolInput(
                format="csv",
                data=self._read_file(str(counterparty_path)),
            )
        else:
            self.logger.error(f"Required counterparty analysis file not found: {counterparty_path}")
            raise FileNotFoundError(f"Required counterparty analysis file not found: {counterparty_path}")

        return data

    def _read_file(self, file_path: str) -> str:
        """Read file content as string.

        Args:
            file_path: Path to the file

        Returns:
            File content as string

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            return f.read()
