"""Trade Timing Tool for wash trade analysis.

This tool analyzes temporal patterns of flagged trades to identify
pre-arranged execution indicative of wash trading.
"""

import logging
import os
from datetime import datetime
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin

logger = logging.getLogger(__name__)


class TradeTimingTool(BaseTool, DataLoadingMixin):
    """Tool to analyze temporal patterns of flagged trades.

    This tool examines the timing of trades to determine if they appear
    to be pre-arranged or coordinated, which is a key indicator of wash trading.

    The tool analyzes:
    - Time delta between trades (sub-second is highly suspicious)
    - Market phase (opening, regular session, closing, after-hours)
    - Liquidity assessment at the time of trades
    - Comparison to normal execution times for similar volumes

    Data Source: Computed from alert data + test_data/market_data.csv for context
    """

    def __init__(self, llm: Any, data_dir: str) -> None:
        """Initialize the TradeTimingTool.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to the data directory
        """
        super().__init__(
            llm=llm,
            name="trade_timing",
            description=(
                "Analyze temporal patterns of flagged trades. "
                "Use this tool to assess if trades appear to be pre-arranged "
                "based on timing. Examines time delta between trades, market phase, "
                "and liquidity conditions. Sub-second execution is highly suspicious."
            ),
        )
        self.data_dir = data_dir
        self.market_data_path = os.path.join(data_dir, "market_data.csv")
        self.logger.info(f"TradeTimingTool initialized with data_dir: {data_dir}")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        Args:
            **kwargs: Must include 'trade1_timestamp' and 'trade2_timestamp',
                     optionally 'symbol' and 'trade_quantity'

        Returns:
            Error message if invalid, None if valid
        """
        if "trade1_timestamp" not in kwargs:
            return "trade1_timestamp is required"
        if "trade2_timestamp" not in kwargs:
            return "trade2_timestamp is required"

        return None

    def _parse_timestamp(self, ts: str) -> Optional[datetime]:
        """Parse timestamp string to datetime.

        Args:
            ts: Timestamp string in various formats

        Returns:
            datetime object or None if parsing fails
        """
        formats = [
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%H:%M:%S.%f",
            "%H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(ts, fmt)
            except ValueError:
                continue

        return None

    def _calculate_time_delta_ms(self, ts1: str, ts2: str) -> Optional[int]:
        """Calculate time delta in milliseconds between two timestamps.

        Args:
            ts1: First timestamp string
            ts2: Second timestamp string

        Returns:
            Time delta in milliseconds, or None if parsing fails
        """
        dt1 = self._parse_timestamp(ts1)
        dt2 = self._parse_timestamp(ts2)

        if dt1 is None or dt2 is None:
            return None

        delta = abs((dt2 - dt1).total_seconds() * 1000)
        return int(delta)

    def _determine_market_phase(self, timestamp: str) -> str:
        """Determine market phase from timestamp.

        Args:
            timestamp: Trade timestamp string

        Returns:
            Market phase description
        """
        dt = self._parse_timestamp(timestamp)
        if dt is None:
            return "unknown"

        hour = dt.hour
        minute = dt.minute

        if hour < 9 or (hour == 9 and minute < 30):
            return "pre_market"
        elif hour == 9 and minute < 45:
            return "opening_auction"
        elif hour < 15 or (hour == 15 and minute < 45):
            return "regular_session"
        elif hour == 15 and minute >= 45:
            return "closing_auction"
        elif hour < 18:
            return "after_hours"
        else:
            return "after_hours"

    def _assess_liquidity(self, timestamp: str) -> str:
        """Assess market liquidity at given time.

        Args:
            timestamp: Trade timestamp string

        Returns:
            Liquidity assessment (high, medium, low, very_low)
        """
        dt = self._parse_timestamp(timestamp)
        if dt is None:
            return "unknown"

        hour = dt.hour

        # Opening and closing typically highest liquidity
        if hour == 9 or hour == 15:
            return "high"
        # Mid-morning typically good liquidity
        elif 10 <= hour <= 11:
            return "medium"
        # Lunch lull - lower liquidity
        elif 12 <= hour <= 13:
            return "low"
        # Early afternoon - moderate
        elif 14 <= hour < 15:
            return "medium"
        # Pre-market and after-hours
        else:
            return "very_low"

    def _load_data(self, **kwargs: Any) -> str:
        """Load timing data and market context.

        Args:
            **kwargs: Must include timestamps, optionally symbol

        Returns:
            Formatted timing analysis data
        """
        trade1_ts = kwargs.get("trade1_timestamp", "")
        trade2_ts = kwargs.get("trade2_timestamp", "")
        symbol = kwargs.get("symbol", "UNKNOWN")
        quantity = kwargs.get("trade_quantity", "Unknown")

        self.logger.info(f"Analyzing timing for trades: {trade1_ts} and {trade2_ts}")

        # Calculate time delta
        delta_ms = self._calculate_time_delta_ms(trade1_ts, trade2_ts)
        delta_str = f"{delta_ms}ms" if delta_ms else "Unable to calculate"

        # Determine market phases
        phase1 = self._determine_market_phase(trade1_ts)
        phase2 = self._determine_market_phase(trade2_ts)

        # Assess liquidity
        liquidity1 = self._assess_liquidity(trade1_ts)
        liquidity2 = self._assess_liquidity(trade2_ts)

        # Try to load market data for additional context
        market_context = ""
        try:
            market_data = self.load_csv_as_string(self.market_data_path)
            # Filter for the symbol if possible
            lines = market_data.strip().split("\n")
            relevant_lines = [lines[0]]  # Header
            for line in lines[1:]:
                if symbol in line:
                    relevant_lines.append(line)
            if len(relevant_lines) > 1:
                market_context = "\n".join(relevant_lines[:10])  # Limit to 10 rows
        except FileNotFoundError:
            market_context = "Market data not available"

        # Format output data
        data = f"""## Timing Analysis Data

