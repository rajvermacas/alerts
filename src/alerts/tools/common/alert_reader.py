"""Alert reader tool for SMARTS Alert Analyzer.

This tool reads and parses alert XML files, extracting key information
for the agent to analyze. This is a shared tool used by all agent types.
"""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin

logger = logging.getLogger(__name__)


class AlertReaderTool(BaseTool, DataLoadingMixin):
    """Tool to read and summarize SMARTS alert XML files.

    This tool reads the full XML content and uses the LLM to
    extract and summarize the key alert information.

    Supports both legacy file-based loading (__call__) and
    proactive data injection (execute) patterns.
    """

    # Expected format for execute() method
    expected_format: str = "xml"

    def __init__(self, llm: Any, data_dir: Path) -> None:
        """Initialize the alert reader tool.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to data directory containing alerts
        """
        super().__init__(
            llm=llm,
            name="read_alert",
            description=(
                "Read and parse a SMARTS alert XML file. "
                "Returns a structured summary of the alert including trader info, "
                "suspicious activity details, anomaly indicators, and related events."
            )
        )
        self.data_dir = data_dir
        self.alerts_dir = data_dir / "alerts"
        self.logger.info(f"Alert reader initialized with alerts dir: {self.alerts_dir}")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        Args:
            **kwargs: Must contain 'alert_file_path'

        Returns:
            Error message if invalid, None if valid
        """
        alert_file_path = kwargs.get("alert_file_path")

        if not alert_file_path:
            return "alert_file_path is required"

        path = Path(alert_file_path)
        if not path.exists():
            return f"Alert file not found: {alert_file_path}"

        if not path.suffix.lower() == ".xml":
            return f"Alert file must be XML: {alert_file_path}"

        return None

    def _load_data(self, **kwargs: Any) -> str:
        """Load alert XML file.

        Args:
            **kwargs: Must contain 'alert_file_path'

        Returns:
            XML content as string
        """
        alert_file_path = kwargs["alert_file_path"]
        self.logger.info(f"Loading alert XML from: {alert_file_path}")

        return self.load_xml_file(str(alert_file_path))

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret the alert XML.

        Args:
            raw_data: XML content
            **kwargs: Additional parameters (unused)

        Returns:
            Interpretation prompt
        """
        return f"""You are a compliance analyst reviewing a SMARTS surveillance alert.

Parse the following alert XML and provide a structured summary covering:

1. **Alert Identification**
   - Alert ID
   - Alert Type
   - Rule Violated
   - Generated Timestamp

2. **Trader Information**
   - Trader ID
   - Name
   - Department

3. **Suspicious Activity Details**
   - Symbol traded
   - Trade date
   - Side (BUY/SELL)
   - Quantity
   - Price
   - Total Value

4. **Anomaly Indicators**
   - Anomaly Score
   - Confidence Level
   - Temporal Proximity to event
   - Estimated Profit

5. **Related Event** (if present)
   - Event Type
   - Event Date
   - Event Description

Provide this information in a clear, structured format that a compliance analyst can quickly review.

Alert XML:
{raw_data}

Summary:"""

    @staticmethod
    def parse_alert_context(xml_content: str) -> Dict[str, str]:
        """Extract context parameters from alert XML for other tools.

        This method parses the alert XML to extract key fields needed by other
        tools in the analysis pipeline. It supports both Insider Trading and
        Wash Trade alert XML formats.

        Args:
            xml_content: Raw XML content of the alert

        Returns:
            Dict with keys:
                - trader_id: Trader identifier (for IT alerts)
                - symbol: Stock symbol being traded
                - trade_date: Date of the suspicious trade (YYYY-MM-DD)
                - start_date: 30 days before trade date (YYYY-MM-DD)
                - end_date: 7 days after trade date (YYYY-MM-DD)

        Raises:
            ValueError: If required fields cannot be extracted from the XML

        Example:
            >>> context = AlertReaderTool.parse_alert_context(xml_content)
            >>> context["symbol"]
            'ACME'
            >>> context["trade_date"]
            '2024-03-15'
        """
        logger.debug("Parsing alert context from XML")

        # Extract trader_id (XML tag: <TraderID>)
        trader_match = re.search(r'<TraderID>([^<]+)</TraderID>', xml_content)
        if not trader_match:
            logger.error("Could not extract TraderID from alert XML")
            raise ValueError("Could not extract TraderID from alert XML")
        trader_id = trader_match.group(1).strip()
        logger.debug(f"Extracted trader_id: {trader_id}")

        # Extract symbol (XML tag: <Symbol>)
        symbol_match = re.search(r'<Symbol>([^<]+)</Symbol>', xml_content)
        if not symbol_match:
            logger.error("Could not extract Symbol from alert XML")
            raise ValueError("Could not extract Symbol from alert XML")
        symbol = symbol_match.group(1).strip()
        logger.debug(f"Extracted symbol: {symbol}")

        # Extract trade date (XML tag: <TradeDate>)
        date_match = re.search(r'<TradeDate>([^<]+)</TradeDate>', xml_content)
        if not date_match:
            logger.error("Could not extract TradeDate from alert XML")
            raise ValueError("Could not extract TradeDate from alert XML")
        trade_date_str = date_match.group(1).strip()
        logger.debug(f"Extracted trade_date: {trade_date_str}")

        # Parse trade date and compute date range (30 days before, 7 days after)
        try:
            trade_date = datetime.strptime(trade_date_str, "%Y-%m-%d")
        except ValueError as e:
            logger.error(f"Invalid trade date format: {trade_date_str}")
            raise ValueError(f"Invalid trade date format '{trade_date_str}': {e}")

        start_date = trade_date - timedelta(days=30)
        end_date = trade_date + timedelta(days=7)

        context = {
            "trader_id": trader_id,
            "symbol": symbol,
            "trade_date": trade_date_str,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        }

        logger.info(
            f"Parsed alert context: symbol={symbol}, trader_id={trader_id}, "
            f"date_range={context['start_date']} to {context['end_date']}"
        )

        return context
