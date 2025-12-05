"""Peer trades tool for SMARTS Alert Analyzer.

This tool queries peer trading activity to understand how other
traders were positioned around the suspicious trade.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin

logger = logging.getLogger(__name__)


class PeerTradesTool(BaseTool, DataLoadingMixin):
    """Tool to query and analyze peer trading activity.

    This tool retrieves trading activity from other traders in the
    same symbol and uses the LLM to interpret whether the flagged
    trader's activity was isolated or part of broader market movement.
    """

    def __init__(self, llm: Any, data_dir: Path) -> None:
        """Initialize the peer trades tool.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to data directory
        """
        super().__init__(
            llm=llm,
            name="query_peer_trades",
            description=(
                "Query peer trading activity for a symbol within a date range. "
                "Input: symbol, start_date, end_date. "
                "Returns LLM-interpreted analysis of how other traders were "
                "positioned, whether the flagged activity was isolated or part of "
                "broader market consensus."
            )
        )
        self.data_dir = data_dir
        self.peer_trades_file = data_dir / "peer_trades.csv"
        self.logger.info(f"Peer trades tool initialized with file: {self.peer_trades_file}")

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

        if not self.peer_trades_file.exists():
            return f"Peer trades file not found: {self.peer_trades_file}"

        return None

    def _load_data(self, **kwargs: Any) -> str:
        """Load peer trading data for the symbol.

        Args:
            **kwargs: Must contain 'symbol', 'start_date', 'end_date'

        Returns:
            Filtered CSV content
        """
        symbol = kwargs["symbol"]
        start_date = kwargs["start_date"]
        end_date = kwargs["end_date"]

        self.logger.info(
            f"Loading peer trades for {symbol} from {start_date} to {end_date}"
        )

        # Load full CSV
        csv_content = self.load_csv_as_string(str(self.peer_trades_file))

        # Filter for this symbol
        symbol_data = self.filter_csv_by_column(csv_content, "symbol", symbol)

        # Filter by date range
        filtered_data = self.filter_csv_by_date_range(
            symbol_data, "date", start_date, end_date
        )

        self.logger.debug(f"Filtered to {filtered_data.count(chr(10))} rows")

        return filtered_data

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret peer trading activity.

        Args:
            raw_data: Filtered CSV content
            **kwargs: Contains 'symbol', 'start_date', 'end_date'

        Returns:
            Interpretation prompt
        """
        symbol = kwargs["symbol"]
        start_date = kwargs["start_date"]
        end_date = kwargs["end_date"]

        return f"""You are a compliance analyst reviewing peer trading activity for an insider trading investigation.

Analyze the following peer trading data for {symbol} from {start_date} to {end_date}.

**Data Columns:** trader_id, date, symbol, side, qty, price, trader_type

**Your Task:**
1. Analyze the DIRECTION of peer activity:
   - Were peers net BUYING or SELLING?
   - What was the institutional vs. retail split?
   - Did peers show conviction in either direction?

2. Compare to the FLAGGED TRADER:
   - Was the flagged trader trading WITH or AGAINST peer flow?
   - Was their position size unusual compared to peers?
   - Was their timing ahead of or behind peers?

3. Assess ISOLATION:
   - Was the flagged trade an ISOLATED action (no peer support)?
   - Or was it part of BROADER market consensus?
   - Isolated trades are more suspicious for insider trading

4. Provide overall assessment:
   - Does peer activity suggest public information was driving trades?
   - Or does the flagged trade stand out as uniquely informed?

**Peer Trading Data:**
{raw_data if raw_data.strip() else f"No peer trading data found for {symbol} in this date range."}

**Peer Activity Analysis:**"""
