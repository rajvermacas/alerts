"""Related Accounts History Tool for wash trade analysis.

This tool analyzes trade history for ALL related accounts (not just one trader)
to identify patterns of offsetting trades that may indicate wash trading.

In Proactive Info Flow mode, CSV content is injected via execute(data=...).
"""

import logging
from pathlib import Path
from typing import Any, List, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin, DataFormat

logger = logging.getLogger(__name__)


class RelatedAccountsHistoryTool(BaseTool, DataLoadingMixin):
    """Tool to analyze trade history for all related accounts.

    This tool takes CSV data (injected in Proactive Info Flow mode)
    containing trade history and analyzes patterns across multiple
    related accounts to detect coordinated trading activity
    indicative of wash trading.

    Expected format: csv

    CSV Fields (expected by Big Data Layer):
        - account_id: Account that executed the trade
        - trade_date: Date of trade (YYYY-MM-DD)
        - trade_time: Time of trade (HH:MM:SS.mmm)
        - symbol: Trading symbol
        - side: BUY or SELL
        - quantity: Number of shares
        - price: Trade price
        - counterparty_account: Account on other side of trade
        - order_id: Order identifier
    """

    # Expected data format for this tool
    expected_format: DataFormat = "csv"

    def __init__(self, llm: Any, data_dir: str | Path | None = None) -> None:
        """Initialize the RelatedAccountsHistoryTool.

        Args:
            llm: LangChain LLM instance
            data_dir: DEPRECATED - kept for backward compatibility only
        """
        super().__init__(
            llm=llm,
            name="related_accounts_history",
            description=(
                "Analyze trade history for multiple related accounts. "
                "Finds patterns of offsetting trades between accounts that share "
                "beneficial ownership. Analyzes trade frequency, timing patterns, "
                "and historical recurrence of similar trading behavior."
            ),
            expected_format="csv"
        )
        # Keep data_dir for backward compatibility but log deprecation
        if data_dir is not None:
            self.data_dir = str(data_dir) if isinstance(data_dir, Path) else data_dir
            self.logger.warning(
                "data_dir parameter is deprecated. In Proactive Info Flow mode, "
                "data is injected via execute(data=...)."
            )
        else:
            self.data_dir = None

        self.logger.info("RelatedAccountsHistoryTool initialized (Proactive Info Flow mode)")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        In Proactive Info Flow mode, data is injected directly.
        Optional account_ids, symbol, time_window can be provided for context.

        Args:
            **kwargs: Optional parameters for context

        Returns:
            Error message if invalid, None if valid
        """
        # No validation needed in Proactive Info Flow mode
        # Data validation is handled by execute()
        return None

    def _parse_account_ids(self, account_ids: Any) -> List[str]:
        """Parse account IDs from various input formats.

        Args:
            account_ids: List of account IDs or comma-separated string

        Returns:
            List of account ID strings
        """
        if isinstance(account_ids, str):
            return [aid.strip() for aid in account_ids.split(",")]
        return list(account_ids) if account_ids else []

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM interpretation of trade history.

        Args:
            raw_data: Filtered CSV content with trade history
            **kwargs: Must include 'account_ids'

        Returns:
            Prompt for LLM interpretation
        """
        account_ids = self._parse_account_ids(kwargs.get("account_ids", []))
        symbol = kwargs.get("symbol", "all symbols")
        time_window = kwargs.get("time_window", "30d")

        prompt = f"""You are analyzing trade history for related accounts to detect wash trading patterns.

## Task
Analyze trade history for the following related accounts: {', '.join(account_ids)}
Looking at: {symbol} trades within {time_window} time window.

## Trade History Data
```csv
{raw_data}
```

## Analysis Requirements
1. **Offsetting Trades**: Identify trades where one account buys and another sells the same quantity
2. **Counterparty Analysis**: Look for trades where related accounts are counterparties to each other
3. **Timing Patterns**: Note trades that occur within seconds or minutes of each other
4. **Pattern Frequency**: Count how often similar trading patterns have occurred
5. **Historical Comparison**: Assess if this is a recurring pattern or one-off occurrence

## Wash Trade Indicators
- Same quantity buy and sell between related accounts
- Trades within very short time windows (< 1 second is highly suspicious)
- Repeated patterns over time (suggests systematic behavior)
- Same price trades with no market movement
- Trades that would return shares to original holder

## Output Format
Provide a concise analysis (2-3 paragraphs) covering:
1. Summary of trading activity between the related accounts
2. Specific wash trade patterns identified (if any), with dates and quantities
3. Historical frequency assessment - is this a recurring pattern?
4. Risk level for wash trading: HIGH (clear pattern), MEDIUM (some indicators), LOW (normal activity)

Be specific about trade dates, times, quantities, and which accounts were involved.
If accounts traded with each other as counterparties, highlight this explicitly."""

        return prompt


def create_related_accounts_history_tool(llm: Any, data_dir: str) -> dict:
    """Create LangChain-compatible tool for related accounts history.

    Args:
        llm: LangChain LLM instance
        data_dir: Path to data directory

    Returns:
        Dictionary with tool function and metadata
    """
    tool = RelatedAccountsHistoryTool(llm, data_dir)

    def related_accounts_history_func(
        account_ids: str,
        symbol: Optional[str] = None,
        time_window: str = "30d"
    ) -> str:
        """Query trade history for multiple related accounts.

        Args:
            account_ids: Comma-separated list of account IDs (e.g., "ACC-001,ACC-002")
            symbol: Optional symbol to filter trades
            time_window: Time window for analysis (default: "30d")

        Returns:
            Analysis of trading patterns between related accounts
        """
        return tool(account_ids=account_ids, symbol=symbol, time_window=time_window)

    return {
        "func": related_accounts_history_func,
        "name": tool.name,
        "description": tool.description,
        "tool_instance": tool,
    }
