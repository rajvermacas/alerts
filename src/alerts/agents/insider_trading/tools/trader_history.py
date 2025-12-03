"""Trader history tool for Insider Trading Analyzer.

This tool queries and analyzes a trader's historical trading activity
to establish their baseline behavior. This is specific to insider trading
analysis - wash trade uses RelatedAccountsHistory instead.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin

logger = logging.getLogger(__name__)


class TraderHistoryTool(BaseTool, DataLoadingMixin):
    """Tool to query and analyze trader's historical trading activity.

    This tool retrieves a trader's past trades and uses the LLM to
    interpret their baseline behavior, comparing it to the flagged trade.
    """

    def __init__(self, llm: Any, data_dir: Path) -> None:
        """Initialize the trader history tool.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to data directory
        """
        super().__init__(
            llm=llm,
            name="query_trader_history",
            description=(
                "Query a trader's historical trading activity over the past year. "
                "Input: trader_id, symbol (the flagged symbol), trade_date (the flagged trade date). "
                "Returns LLM-interpreted baseline analysis including typical volume, "
                "sectors, frequency, and how the flagged trade deviates from normal patterns."
            )
        )
        self.data_dir = data_dir
        self.history_file = data_dir / "trader_history.csv"
        self.logger.info(f"Trader history tool initialized with file: {self.history_file}")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        Args:
            **kwargs: Must contain 'trader_id', 'symbol', 'trade_date'

        Returns:
            Error message if invalid, None if valid
        """
        required = ["trader_id", "symbol", "trade_date"]
        for field in required:
            if not kwargs.get(field):
                return f"{field} is required"

        if not self.history_file.exists():
            return f"Trader history file not found: {self.history_file}"

        return None

    def _load_data(self, **kwargs: Any) -> str:
        """Load trader's historical trading data.

        Args:
            **kwargs: Must contain 'trader_id', 'symbol', 'trade_date'

        Returns:
            Filtered CSV content for the trader
        """
        trader_id = kwargs["trader_id"]
        symbol = kwargs["symbol"]
        trade_date = kwargs["trade_date"]

        self.logger.info(
            f"Loading history for trader {trader_id}, symbol {symbol}, trade date {trade_date}"
        )

        # Load full CSV
        csv_content = self.load_csv_as_string(str(self.history_file))

        # Filter for this trader
        trader_data = self.filter_csv_by_column(csv_content, "trader_id", trader_id)

        # Calculate date range (1 year lookback from trade date)
        try:
            trade_dt = datetime.strptime(trade_date, "%Y-%m-%d")
            start_date = (trade_dt - timedelta(days=365)).strftime("%Y-%m-%d")
            end_date = trade_date
        except ValueError:
            self.logger.warning(f"Invalid trade_date format: {trade_date}, using all data")
            return trader_data

        # Filter by date range
        filtered_data = self.filter_csv_by_date_range(
            trader_data, "date", start_date, end_date
        )

        self.logger.debug(f"Filtered to {filtered_data.count(chr(10))} rows")

        return filtered_data

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret trader's baseline.

        Args:
            raw_data: Filtered CSV content
            **kwargs: Contains 'trader_id', 'symbol', 'trade_date'

        Returns:
            Interpretation prompt
        """
        trader_id = kwargs["trader_id"]
        symbol = kwargs["symbol"]
        trade_date = kwargs["trade_date"]

        return f"""You are a compliance analyst establishing a trader's baseline behavior.

Analyze the following 1-year trading history for trader {trader_id}. The trader has been flagged for trading {symbol} on {trade_date}.

**Your Task:**
1. Identify the trader's TYPICAL trading patterns:
   - What is their average daily/weekly volume?
   - What sectors do they typically trade?
   - How frequently do they trade?
   - What is their typical position size?

2. Assess how the flagged trade ({symbol} on {trade_date}) DEVIATES from their baseline:
   - Is this a new sector for them?
   - Is the volume unusual compared to their history?
   - Is this trading pattern consistent or anomalous?

3. Provide a clear assessment of whether this trade fits their established pattern or represents unusual behavior.

**Trading History:**
{raw_data if raw_data.strip() else "No trading history found for this trader in the past year."}

**Baseline Analysis:**"""