### Trade Timestamps
- Trade 1: {trade1_ts}
- Trade 2: {trade2_ts}
- Symbol: {symbol}
- Quantity: {quantity}

### Calculated Metrics
- Time Delta: {delta_str}
- Delta (readable): {self._format_delta_readable(delta_ms)}

### Market Phase Analysis
- Trade 1 Phase: {phase1}
- Trade 2 Phase: {phase2}

### Liquidity Assessment
- Trade 1 Liquidity: {liquidity1}
- Trade 2 Liquidity: {liquidity2}

### Normal Execution Benchmarks
- Normal execution for 1K-5K shares: 1-5 seconds
- Normal execution for 5K-10K shares: 5-15 seconds
- Normal execution for 10K+ shares: 15-60 seconds
- Sub-second execution: Highly unusual, suggests pre-arrangement

### Market Data Context
{market_context if market_context else "Not available"}
"""
        return data

    def _format_delta_readable(self, delta_ms: Optional[int]) -> str:
        """Format time delta as readable string.

        Args:
            delta_ms: Time delta in milliseconds

        Returns:
            Human-readable time delta string
        """
        if delta_ms is None:
            return "Unknown"

        if delta_ms < 1000:
            return f"{delta_ms} milliseconds"
        elif delta_ms < 60000:
            seconds = delta_ms / 1000
            return f"{seconds:.1f} seconds"
        elif delta_ms < 3600000:
            minutes = delta_ms / 60000
            return f"{minutes:.1f} minutes"
        else:
            hours = delta_ms / 3600000
            return f"{hours:.1f} hours"

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM interpretation of timing data.

        Args:
            raw_data: Timing analysis data
            **kwargs: Trade parameters

        Returns:
            Prompt for LLM interpretation
        """
        trade1_ts = kwargs.get("trade1_timestamp", "")
        trade2_ts = kwargs.get("trade2_timestamp", "")

        prompt = f"""You are analyzing trade timing patterns for potential wash trade detection.

## Task
Analyze the temporal patterns of two trades to determine if they appear pre-arranged.

{raw_data}

## Analysis Requirements
1. **Time Delta Assessment**: Evaluate if the time between trades is suspicious
   - Sub-second (< 1000ms): HIGHLY SUSPICIOUS - suggests pre-arranged execution
   - 1-10 seconds: SUSPICIOUS - faster than typical retail execution
   - 10-60 seconds: MODERATE - could be coordinated or coincidental
   - > 60 seconds: LOWER RISK - more likely to be independent trades

2. **Market Phase Analysis**: Consider when the trades occurred
   - Opening/closing: Higher volume, easier to hide wash trades
   - Mid-day lull: Lower liquidity, wash trades more visible
   - After-hours: Very suspicious for retail accounts

3. **Liquidity Context**: Consider if timing exploits low liquidity periods
   - Low liquidity periods make wash trades more impactful on volume metrics

4. **Pre-Arrangement Indicators**:
   - Identical or near-identical timestamps
   - Execution during low-liquidity periods
   - Timing patterns inconsistent with human reaction time
   - Execution faster than typical order routing would allow

## Output Format
Provide a concise analysis (2-3 paragraphs) covering:
1. The specific time delta and what it suggests about coordination
2. Market phase and liquidity conditions assessment
3. Overall pre-arrangement probability: HIGH (>80%), MEDIUM (40-80%), LOW (<40%)
4. Key timing red flags identified

Be specific about timestamps and calculated values."""

        return prompt


def create_trade_timing_tool(llm: Any, data_dir: str) -> dict:
    """Create LangChain-compatible tool for trade timing analysis.

    Args:
        llm: LangChain LLM instance
        data_dir: Path to data directory

    Returns:
        Dictionary with tool function and metadata
    """
    tool = TradeTimingTool(llm, data_dir)

    def trade_timing_func(
        trade1_timestamp: str,
        trade2_timestamp: str,
        symbol: Optional[str] = None,
        trade_quantity: Optional[str] = None
    ) -> str:
        """Analyze temporal patterns of flagged trades.

        Args:
            trade1_timestamp: Timestamp of first trade (e.g., "14:32:15.123")
            trade2_timestamp: Timestamp of second trade (e.g., "14:32:15.625")
            symbol: Optional trading symbol
            trade_quantity: Optional quantity for execution time benchmarking

        Returns:
            Analysis of timing patterns and pre-arrangement probability
        """
        return tool(
            trade1_timestamp=trade1_timestamp,
            trade2_timestamp=trade2_timestamp,
            symbol=symbol,
            trade_quantity=trade_quantity
        )

    return {
        "func": trade_timing_func,
        "name": tool.name,
        "description": tool.description,
        "tool_instance": tool,
    }
