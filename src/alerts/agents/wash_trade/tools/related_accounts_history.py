"""Related Accounts History Tool for wash trade analysis.

This tool queries trade history for ALL related accounts (not just one trader)
to identify patterns of offsetting trades that may indicate wash trading.
"""

import logging
import os
from typing import Any, List, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin

logger = logging.getLogger(__name__)


class RelatedAccountsHistoryTool(BaseTool, DataLoadingMixin):
    """Tool to query trade history for all related accounts.

    Unlike the single-trader TraderHistoryTool used for insider trading,
    this tool analyzes trade patterns across multiple related accounts
    to detect coordinated trading activity indicative of wash trading.

    The tool looks for:
    - Offsetting trades (buy/sell of same quantity)
    - Trades between related accounts
    - Pattern frequency and recurrence
    - Historical wash trade signatures

    Data Source: test_data/wash_trade/related_accounts_history.csv

    CSV Fields:
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
        self.csv_path = os.path.join(
            data_dir, "wash_trade", "related_accounts_history.csv"
        )
        self.logger.info(f"RelatedAccountsHistoryTool initialized with data_dir: {data_dir}")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        Args:
            **kwargs: Must include 'account_ids', optionally 'symbol' and 'time_window'

        Returns:
            Error message if invalid, None if valid
        """
        if "account_ids" not in kwargs:
            return "account_ids is required"

        account_ids = kwargs.get("account_ids")
        if not account_ids:
            return "account_ids must be a non-empty list"

        if isinstance(account_ids, str):
            # Allow comma-separated string
            pass
        elif not isinstance(account_ids, list):
            return "account_ids must be a list or comma-separated string"

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
        return list(account_ids)

    def _load_data(self, **kwargs: Any) -> str:
        """Load trade history data for related accounts.

        Args:
            **kwargs: Must include 'account_ids', optionally 'symbol' and 'time_window'

        Returns:
            Filtered CSV content for the specified accounts

        Raises:
            FileNotFoundError: If CSV file doesn't exist
        """
        account_ids = self._parse_account_ids(kwargs.get("account_ids", []))
        symbol = kwargs.get("symbol", None)
        time_window = kwargs.get("time_window", "30d")

        self.logger.info(
            f"Loading trade history for accounts: {account_ids}, "
            f"symbol: {symbol}, window: {time_window}"
        )

        # Load full CSV
        csv_content = self.load_csv_as_string(self.csv_path)

        # Parse CSV header
        lines = csv_content.strip().split("\n")
        header = lines[0]
        columns = header.split(",")

        # Find column indices
        try:
            account_idx = columns.index("account_id")
        except ValueError:
            self.logger.error("account_id column not found in CSV")
            raise ValueError("Invalid CSV format: account_id column required")

        # Optional symbol filtering
        symbol_idx = None
        if symbol and "symbol" in columns:
            symbol_idx = columns.index("symbol")

        # Filter rows for specified accounts and optional symbol
        filtered_rows = [header]

        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) <= account_idx:
                continue

            row_account = parts[account_idx]

            # Check if account matches
            if row_account not in account_ids:
                continue

            # Check if symbol matches (if specified)
            if symbol and symbol_idx is not None:
                if len(parts) <= symbol_idx:
                    continue
                row_symbol = parts[symbol_idx]
                if row_symbol != symbol:
                    continue

            filtered_rows.append(line)

        filtered_csv = "\n".join(filtered_rows)
        self.logger.debug(f"Found {len(filtered_rows) - 1} trade records for related accounts")

        return filtered_csv

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
