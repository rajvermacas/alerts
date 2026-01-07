"""Mock Big Data Layer Simulator.

This module simulates the Big Data Layer for POC testing and contract validation.
It reads from test_data/ and constructs AnalysisRequest payloads exactly as the
real Big Data Layer would.

The Big Data Layer (owned by external team) is responsible for:
1. Ingesting raw alerts from SMARTS surveillance system
2. Querying production databases for trader/market data
3. Filtering and aggregating relevant data per tool requirements
4. Determining agent_type (insider_trading | wash_trade)
5. Constructing the AnalysisRequest JSON payload

This simulator provides the same interface for local testing.
"""

import logging
import re
from pathlib import Path
from typing import Literal

from alerts.models.request import (
    AnalysisRequest,
    ToolInput,
    INSIDER_TRADING_REQUIRED_TOOLS,
    WASH_TRADE_REQUIRED_TOOLS,
)

logger = logging.getLogger(__name__)

# Default test data directory
DEFAULT_TEST_DATA_DIR = Path(__file__).parent.parent.parent.parent / "test_data"


class BigDataSimulatorError(Exception):
    """Base exception for Big Data Simulator errors."""
    pass


class AlertFileNotFoundError(BigDataSimulatorError):
    """Raised when alert file is not found."""
    pass


class DataFileNotFoundError(BigDataSimulatorError):
    """Raised when a required data file is not found."""

    def __init__(self, tool_name: str, file_path: Path) -> None:
        self.tool_name = tool_name
        self.file_path = file_path
        super().__init__(
            f"Data file not found for tool '{tool_name}': {file_path}"
        )


class UnknownAgentTypeError(BigDataSimulatorError):
    """Raised when agent type cannot be determined from alert."""

    def __init__(self, alert_file: str) -> None:
        self.alert_file = alert_file
        super().__init__(
            f"Could not determine agent type from alert: {alert_file}"
        )


