"""Mock Big Data Layer Simulator.

This module simulates the production Big Data Layer for POC testing and
contract validation. It reads from test_data/ and constructs AnalysisRequest
objects exactly as the real Big Data Layer would.

Architecture Change (AlertReaderTool Removal):
    - alert_xml replaced with alert_context (structured AlertContext)
    - XML parsing now happens here (Big Data Layer), not in agent
    - Enables all tools to run in parallel from start
    - See: .dev-resources/architecture/remove-alert-reader-tool.md

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                   BigDataSimulator                       │
    │  1. Read alert XML file                                  │
    │  2. Parse XML → AlertContext (structured)                │
    │  3. Load tool data files                                 │
    │  4. Assemble AnalysisRequest                             │
    └─────────────────────────────┬───────────────────────────┘
                                  │
                                  │ create_request(alert_file)
                                  ▼
    ┌─────────────────────────────────────────────────────────┐
    │                    AnalysisRequest                       │
    │  - alert_context: AlertContext (InsiderTrading | WT)     │
    │  - agent_type: "insider_trading" | "wash_trade"          │
    │  - tool_data: Dict[str, ToolInput] (NO alert_reader)     │
    └─────────────────────────────────────────────────────────┘
"""

import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, Literal, Union, cast

from alerts.models.alert_context import (
    InsiderTradingAlertContext,
    RelatedEvent,
    Trade,
    Trader,
    WashTradeAlertContext,
    WashTradeFlaggedTrade,
)
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

        This method reads the alert XML, parses it into structured AlertContext,
        determines the alert type, and loads all required tool data files.

        Architecture Change:
            - XML is now parsed into AlertContext here (not in agent)
            - alert_reader tool removed from tool_data
            - Enables all tools to run in parallel

        Args:
            alert_file: Path to the alert XML file

        Returns:
            AnalysisRequest with alert_context and tool data

        Raises:
            FileNotFoundError: If alert file or required data files don't exist
            ValueError: If XML parsing fails or required fields are missing
        """
        self.logger.info(f"Creating request from alert file: {alert_file}")

        # Read alert XML content
        xml_content = self._read_file(alert_file)

        # Parse XML into structured AlertContext
        alert_context = self._parse_xml_to_context(xml_content)
        agent_type = alert_context.context_type
        self.logger.info(
            f"Parsed alert context: alert_id={alert_context.alert_id}, "
            f"agent_type={agent_type}"
        )

        # Load tool data for this agent type (NO alert_reader)
        tool_data = self._load_tool_data(agent_type)
        self.logger.info(f"Loaded {len(tool_data)} tool data items")

        return AnalysisRequest(
            alert_context=alert_context,
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

        Architecture Change:
            - XML is now parsed into AlertContext here (not in agent)
            - alert_reader tool removed from tool_data
            - Enables all tools to run in parallel

        Args:
            xml_content: Raw XML content of the alert

        Returns:
            AnalysisRequest with alert_context and tool data

        Raises:
            ValueError: If XML parsing fails or required fields are missing
        """
        self.logger.info("Creating request from XML content")

        # Parse XML into structured AlertContext
        alert_context = self._parse_xml_to_context(xml_content)
        agent_type = alert_context.context_type
        self.logger.info(
            f"Parsed alert context: alert_id={alert_context.alert_id}, "
            f"agent_type={agent_type}"
        )

        # Load tool data for this agent type (NO alert_reader)
        tool_data = self._load_tool_data(agent_type)
        self.logger.info(f"Loaded {len(tool_data)} tool data items")

        return AnalysisRequest(
            alert_context=alert_context,
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
    ) -> Dict[str, ToolInput]:
        """Load tool data files for the specified agent type.

        Architecture Change:
            - alert_reader REMOVED from tool data
            - Alert context is now passed via alert_context field
            - Enables all tools to run in parallel

        Args:
            agent_type: Type of agent ("insider_trading" or "wash_trade")

        Returns:
            Dict mapping tool names to ToolInput objects
        """
        tool_data: Dict[str, ToolInput] = {}

        # NOTE: alert_reader removed - context is now in alert_context field
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

    # =========================================================================
    # XML Parsing Methods (AlertReaderTool replacement)
    # =========================================================================

    def _parse_xml_to_context(
        self,
        xml_content: str,
    ) -> Union[InsiderTradingAlertContext, WashTradeAlertContext]:
        """Parse XML content into structured AlertContext.

        This is pure XML→JSON transformation. NO analysis. NO computed fields.
        Replaces AlertReaderTool's LLM-based parsing with deterministic extraction.

        Architecture Reference:
            .dev-resources/architecture/remove-alert-reader-tool.md
            Section: AlertContext Schema

        Args:
            xml_content: Raw XML content of the alert

        Returns:
            Typed AlertContext (InsiderTradingAlertContext or WashTradeAlertContext)

        Raises:
            ValueError: If XML cannot be parsed or required fields are missing
        """
        self.logger.info("Parsing XML to AlertContext")

        # Determine alert type first to pick the right parser
        agent_type = self._determine_agent_type(xml_content)
        self.logger.debug(f"Determined agent type for parsing: {agent_type}")

        if agent_type == "insider_trading":
            return self._parse_insider_trading_xml(xml_content)
        else:
            return self._parse_wash_trade_xml(xml_content)

    def _parse_insider_trading_xml(
        self,
        xml_content: str,
    ) -> InsiderTradingAlertContext:
        """Parse IT alert XML into InsiderTradingAlertContext.

        Expected XML structure:
            <SMARTSAlert>
                <AlertID>...</AlertID>
                <AlertType>...</AlertType>
                <RuleViolated>...</RuleViolated>
                <GeneratedTimestamp>...</GeneratedTimestamp>
                <Trader>...</Trader>
                <SuspiciousActivity>...</SuspiciousActivity>
                <RelatedEvent>...</RelatedEvent>  (optional)
            </SMARTSAlert>

        EXCLUDES: <AnomalyIndicators> (SMARTS pre-analysis, not raw data)

        Args:
            xml_content: Raw XML content

        Returns:
            InsiderTradingAlertContext with all parsed fields

        Raises:
            ValueError: If required fields are missing
        """
        self.logger.info("Parsing Insider Trading alert XML")

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            self.logger.error(f"Failed to parse XML: {e}")
            raise ValueError(f"Invalid XML content: {e}") from e

        # Extract root-level fields
        alert_id = self._get_text_required(root, "AlertID")
        alert_type = self._get_text_required(root, "AlertType")
        rule_violated = self._get_text_required(root, "RuleViolated")
        generated_timestamp_str = self._get_text_required(root, "GeneratedTimestamp")

        # Parse timestamp (handle Z suffix)
        try:
            generated_timestamp = datetime.fromisoformat(
                generated_timestamp_str.replace("Z", "+00:00")
            )
        except ValueError as e:
            self.logger.error(f"Invalid timestamp format: {generated_timestamp_str}")
            raise ValueError(f"Invalid timestamp format: {generated_timestamp_str}") from e

        # Extract Trader
        trader_elem = root.find(".//Trader")
        if trader_elem is None:
            self.logger.error("Missing <Trader> element in IT alert XML")
            raise ValueError("Missing <Trader> element in IT alert XML")

        trader = Trader(
            trader_id=self._get_text_required(trader_elem, "TraderID"),
            name=self._get_text_required(trader_elem, "Name"),
            department=self._get_text_required(trader_elem, "Department"),
        )
        self.logger.debug(f"Parsed trader: {trader.trader_id}")

        # Extract SuspiciousActivity
        activity_elem = root.find(".//SuspiciousActivity")
        if activity_elem is None:
            self.logger.error("Missing <SuspiciousActivity> element in IT alert XML")
            raise ValueError("Missing <SuspiciousActivity> element in IT alert XML")

        # Parse trade date
        trade_date_str = self._get_text_required(activity_elem, "TradeDate")
        trade_date_parsed = date.fromisoformat(trade_date_str)

        # Parse side as literal type
        side_str = self._get_text_required(activity_elem, "Side")
        if side_str not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side value: {side_str}, expected BUY or SELL")
        side: Literal["BUY", "SELL"] = cast(Literal["BUY", "SELL"], side_str)

        trade = Trade(
            symbol=self._get_text_required(activity_elem, "Symbol"),
            trade_date=trade_date_parsed,
            side=side,
            quantity=int(self._get_text_required(activity_elem, "Quantity")),
            price=Decimal(self._get_text_required(activity_elem, "Price")),
            total_value=Decimal(self._get_text_required(activity_elem, "TotalValue")),
        )
        self.logger.debug(f"Parsed trade: {trade.symbol} {trade.side} {trade.quantity}")

        # Extract RelatedEvent (optional)
        related_event = None
        event_elem = root.find(".//RelatedEvent")
        if event_elem is not None:
            event_date_str = self._get_text_required(event_elem, "EventDate")
            event_date_parsed = date.fromisoformat(event_date_str)
            related_event = RelatedEvent(
                event_type=self._get_text_required(event_elem, "EventType"),
                event_date=event_date_parsed,
                description=self._get_text_required(event_elem, "EventDescription"),
            )
            self.logger.debug(f"Parsed related event: {related_event.event_type}")

        context = InsiderTradingAlertContext(
            alert_id=alert_id,
            alert_type=alert_type,
            rule_violated=rule_violated,
            generated_timestamp=generated_timestamp,
            trader=trader,
            trade=trade,
            related_event=related_event,
        )
        self.logger.info(
            f"Successfully parsed IT alert context: {alert_id}, "
            f"trader={trader.trader_id}, symbol={trade.symbol}"
        )
        return context

    def _parse_wash_trade_xml(
        self,
        xml_content: str,
    ) -> WashTradeAlertContext:
        """Parse WT alert XML into WashTradeAlertContext.

        Expected XML structure:
            <SmartsAlert>
                <AlertMetadata>
                    <AlertID>...</AlertID>
                    <AlertType>...</AlertType>
                    <RuleViolated>...</RuleViolated>
                    <GeneratedTimestamp>...</GeneratedTimestamp>
                    <Severity>...</Severity>
                </AlertMetadata>
                <FlaggedTrades>
                    <Trade sequence="1">...</Trade>
                    <Trade sequence="2">...</Trade>
                </FlaggedTrades>
            </SmartsAlert>

        EXCLUDES: <WashTradeIndicators>, <AnomalyScore>, <ConfidenceLevel>
                  (SMARTS pre-analysis, not raw data)

        Args:
            xml_content: Raw XML content

        Returns:
            WashTradeAlertContext with all parsed fields

        Raises:
            ValueError: If required fields are missing or < 2 trades
        """
        self.logger.info("Parsing Wash Trade alert XML")

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            self.logger.error(f"Failed to parse XML: {e}")
            raise ValueError(f"Invalid XML content: {e}") from e

        # Extract AlertMetadata
        metadata = root.find(".//AlertMetadata")
        if metadata is None:
            self.logger.error("Missing <AlertMetadata> element in WT alert XML")
            raise ValueError("Missing <AlertMetadata> element in WT alert XML")

        alert_id = self._get_text_required(metadata, "AlertID")
        alert_type = self._get_text_required(metadata, "AlertType")
        rule_violated = self._get_text_required(metadata, "RuleViolated")
        generated_timestamp_str = self._get_text_required(metadata, "GeneratedTimestamp")
        severity = self._get_text_required(metadata, "Severity")

        # Parse timestamp
        try:
            generated_timestamp = datetime.fromisoformat(
                generated_timestamp_str.replace("Z", "+00:00")
            )
        except ValueError as e:
            self.logger.error(f"Invalid timestamp format: {generated_timestamp_str}")
            raise ValueError(f"Invalid timestamp format: {generated_timestamp_str}") from e

        # Extract FlaggedTrades
        trades_elem = root.find(".//FlaggedTrades")
        if trades_elem is None:
            self.logger.error("Missing <FlaggedTrades> element in WT alert XML")
            raise ValueError("Missing <FlaggedTrades> element in WT alert XML")

        flagged_trades = []
        for trade_elem in trades_elem.findall("Trade"):
            sequence_str = trade_elem.get("sequence", "0")
            sequence = int(sequence_str) if sequence_str else 0

            # Parse trade date
            wt_trade_date_str = self._get_text_required(trade_elem, "TradeDate")
            wt_trade_date = date.fromisoformat(wt_trade_date_str)

            # Parse side as literal type
            wt_side_str = self._get_text_required(trade_elem, "Side")
            if wt_side_str not in ("BUY", "SELL"):
                raise ValueError(f"Invalid side value: {wt_side_str}, expected BUY or SELL")
            wt_side: Literal["BUY", "SELL"] = cast(Literal["BUY", "SELL"], wt_side_str)

            flagged_trade = WashTradeFlaggedTrade(
                sequence=sequence,
                account_id=self._get_text_required(trade_elem, "AccountID"),
                account_name=self._get_text_required(trade_elem, "AccountName"),
                trade_date=wt_trade_date,
                trade_time=self._get_text_required(trade_elem, "TradeTime"),
                symbol=self._get_text_required(trade_elem, "Symbol"),
                side=wt_side,
                quantity=int(self._get_text_required(trade_elem, "Quantity")),
                price=Decimal(self._get_text_required(trade_elem, "Price")),
                total_value=Decimal(self._get_text_required(trade_elem, "TotalValue")),
                counterparty_account=self._get_text_required(trade_elem, "CounterpartyAccount"),
                order_id=self._get_text_required(trade_elem, "OrderID"),
            )
            flagged_trades.append(flagged_trade)
            self.logger.debug(
                f"Parsed flagged trade {sequence}: {flagged_trade.account_id} "
                f"{flagged_trade.side} {flagged_trade.quantity}"
            )

        if len(flagged_trades) < 2:
            self.logger.error(f"Wash trade requires at least 2 trades, found {len(flagged_trades)}")
            raise ValueError(f"Wash trade requires at least 2 trades, found {len(flagged_trades)}")

        context = WashTradeAlertContext(
            alert_id=alert_id,
            alert_type=alert_type,
            rule_violated=rule_violated,
            generated_timestamp=generated_timestamp,
            severity=severity,
            flagged_trades=flagged_trades,
        )
        self.logger.info(
            f"Successfully parsed WT alert context: {alert_id}, "
            f"severity={severity}, trades={len(flagged_trades)}"
        )
        return context

    def _get_text_required(self, element: ET.Element, tag: str) -> str:
        """Get required text from XML element.

        Args:
            element: Parent XML element
            tag: Tag name to find

        Returns:
            Text content of the tag

        Raises:
            ValueError: If tag is missing or has no text
        """
        child = element.find(f".//{tag}")
        if child is None:
            raise ValueError(f"Missing required XML element: <{tag}>")
        if child.text is None:
            raise ValueError(f"Empty required XML element: <{tag}>")
        return child.text.strip()
