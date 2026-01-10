"""Market data tool for SMARTS Alert Analyzer.

This tool analyzes market price and volume data to understand
market conditions around the suspicious trade. This is a shared tool
used by multiple agent types.

Uses proactive information flow pattern where data is injected via execute().
"""

import logging
from pathlib import Path
from typing import Any

from alerts.tools.common.base import BaseTool

logger = logging.getLogger(__name__)


class MarketDataTool(BaseTool):
    """Tool to analyze market data around a trade date.

    This tool receives price, volume, and volatility data via execute()
    and uses the LLM to interpret market conditions and price movements.

    Uses proactive information flow pattern where data is injected
    from the Big Data Layer.
    """

    # Expected format for execute() method
    expected_format: str = "csv"

    def __init__(self, llm: Any, data_dir: Path) -> None:
        """Initialize the market data tool.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to data directory
        """
        super().__init__(
            llm=llm,
            name="query_market_data",
            description=(
                "Query market price and volume data for a symbol within a date range. "
                "Input: symbol, start_date, end_date. "
                "Returns LLM-interpreted analysis of price movements, volatility, "
                "and volume patterns around the trade date."
            )
        )
        self.data_dir = data_dir
        self.market_data_file = data_dir / "market_data.csv"
        self.logger.info(f"Market data tool initialized with file: {self.market_data_file}")

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret market data.

        Args:
            raw_data: Filtered CSV content
            **kwargs: Contains 'symbol', 'start_date', 'end_date'

        Returns:
            Interpretation prompt
        """
        symbol = kwargs.get("symbol", "unknown")
        start_date = kwargs.get("start_date", "unknown")
        end_date = kwargs.get("end_date", "unknown")

        return f"""You are a compliance analyst reviewing market data for an insider trading investigation.

Analyze the following market data for {symbol} from {start_date} to {end_date}.

**Data Columns:** symbol, date, open, high, low, close, volume, vix

**Your Task:**
1. Analyze PRICE MOVEMENT patterns:
   - What was the price trend before the suspicious trade?
   - Was there any unusual price action before the announcement?
   - What was the price impact of the material event?

2. Analyze VOLUME patterns:
   - Was there unusual volume before the announcement?
   - How does trading volume compare to typical levels?
   - Was there accumulation or distribution before the event?

3. Assess VOLATILITY (VIX):
   - Was market volatility elevated?
   - Did volatility spike before or after the event?

4. Calculate key metrics:
   - Price change from trade date to post-announcement
   - Volume multiple vs. average
   - Estimated profit/loss based on price movement

**Market Data:**
{raw_data if raw_data.strip() else f"No market data found for {symbol} in this date range."}

**Market Analysis:**"""
