"""Trader history tool for Insider Trading Analyzer.

This tool analyzes a trader's historical trading activity
to establish their baseline behavior. This is specific to insider trading
analysis - wash trade uses RelatedAccountsHistory instead.

In Proactive Info Flow mode, CSV content is injected via execute(data=...).
"""

import logging
from pathlib import Path
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin, DataFormat

logger = logging.getLogger(__name__)


class TraderHistoryTool(BaseTool, DataLoadingMixin):
    """Tool to analyze trader's historical trading activity.

    This tool takes CSV data (injected in Proactive Info Flow mode)
    containing trading history and uses the LLM to interpret their
    baseline behavior, comparing it to the flagged trade.

    Expected format: csv
    """

    # Expected data format for this tool
    expected_format: DataFormat = "csv"

    def __init__(self, llm: Any, data_dir: Path | None = None) -> None:
        """Initialize the trader history tool.

        Args:
            llm: LangChain LLM instance
            data_dir: DEPRECATED - kept for backward compatibility only
        """
        super().__init__(
            llm=llm,
            name="query_trader_history",
            description=(
                "Analyze a trader's historical trading activity. "
                "Returns LLM-interpreted baseline analysis including typical volume, "
                "sectors, frequency, and how the flagged trade deviates from normal patterns."
            ),
            expected_format="csv"
        )
        # Keep data_dir for backward compatibility but log deprecation
        if data_dir is not None:
            self.data_dir = data_dir
            self.history_file = data_dir / "trader_history.csv"
            self.logger.warning(
                "data_dir parameter is deprecated. In Proactive Info Flow mode, "
                "data is injected via execute(data=...)."
            )
        else:
            self.data_dir = None
            self.history_file = None

        self.logger.info("Trader history tool initialized (Proactive Info Flow mode)")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        In Proactive Info Flow mode, data is injected directly.
        Optional trader_id, symbol, trade_date can be provided for context.

        Args:
            **kwargs: Optional parameters for context

        Returns:
            Error message if invalid, None if valid
        """
        # No validation needed in Proactive Info Flow mode
        # Data validation is handled by execute()
        return None

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret trader's baseline.

        Args:
            raw_data: CSV content with trading history
            **kwargs: Optional 'trader_id', 'symbol', 'trade_date' for context

        Returns:
            Interpretation prompt
        """
        trader_id = kwargs.get("trader_id", "the flagged trader")
        symbol = kwargs.get("symbol", "the flagged security")
        trade_date = kwargs.get("trade_date", "the flagged trade date")

        return f"""You are a compliance analyst establishing a trader's baseline behavior.

Analyze the following trading history for {trader_id}. The trader has been flagged for trading {symbol} on {trade_date}.

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
