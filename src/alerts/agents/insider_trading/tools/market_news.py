"""Market news tool for Insider Trading Analyzer.

This tool queries market news to establish what public information
was available around the time of the suspicious trade. This is specific
to insider trading analysis.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin

logger = logging.getLogger(__name__)


class MarketNewsTool(BaseTool, DataLoadingMixin):
    """Tool to query and analyze market news around a trade date.

    This tool retrieves news items for a symbol within a date range
    and uses the LLM to interpret whether public information could
    have justified the trading decision.
    """

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

        if not self.news_file.exists():
            return f"Market news file not found: {self.news_file}"

        return None

    def _load_data(self, **kwargs: Any) -> str:
        """Load market news for the symbol.

        Args:
            **kwargs: Must contain 'symbol', 'start_date', 'end_date'

        Returns:
            Relevant news content
        """
        symbol = kwargs["symbol"]
        start_date = kwargs["start_date"]
        end_date = kwargs["end_date"]

        self.logger.info(
            f"Loading news for {symbol} from {start_date} to {end_date}"
        )

        # Load full news file
        news_content = self.load_text_file(str(self.news_file))

        # Find the section for this symbol
        # The news file has sections marked with "===== SYMBOL News Timeline ====="
        symbol_section = ""
        in_section = False
        section_marker = f"===== {symbol}"

        for line in news_content.split("\n"):
            if section_marker in line.upper():
                in_section = True
                symbol_section = line + "\n"
            elif in_section:
                if line.startswith("=====") and section_marker not in line.upper():
                    break
                symbol_section += line + "\n"

        if not symbol_section.strip():
            self.logger.warning(f"No news section found for symbol {symbol}")
            return f"No news found for {symbol}"

        # Filter by date range
        filtered_lines = []
        for line in symbol_section.split("\n"):
            # Check if line starts with a date (YYYY-MM-DD format)
            if len(line) >= 10 and line[4] == "-" and line[7] == "-":
                line_date = line[:10]
                if start_date <= line_date <= end_date:
                    filtered_lines.append(line)
            elif not line.startswith("20"):  # Keep non-dated lines (headers)
                filtered_lines.append(line)

        result = "\n".join(filtered_lines)
        self.logger.debug(f"Filtered news: {len(filtered_lines)} lines")

        return result

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret market news.

        Args:
            raw_data: Filtered news content
            **kwargs: Contains 'symbol', 'start_date', 'end_date'

        Returns:
            Interpretation prompt
        """
        symbol = kwargs["symbol"]
        start_date = kwargs["start_date"]
        end_date = kwargs["end_date"]

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
