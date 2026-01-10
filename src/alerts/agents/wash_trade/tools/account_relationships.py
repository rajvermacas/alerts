"""Account Relationships Tool for wash trade analysis.

This tool analyzes beneficial ownership data and finds linked accounts
to identify potential wash trading relationships.

Uses proactive information flow pattern where data is injected via execute().
"""

import logging
from typing import Any

from alerts.tools.common.base import BaseTool

logger = logging.getLogger(__name__)


class AccountRelationshipsTool(BaseTool):
    """Tool to analyze beneficial ownership and find linked accounts.

    This tool receives account relationships data via execute() and uses the LLM
    to identify potential wash trading risk based on beneficial ownership patterns.

    Analysis includes:
    - Beneficial owner information for accounts
    - Related/linked accounts under the same beneficial owner
    - Relationship types (direct, family trust, corporate, nominee, etc.)
    - Relationship degrees (1st degree = direct, 2nd = through intermediary)

    Uses proactive information flow pattern where data is injected
    from the Big Data Layer.

    CSV Fields (expected in injected data):
        - account_id: Account identifier
        - beneficial_owner_id: ID of the beneficial owner
        - beneficial_owner_name: Name of the beneficial owner
        - relationship_type: Type of ownership (direct, family_trust, corporate, etc.)
        - linked_accounts: JSON array of related account IDs
        - relationship_degree: 1 = direct, 2 = through intermediary
    """

    # Expected format for execute() method
    expected_format: str = "csv"

    def __init__(self, llm: Any, data_dir: str) -> None:
        """Initialize the AccountRelationshipsTool.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to the data directory containing wash_trade subdirectory
        """
        super().__init__(
            llm=llm,
            name="account_relationships",
            description=(
                "Query beneficial ownership information and find linked accounts. "
                "Use this tool to identify relationships between accounts and "
                "determine if the same beneficial owner controls multiple accounts "
                "involved in trades. Returns relationship analysis and linked accounts."
            ),
        )
        self.data_dir = data_dir
        self.logger.info(f"AccountRelationshipsTool initialized with data_dir: {data_dir}")

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM interpretation of relationship data.

        Args:
            raw_data: Filtered CSV content with relationship data
            **kwargs: May include 'account_ids' for context

        Returns:
            Prompt for LLM interpretation
        """
        account_ids_str = kwargs.get("account_ids") or kwargs.get("account_id") or ""
        account_ids = [aid.strip() for aid in account_ids_str.split(",") if aid.strip()] if account_ids_str else []
        accounts_display = ", ".join(account_ids) if account_ids else "provided accounts"

        prompt = f"""You are analyzing account relationship data for potential wash trade detection.

## Task
Analyze the relationship data for accounts {accounts_display} and their linked accounts.
Identify beneficial ownership patterns that could indicate wash trading risk.

## Account Relationship Data
```csv
{raw_data}
```

## Analysis Requirements
1. **Beneficial Ownership**: Identify who controls each account
2. **Linked Accounts**: List all accounts sharing beneficial ownership
3. **Relationship Types**: Describe the type of each relationship
4. **Risk Assessment**: Assess wash trade risk based on ownership structure

## Wash Trade Risk Indicators
- Same beneficial owner controlling multiple trading accounts
- Family trust or corporate structures that obscure ownership
- Nominee arrangements that may mask true ownership
- Complex relationship chains (degree > 1)

## Output Format
Provide a concise analysis (2-3 paragraphs) covering:
1. Who the beneficial owner(s) are and what accounts they control
2. The relationship structure (direct ownership, trust, corporate, etc.)
3. Wash trade risk level (HIGH, MEDIUM, LOW) with reasoning

Be specific about account IDs and beneficial owner names from the data.
Focus on information relevant to wash trade detection."""

        return prompt
