"""Market news tool for Insider Trading Analyzer.

This tool analyzes market news to establish what public information
was available around the time of the suspicious trade. This is specific
to insider trading analysis.

Uses proactive information flow pattern where data is injected via execute().
"""

import logging
from pathlib import Path
from typing import Any

from alerts.tools.common.base import BaseTool

logger = logging.getLogger(__name__)


class MarketNewsTool(BaseTool):
    """Tool to analyze market news around a trade date.

    This tool receives news content via execute() and uses the LLM to
    interpret whether public information could have justified the trading decision.

    Uses proactive information flow pattern where data is injected
    from the Big Data Layer.
    """

    # Expected format for execute() method
    expected_format: str = "txt"

    def __init__(self, llm: Any, data_dir: Path) -> None:
        """Initialize the market news tool.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to data directory
        """
        super().__init__(
            llm=llm,
            name="query_market_news",
            description=(
                "Query market news for a symbol within a date range. "
                "Input: symbol, start_date, end_date. "
                "Returns LLM-interpreted news timeline analysis showing what public "
                "information was available before, during, and after the trade date."
            )
        )
        self.data_dir = data_dir
        self.news_file = data_dir / "market_news.txt"
        self.logger.info(f"Market news tool initialized with file: {self.news_file}")

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret market news.

        Args:
            raw_data: Filtered news content
            **kwargs: Contains 'symbol', 'start_date', 'end_date'

        Returns:
            Interpretation prompt
        """
        symbol = kwargs.get("symbol", "unknown")
        start_date = kwargs.get("start_date", "unknown")
        end_date = kwargs.get("end_date", "unknown")

        return f"""You are a compliance analyst reviewing market news for an insider trading investigation.

Analyze the following news timeline for {symbol} from {start_date} to {end_date}.

**Your Task:**
1. Create a CHRONOLOGICAL timeline of significant news events
2. Identify what PUBLIC INFORMATION was available BEFORE the suspicious trade
3. Determine when the material announcement (M&A, earnings, FDA approval, etc.) became PUBLIC
4. Assess whether there were any LEAKS, RUMORS, or ANALYST HINTS before the announcement
5. Evaluate if a reasonable investor could have made the trading decision based on PUBLIC information alone

**Key Question:** Was there any public information that could have justified a bullish/bearish position before the material event?

**News Content:**
{raw_data if raw_data.strip() else f"No news found for {symbol} in this date range."}

**News Timeline Analysis:**"""
