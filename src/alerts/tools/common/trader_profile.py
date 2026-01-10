"""Trader profile tool for SMARTS Alert Analyzer.

This tool analyzes trader profile information to assess their role,
access level, and any trading restrictions. This is a shared tool
used by multiple agent types.

Uses proactive information flow pattern where data is injected via execute().
"""

import logging
from pathlib import Path
from typing import Any

from alerts.tools.common.base import BaseTool

logger = logging.getLogger(__name__)


class TraderProfileTool(BaseTool):
    """Tool to analyze trader profile information.

    This tool receives trader profile data via execute() and uses the LLM
    to assess their potential access to material non-public information.

    Uses proactive information flow pattern where data is injected
    from the Big Data Layer.
    """

    # Expected format for execute() method
    expected_format: str = "csv"

    def __init__(self, llm: Any, data_dir: Path) -> None:
        """Initialize the trader profile tool.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to data directory
        """
        super().__init__(
            llm=llm,
            name="query_trader_profile",
            description=(
                "Query a trader's profile including role, department, access level, and restrictions. "
                "Input: trader_id. "
                "Returns LLM-interpreted assessment of the trader's potential access to "
                "material non-public information and whether their role permits trading."
            )
        )
        self.data_dir = data_dir
        self.profiles_file = data_dir / "trader_profiles.csv"
        self.logger.info(f"Trader profile tool initialized with file: {self.profiles_file}")

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret trader's profile.

        Args:
            raw_data: Profile CSV content
            **kwargs: Contains 'trader_id'

        Returns:
            Interpretation prompt
        """
        trader_id = kwargs.get("trader_id", "unknown")

        return f"""You are a compliance analyst reviewing a trader's profile for insider trading investigation.

Analyze the following profile information for trader {trader_id}.

**Role Definitions:**
- PORTFOLIO_MANAGER: High information access, manages portfolios, regular exposure to market-moving information
- RESEARCH_ANALYST: Medium access, sector-specific research, some MNPI exposure through coverage
- TRADER: Low access, execution only, limited information access
- COMPLIANCE: No trading allowed, sees alerts but no deal information
- BACK_OFFICE: Operations role, no information access, no trading allowed

**Your Task:**
1. Assess the trader's potential ACCESS to material non-public information based on their role
2. Evaluate whether their trading is PERMITTED based on their role and restrictions
3. Identify any RED FLAGS (e.g., back-office employee trading, compliance staff trading)
4. Provide an overall risk assessment of this trader profile in context of insider trading

**Profile Data:**
{raw_data if raw_data.strip() else f"No profile found for trader {trader_id}."}

**Profile Assessment:**"""
