"""Trader profile tool for SMARTS Alert Analyzer.

This tool queries trader profile information to assess their role,
access level, and any trading restrictions.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from alerts.tools.base import BaseTool, DataLoadingMixin

logger = logging.getLogger(__name__)


class TraderProfileTool(BaseTool, DataLoadingMixin):
    """Tool to query and analyze trader profile information.

    This tool retrieves trader's role, department, access level,
    and restrictions, using the LLM to assess their potential
    access to material non-public information.
    """

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

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        Args:
            **kwargs: Must contain 'trader_id'

        Returns:
            Error message if invalid, None if valid
        """
        if not kwargs.get("trader_id"):
            return "trader_id is required"

        if not self.profiles_file.exists():
            return f"Trader profiles file not found: {self.profiles_file}"

        return None

    def _load_data(self, **kwargs: Any) -> str:
        """Load trader's profile data.

        Args:
            **kwargs: Must contain 'trader_id'

        Returns:
            Profile data for the trader
        """
        trader_id = kwargs["trader_id"]

        self.logger.info(f"Loading profile for trader {trader_id}")

        # Load full CSV
        csv_content = self.load_csv_as_string(str(self.profiles_file))

        # Filter for this trader
        trader_data = self.filter_csv_by_column(csv_content, "trader_id", trader_id)

        self.logger.debug(f"Profile data: {trader_data}")

        return trader_data

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret trader's profile.

        Args:
            raw_data: Profile CSV content
            **kwargs: Contains 'trader_id'

        Returns:
            Interpretation prompt
        """
        trader_id = kwargs["trader_id"]

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
