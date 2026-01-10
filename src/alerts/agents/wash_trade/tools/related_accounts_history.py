"""Related Accounts History Tool for wash trade analysis.

This tool analyzes trade history for ALL related accounts (not just one trader)
to identify patterns of offsetting trades that may indicate wash trading.

Uses proactive information flow pattern where data is injected via execute().
"""

import logging
from typing import Any, List

from alerts.tools.common.base import BaseTool

logger = logging.getLogger(__name__)


class RelatedAccountsHistoryTool(BaseTool):
    """Tool to analyze trade history for all related accounts.

    Unlike the single-trader TraderHistoryTool used for insider trading,
    this tool analyzes trade patterns across multiple related accounts
    to detect coordinated trading activity indicative of wash trading.

    The tool looks for:
    - Offsetting trades (buy/sell of same quantity)
    - Trades between related accounts
    - Pattern frequency and recurrence
    - Historical wash trade signatures

    Uses proactive information flow pattern where data is injected
    from the Big Data Layer.

    CSV Fields (expected in injected data):
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

    # Expected format for execute() method
    expected_format: str = "csv"

    def __init__(self, llm: Any, data_dir: str) -> None:
        """Initialize the RelatedAccountsHistoryTool.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to the data directory containing wash_trade subdirectory
        """
        super().__init__(
            llm=llm,
            name="related_accounts_history",
            description=(
                "Query trade history for multiple related accounts. "
                "Use this tool to find patterns of offsetting trades between "
                "accounts that share beneficial ownership. Analyzes trade frequency, "
                "timing patterns, and historical recurrence of similar trading behavior."
            ),
        )
        self.data_dir = data_dir
        self.logger.info(f"RelatedAccountsHistoryTool initialized with data_dir: {data_dir}")

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
            **kwargs: May include 'account_ids', 'symbol', 'time_window'

        Returns:
            Prompt for LLM interpretation
        """
        account_ids = self._parse_account_ids(kwargs.get("account_ids", []))
        symbol = kwargs.get("symbol", "all symbols")
        time_window = kwargs.get("time_window", "30d")

        prompt = f"""You are analyzing trade history for related accounts to detect wash trading patterns.

## Task
Analyze trade history for the following related accounts: {', '.join(account_ids) if account_ids else 'provided accounts'}
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
