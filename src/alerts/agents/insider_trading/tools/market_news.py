"""Market news tool for Insider Trading Analyzer.

This tool analyzes market news to establish what public information
was available around the time of the suspicious trade. This is specific
to insider trading analysis.

In Proactive Info Flow mode, text content is injected via execute(data=...).
"""

import logging
from pathlib import Path
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin, DataFormat

logger = logging.getLogger(__name__)


class MarketNewsTool(BaseTool, DataLoadingMixin):
    """Tool to analyze market news around a trade date.

    This tool takes text data (injected in Proactive Info Flow mode)
    containing news items and uses the LLM to interpret whether public
    information could have justified the trading decision.

    Expected format: txt
    """

    # Expected data format for this tool
    expected_format: DataFormat = "txt"

    def __init__(self, llm: Any, data_dir: Path | None = None) -> None:
        """Initialize the market news tool.

        Args:
            llm: LangChain LLM instance
            data_dir: DEPRECATED - kept for backward compatibility only
        """
        super().__init__(
            llm=llm,
            name="query_market_news",
            description=(
                "Analyze market news for a symbol. "
                "Returns LLM-interpreted news timeline analysis showing what public "
                "information was available before, during, and after the trade date."
            ),
            expected_format="txt"
        )
        # Keep data_dir for backward compatibility but log deprecation
        if data_dir is not None:
            self.data_dir = data_dir
            self.news_file = data_dir / "market_news.txt"
            self.logger.warning(
                "data_dir parameter is deprecated. In Proactive Info Flow mode, "
                "data is injected via execute(data=...)."
            )
        else:
            self.data_dir = None
            self.news_file = None

        self.logger.info("Market news tool initialized (Proactive Info Flow mode)")

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
        """Build prompt for LLM to interpret market news.

        Args:
            raw_data: News content as text
            **kwargs: Optional 'symbol', 'start_date', 'end_date' for context

        Returns:
            Interpretation prompt
        """
        symbol = kwargs.get("symbol", "the flagged security")
        start_date = kwargs.get("start_date", "the relevant period")
        end_date = kwargs.get("end_date", "")

        date_range = f"from {start_date} to {end_date}" if end_date else f"around {start_date}"

        return f"""You are a compliance analyst reviewing market news for an insider trading investigation.

Analyze the following news timeline for {symbol} {date_range}.

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
