"""Trader profile tool for SMARTS Alert Analyzer.

This tool analyzes trader profile information to assess their role,
access level, and any trading restrictions. This is a shared tool
used by multiple agent types.

In Proactive Info Flow mode, CSV content is injected via execute(data=...).
"""

import logging
from pathlib import Path
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin, DataFormat

logger = logging.getLogger(__name__)


class TraderProfileTool(BaseTool, DataLoadingMixin):
    """Tool to analyze trader profile information.

    This tool takes CSV data (injected in Proactive Info Flow mode)
    containing trader profiles and uses the LLM to assess their potential
    access to material non-public information.

    Expected format: csv
    """

    # Expected data format for this tool
    expected_format: DataFormat = "csv"

    def __init__(self, llm: Any, data_dir: Path | None = None) -> None:
        """Initialize the trader profile tool.

        Args:
            llm: LangChain LLM instance
            data_dir: DEPRECATED - kept for backward compatibility only
        """
        super().__init__(
            llm=llm,
            name="query_trader_profile",
            description=(
                "Analyze a trader's profile including role, department, access level, and restrictions. "
                "Returns LLM-interpreted assessment of the trader's potential access to "
                "material non-public information and whether their role permits trading."
            ),
            expected_format="csv"
        )
        # Keep data_dir for backward compatibility but log deprecation
        if data_dir is not None:
            self.data_dir = data_dir
            self.profiles_file = data_dir / "trader_profiles.csv"
            self.logger.warning(
                "data_dir parameter is deprecated. In Proactive Info Flow mode, "
                "data is injected via execute(data=...)."
            )
        else:
            self.data_dir = None
            self.profiles_file = None

        self.logger.info("Trader profile tool initialized (Proactive Info Flow mode)")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        In Proactive Info Flow mode, data is injected directly.
        Optional trader_id can be provided for filtering/context.

        Args:
            **kwargs: Optional 'trader_id' for context

        Returns:
            Error message if invalid, None if valid
        """
        # No validation needed in Proactive Info Flow mode
        # Data validation is handled by execute()
        return None

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret trader's profile.

        Args:
            raw_data: Profile CSV content
            **kwargs: Optional 'trader_id' for context

        Returns:
            Interpretation prompt
        """
        trader_id = kwargs.get("trader_id", "the flagged trader")

        return f"""You are a compliance analyst reviewing a trader's profile for insider trading investigation.

Analyze the following profile information for {trader_id}.

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
