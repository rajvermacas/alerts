"""Market data tool for SMARTS Alert Analyzer.

This tool queries market price and volume data to understand
market conditions around the suspicious trade. This is a shared tool
used by multiple agent types.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin

logger = logging.getLogger(__name__)


class MarketDataTool(BaseTool, DataLoadingMixin):
    """Tool to query and analyze market data around a trade date.

    This tool retrieves price, volume, and volatility data for a symbol
    and uses the LLM to interpret market conditions and price movements.
    """

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

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        Args:
            **kwargs: Must contain 'symbol', 'start_date', 'end_date'

        Returns:
            Error message if invalid, None if valid
        """
        required = ["symbol", "start_date", "end_date"]
        for field in required:
            if not kwargs.get(field):
                return f"{field} is required"

        if not self.market_data_file.exists():
            return f"Market data file not found: {self.market_data_file}"

        return None

    def _load_data(self, **kwargs: Any) -> str:
        """Load market data for the symbol.

        Args:
            **kwargs: Must contain 'symbol', 'start_date', 'end_date'

        Returns:
            Filtered CSV content
        """
        symbol = kwargs["symbol"]
        start_date = kwargs["start_date"]
        end_date = kwargs["end_date"]

        self.logger.info(
            f"Loading market data for {symbol} from {start_date} to {end_date}"
        )

        # Load full CSV
        csv_content = self.load_csv_as_string(str(self.market_data_file))

        # Filter for this symbol
        symbol_data = self.filter_csv_by_column(csv_content, "symbol", symbol)

        # Filter by date range
        filtered_data = self.filter_csv_by_date_range(
            symbol_data, "date", start_date, end_date
        )

        self.logger.debug(f"Filtered to {filtered_data.count(chr(10))} rows")

        return filtered_data

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret market data.

        Args:
            raw_data: Filtered CSV content
            **kwargs: Contains 'symbol', 'start_date', 'end_date'

        Returns:
            Interpretation prompt
        """
        symbol = kwargs["symbol"]
        start_date = kwargs["start_date"]
        end_date = kwargs["end_date"]

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
