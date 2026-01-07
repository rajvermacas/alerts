"""Market data tool for SMARTS Alert Analyzer.

This tool analyzes market price and volume data to understand
market conditions around the suspicious trade. This is a shared tool
used by multiple agent types.

In Proactive Info Flow mode, CSV content is injected via execute(data=...).
"""

import logging
from pathlib import Path
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin, DataFormat

logger = logging.getLogger(__name__)


class MarketDataTool(BaseTool, DataLoadingMixin):
    """Tool to analyze market data around a trade date.

    This tool takes CSV data (injected in Proactive Info Flow mode)
    containing market price/volume data and uses the LLM to interpret
    market conditions and price movements.

    Expected format: csv
    """

    # Expected data format for this tool
    expected_format: DataFormat = "csv"

    def __init__(self, llm: Any, data_dir: Path | None = None) -> None:
        """Initialize the market data tool.

        Args:
            llm: LangChain LLM instance
            data_dir: DEPRECATED - kept for backward compatibility only
        """
        super().__init__(
            llm=llm,
            name="query_market_data",
            description=(
                "Analyze market price and volume data for a symbol. "
                "Returns LLM-interpreted analysis of price movements, volatility, "
                "and volume patterns around the trade date."
            ),
            expected_format="csv"
        )
        # Keep data_dir for backward compatibility but log deprecation
        if data_dir is not None:
            self.data_dir = data_dir
            self.market_data_file = data_dir / "market_data.csv"
            self.logger.warning(
                "data_dir parameter is deprecated. In Proactive Info Flow mode, "
                "data is injected via execute(data=...)."
            )
        else:
            self.data_dir = None
            self.market_data_file = None

        self.logger.info("Market data tool initialized (Proactive Info Flow mode)")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        In Proactive Info Flow mode, data is injected directly.
        Optional symbol, start_date, end_date can be provided for context.

        Args:
            **kwargs: Optional parameters for context

        Returns:
            Error message if invalid, None if valid
        """
        # No validation needed in Proactive Info Flow mode
        # Data validation is handled by execute()
        return None

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret market data.

        Args:
            raw_data: CSV content with market data
            **kwargs: Optional 'symbol', 'start_date', 'end_date' for context

        Returns:
            Interpretation prompt
        """
        symbol = kwargs.get("symbol", "the flagged security")
        start_date = kwargs.get("start_date", "the relevant period")
        end_date = kwargs.get("end_date", "")

        date_range = f"from {start_date} to {end_date}" if end_date else f"around {start_date}"

        return f"""You are a compliance analyst reviewing market data for an insider trading investigation.

Analyze the following market data for {symbol} {date_range}.

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