class BigDataSimulator:
    """Simulates the Big Data Layer for POC testing.

    This class reads from test_data/ and constructs AnalysisRequest
    payloads exactly as the real Big Data Layer would.

    Attributes:
        test_data_dir: Path to test data directory

    Example:
        >>> simulator = BigDataSimulator()
        >>> request = simulator.create_request("test_data/alerts/alert_genuine.xml")
        >>> print(request.agent_type)
        "insider_trading"
    """

    # Patterns for detecting agent type from alert content
    INSIDER_TRADING_PATTERNS = [
        r"insider",
        r"pre-announcement",
        r"mnpi",
        r"SMARTS-IT-",
        r"SMARTS-PAT-",
    ]

    WASH_TRADE_PATTERNS = [
        r"wash",
        r"self-trade",
        r"circular",
        r"SMARTS-WT-",
        r"WT-",
        r"WASH_TRADE",
    ]

    # File mappings for each tool
    INSIDER_TRADING_FILE_MAP = {
        "alert_reader": ("alerts/{alert_name}", "xml"),
        "market_news": ("market_news.txt", "txt"),
        "market_data": ("market_data.csv", "csv"),
        "trader_profile": ("trader_profiles.csv", "csv"),
        "trader_history": ("trader_history.csv", "csv"),
    }

    WASH_TRADE_FILE_MAP = {
        "alert_reader": ("alerts/wash_trade/{alert_name}", "xml"),
        "market_data": ("market_data.csv", "csv"),
        "trader_profile": ("trader_profiles.csv", "csv"),
        "account_relationships": ("wash_trade/account_relationships.csv", "csv"),
        "related_accounts_history": ("wash_trade/related_accounts_history.csv", "csv"),
        "trade_timing": ("wash_trade/trade_timing.csv", "csv"),
        "counterparty_analysis": ("wash_trade/counterparty_analysis.csv", "csv"),
    }

    def __init__(self, test_data_dir: Path | str | None = None) -> None:
        """Initialize the simulator.

        Args:
            test_data_dir: Path to test data directory. Defaults to project's test_data/
        """
        if test_data_dir is None:
            self.test_data_dir = DEFAULT_TEST_DATA_DIR
        else:
            self.test_data_dir = Path(test_data_dir)

        if not self.test_data_dir.exists():
            raise BigDataSimulatorError(
                f"Test data directory not found: {self.test_data_dir}"
            )

        logger.info(f"BigDataSimulator initialized with test_data_dir: {self.test_data_dir}")

    def _read_file(self, file_path: Path) -> str:
        """Read file content as string.

        Args:
            file_path: Path to file

        Returns:
            File content as string

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        logger.debug(f"Reading file: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def _determine_agent_type(
        self,
        alert_content: str,
        alert_file: str
    ) -> Literal["insider_trading", "wash_trade"]:
        """Determine agent type from alert content.

        In production, this would be done by the Big Data Layer using
        more sophisticated rules. For POC, we use pattern matching.

        Args:
            alert_content: XML content of the alert
            alert_file: Path to alert file (for fallback detection)

        Returns:
            Agent type: "insider_trading" or "wash_trade"

        Raises:
            UnknownAgentTypeError: If agent type cannot be determined
        """
        alert_lower = alert_content.lower()
        file_lower = alert_file.lower()

        # Check wash trade patterns first (more specific)
        for pattern in self.WASH_TRADE_PATTERNS:
            if re.search(pattern, alert_lower, re.IGNORECASE):
                logger.debug(f"Detected wash_trade from pattern: {pattern}")
                return "wash_trade"

        # Check file path for wash trade indicators
        if "wash" in file_lower:
            logger.debug("Detected wash_trade from file path")
            return "wash_trade"

        # Check insider trading patterns
        for pattern in self.INSIDER_TRADING_PATTERNS:
            if re.search(pattern, alert_lower, re.IGNORECASE):
                logger.debug(f"Detected insider_trading from pattern: {pattern}")
                return "insider_trading"

        # Default to insider trading for non-wash trade alerts
        # This matches the current behavior where IT is the default
        logger.debug("Defaulting to insider_trading (no specific pattern matched)")
        return "insider_trading"

    def _load_tool_data_for_insider_trading(
        self,
        alert_file: Path
    ) -> dict[str, ToolInput]:
        """Load tool data for insider trading agent.

        Args:
            alert_file: Path to the alert file

        Returns:
            Dictionary mapping tool names to ToolInput

        Raises:
            DataFileNotFoundError: If required data file not found
        """
        tool_data = {}
        alert_name = alert_file.name

        for tool_name in INSIDER_TRADING_REQUIRED_TOOLS:
            file_pattern, format_type = self.INSIDER_TRADING_FILE_MAP[tool_name]

            # Handle dynamic alert file path
            if "{alert_name}" in file_pattern:
                # For alert_reader, use the provided alert file directly
                file_path = alert_file
            else:
                file_path = self.test_data_dir / file_pattern

            if not file_path.exists():
                raise DataFileNotFoundError(tool_name, file_path)

            data = self._read_file(file_path)
            tool_data[tool_name] = ToolInput(format=format_type, data=data)
            logger.debug(
                f"Loaded {tool_name}: {len(data)} chars from {file_path}"
            )

        return tool_data

    def _load_tool_data_for_wash_trade(
        self,
        alert_file: Path
    ) -> dict[str, ToolInput]:
        """Load tool data for wash trade agent.

        Args:
            alert_file: Path to the alert file

        Returns:
            Dictionary mapping tool names to ToolInput

        Raises:
            DataFileNotFoundError: If required data file not found
        """
        tool_data = {}

        for tool_name in WASH_TRADE_REQUIRED_TOOLS:
            file_pattern, format_type = self.WASH_TRADE_FILE_MAP[tool_name]

            # Handle dynamic alert file path
            if "{alert_name}" in file_pattern:
                # For alert_reader, use the provided alert file directly
                file_path = alert_file
            else:
                file_path = self.test_data_dir / file_pattern

            # Check if file exists, create placeholder if missing
            if not file_path.exists():
                logger.warning(
                    f"Data file not found for {tool_name}: {file_path}. "
                    f"Creating placeholder data."
                )
                # Create placeholder data for missing files
                data = self._create_placeholder_data(tool_name, format_type)
            else:
                data = self._read_file(file_path)

            tool_data[tool_name] = ToolInput(format=format_type, data=data)
            logger.debug(
                f"Loaded {tool_name}: {len(data)} chars"
            )

        return tool_data

    def _create_placeholder_data(self, tool_name: str, format_type: str) -> str:
        """Create placeholder data for missing files.

        This is a fallback for POC testing when data files don't exist yet.

        Args:
            tool_name: Name of the tool
            format_type: Expected format (csv, txt, xml)

        Returns:
            Placeholder data string
        """
        if format_type == "csv":
            placeholders = {
                "trade_timing": (
                    "trade_id,timestamp_ms,account_id,symbol,side,quantity,price\n"
                    "T001,1704873600123,ACC001,AAPL,BUY,1000,185.50\n"
                    "T002,1704873600456,ACC002,AAPL,SELL,1000,185.50"
                ),
                "counterparty_analysis": (
                    "trade_id,account_id,counterparty_id,beneficial_owner,relationship\n"
                    "T001,ACC001,ACC002,John Smith,SAME_ENTITY\n"
                    "T002,ACC002,ACC001,John Smith,SAME_ENTITY"
                ),
            }
            return placeholders.get(
                tool_name,
                f"id,data\n1,placeholder_{tool_name}"
            )
        elif format_type == "txt":
            return f"Placeholder data for {tool_name}"
        else:
            return f"<placeholder tool='{tool_name}'/>"

    def create_request(
        self,
        alert_file: str | Path,
        agent_type: Literal["insider_trading", "wash_trade"] | None = None
    ) -> AnalysisRequest:
        """Create an AnalysisRequest from an alert file.

        This is the main entry point for simulating the Big Data Layer.
        It reads the alert, determines the agent type (if not specified),
        and aggregates all required tool data.

        Args:
            alert_file: Path to the alert XML file
            agent_type: Optional agent type override. If not provided,
                       will be determined from alert content.

        Returns:
            AnalysisRequest ready to be sent to the Orchestrator

        Raises:
            AlertFileNotFoundError: If alert file doesn't exist
            DataFileNotFoundError: If required data file doesn't exist
            UnknownAgentTypeError: If agent type cannot be determined
        """
        alert_path = Path(alert_file)

        # Handle relative paths
        if not alert_path.is_absolute():
            # Try relative to test_data first
            if (self.test_data_dir / alert_path).exists():
                alert_path = self.test_data_dir / alert_path
            # Then try relative to current directory
            elif not alert_path.exists():
                raise AlertFileNotFoundError(
                    f"Alert file not found: {alert_file}"
                )

        if not alert_path.exists():
            raise AlertFileNotFoundError(f"Alert file not found: {alert_path}")

        logger.info(f"Creating AnalysisRequest from alert: {alert_path}")

        # Read alert content
        alert_xml = self._read_file(alert_path)

        # Determine agent type if not specified
        if agent_type is None:
            agent_type = self._determine_agent_type(alert_xml, str(alert_path))

        logger.info(f"Agent type: {agent_type}")

        # Load tool data based on agent type
        if agent_type == "insider_trading":
            tool_data = self._load_tool_data_for_insider_trading(alert_path)
        else:
            tool_data = self._load_tool_data_for_wash_trade(alert_path)

        # Construct and return the request
        request = AnalysisRequest(
            alert_xml=alert_xml,
            agent_type=agent_type,
            tool_data=tool_data
        )

        logger.info(
            f"Created AnalysisRequest: agent_type={agent_type}, "
            f"tools={list(tool_data.keys())}"
        )

        return request

    def create_request_from_dict(
        self,
        alert_xml: str,
        agent_type: Literal["insider_trading", "wash_trade"],
        tool_data_dict: dict[str, dict[str, str]]
    ) -> AnalysisRequest:
        """Create an AnalysisRequest from raw dictionaries.

        This is useful for testing with custom data that doesn't come from files.

        Args:
            alert_xml: Alert XML content
            agent_type: Agent type
            tool_data_dict: Dictionary mapping tool names to {"format": ..., "data": ...}

        Returns:
            AnalysisRequest

        Example:
            >>> request = simulator.create_request_from_dict(
            ...     alert_xml="<ALERT>...</ALERT>",
            ...     agent_type="insider_trading",
            ...     tool_data_dict={
            ...         "alert_reader": {"format": "xml", "data": "<ALERT>...</ALERT>"},
            ...         "market_news": {"format": "txt", "data": "News..."},
            ...         ...
            ...     }
            ... )
        """
        tool_data = {
            name: ToolInput(format=data["format"], data=data["data"])
            for name, data in tool_data_dict.items()
        }

        return AnalysisRequest(
            alert_xml=alert_xml,
            agent_type=agent_type,
            tool_data=tool_data
        )

    def get_available_alerts(self) -> dict[str, list[Path]]:
        """Get list of available alert files by agent type.

        Returns:
            Dictionary mapping agent type to list of alert file paths
        """
        alerts = {
            "insider_trading": [],
            "wash_trade": [],
        }

        # Insider trading alerts
        it_alerts_dir = self.test_data_dir / "alerts"
        if it_alerts_dir.exists():
            for f in it_alerts_dir.glob("*.xml"):
                alerts["insider_trading"].append(f)

        # Wash trade alerts
        wt_alerts_dir = self.test_data_dir / "alerts" / "wash_trade"
        if wt_alerts_dir.exists():
            for f in wt_alerts_dir.glob("*.xml"):
                alerts["wash_trade"].append(f)

        return alerts
