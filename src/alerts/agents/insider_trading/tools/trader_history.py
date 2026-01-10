"""Trader history tool for Insider Trading Analyzer.

This tool analyzes a trader's historical trading activity
to establish their baseline behavior. This is specific to insider trading
analysis - wash trade uses RelatedAccountsHistory instead.

Uses proactive information flow pattern where data is injected via execute().
"""

import logging
from pathlib import Path
from typing import Any

from alerts.tools.common.base import BaseTool

logger = logging.getLogger(__name__)


class TraderHistoryTool(BaseTool):
    """Tool to analyze trader's historical trading activity.

    This tool receives trading history data via execute() and uses the LLM to
    interpret their baseline behavior, comparing it to the flagged trade.

    Uses proactive information flow pattern where data is injected
    from the Big Data Layer.
    """

    # Expected format for execute() method
    expected_format: str = "csv"

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

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret trader's baseline.

        Args:
            raw_data: Filtered CSV content
            **kwargs: Contains 'trader_id', 'symbol', 'trade_date'

        Returns:
            Interpretation prompt
        """
        trader_id = kwargs.get("trader_id", "unknown")
        symbol = kwargs.get("symbol", "unknown")
        trade_date = kwargs.get("trade_date", "unknown")

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
