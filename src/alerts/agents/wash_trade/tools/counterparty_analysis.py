"""Counterparty Analysis Tool for wash trade analysis.

This tool maps trade flows and detects circular patterns that
are indicative of wash trading schemes.

Uses proactive information flow pattern where data is injected via execute().
"""

import json
import logging
from typing import Any, Dict, List

from alerts.tools.common.base import BaseTool

logger = logging.getLogger(__name__)


class CounterpartyAnalysisTool(BaseTool):
    """Tool to map trade flow and detect circular patterns.

    This tool receives trade flow data via execute() and uses the LLM to
    analyze patterns indicative of wash trading:
    - DIRECT_WASH: A -> B where A and B have same beneficial owner
    - LAYERED_WASH: A -> B -> C -> A (circular pattern)
    - INTERMEDIARY_WASH: A -> X -> B where X is unrelated intermediary

    Uses proactive information flow pattern where data is injected
    from the Big Data Layer.

    Data Sources (expected in injected data):
    - Trade data from alert and history
    - Account relationships for beneficial owner mapping
    """

    # Expected format for execute() method
    expected_format: str = "csv"

    def __init__(self, llm: Any, data_dir: str) -> None:
        """Initialize the CounterpartyAnalysisTool.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to the data directory
        """
        super().__init__(
            llm=llm,
            name="counterparty_analysis",
            description=(
                "Map trade flow and detect circular trading patterns. "
                "Use this tool to identify wash trade patterns: DIRECT_WASH "
                "(same owner both sides), LAYERED_WASH (circular A->B->C->A), "
                "or INTERMEDIARY_WASH (using unrelated intermediary). "
                "Returns pattern classification with confidence level."
            ),
        )
        self.data_dir = data_dir
        self.logger.info(f"CounterpartyAnalysisTool initialized with data_dir: {data_dir}")

    def _parse_trades(self, trades: Any) -> List[Dict]:
        """Parse trades from various input formats.

        Args:
            trades: List of trade dicts or JSON string

        Returns:
            List of trade dictionaries
        """
        if isinstance(trades, str):
            try:
                return json.loads(trades)
            except json.JSONDecodeError:
                self.logger.warning("Failed to parse trades JSON, treating as description")
                return [{"description": trades}]
        return list(trades) if trades else []

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM interpretation of counterparty analysis.

        Args:
            raw_data: Analysis data with trade flow and ownership info
            **kwargs: Trade parameters

        Returns:
            Prompt for LLM interpretation
        """
        prompt = f"""You are analyzing trade counterparty relationships for wash trade detection.

## Task
Analyze the trade flow and beneficial ownership to classify the wash trade pattern.

## Trade and Ownership Data
{raw_data}

## Analysis Requirements
1. **Trade Flow Mapping**: Understand how trades flow between accounts
2. **Beneficial Ownership Verification**: Confirm if same owner controls multiple accounts
3. **Pattern Classification**: Determine the wash trade pattern type
4. **Economic Purpose Assessment**: Identify any legitimate business purpose

## Wash Trade Pattern Indicators

### DIRECT_WASH (Highest Risk)
- Two accounts with identical beneficial owner trade with each other
- No intermediary, clear self-dealing
- Example: Family trust sells to holding company, both owned by same person

### LAYERED_WASH (High Risk)
- Multiple accounts create circular flow (A->B->C->A)
- All accounts controlled by same beneficial owner
- Designed to create artificial volume while shares return to origin
- Example: Three companies, all controlled by same shareholder, pass shares around

### INTERMEDIARY_WASH (Medium Risk)
- Uses unrelated intermediary to obscure relationship
- A sells to X, X sells to B, where A and B share owner but X doesn't
- Harder to detect but still manipulative

### NO_PATTERN (Lower Risk)
- Accounts have genuinely different beneficial owners
- No circular flow
- Could still be suspicious but less clear-cut

## Output Format
Provide a concise analysis (2-3 paragraphs) covering:
1. The specific trade flow and how accounts are connected
2. Beneficial ownership analysis - who really controls these accounts?
3. Pattern classification with confidence level (HIGH/MEDIUM/LOW)
4. Any legitimate economic purpose that could explain the trades
5. Final assessment: Is this wash trading? Why or why not?

Be specific about account IDs, beneficial owner names, and trade details."""

        return prompt
