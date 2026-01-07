"""Account Relationships Tool for wash trade analysis.

This tool analyzes beneficial ownership data and finds linked accounts
to identify potential wash trading relationships.

In Proactive Info Flow mode, CSV content is injected via execute(data=...).
"""

import logging
from pathlib import Path
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin, DataFormat

logger = logging.getLogger(__name__)


class AccountRelationshipsTool(BaseTool, DataLoadingMixin):
    """Tool to analyze beneficial ownership and find linked accounts.

    This tool takes CSV data (injected in Proactive Info Flow mode)
    containing account relationships and uses the LLM to identify
    relationships and potential wash trading risk based on
    beneficial ownership patterns.

    Expected format: csv

    CSV Fields (expected by Big Data Layer):
        - account_id: Account identifier
        - beneficial_owner_id: ID of the beneficial owner
        - beneficial_owner_name: Name of the beneficial owner
        - relationship_type: Type of ownership (direct, family_trust, corporate, etc.)
        - linked_accounts: JSON array of related account IDs
        - relationship_degree: 1 = direct, 2 = through intermediary
    """

    # Expected data format for this tool
    expected_format: DataFormat = "csv"

    def __init__(self, llm: Any, data_dir: str | Path | None = None) -> None:
        """Initialize the AccountRelationshipsTool.

        Args:
            llm: LangChain LLM instance
            data_dir: DEPRECATED - kept for backward compatibility only
        """
        super().__init__(
            llm=llm,
            name="account_relationships",
            description=(
                "Analyze beneficial ownership information and find linked accounts. "
                "Identifies relationships between accounts and determines if the same "
                "beneficial owner controls multiple accounts involved in trades. "
                "Returns relationship analysis and linked accounts."
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

        self.logger.info("AccountRelationshipsTool initialized (Proactive Info Flow mode)")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        In Proactive Info Flow mode, data is injected directly.
        Optional account_ids can be provided for context.

        Args:
            **kwargs: Optional parameters for context

        Returns:
            Error message if invalid, None if valid
        """
        # No validation needed in Proactive Info Flow mode
        # Data validation is handled by execute()
        return None

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM interpretation of relationship data.

        Args:
            raw_data: CSV content with relationship data
            **kwargs: Optional 'account_ids' for context

        Returns:
            Prompt for LLM interpretation
        """
        # Get account_ids if provided for context
        account_ids_str = kwargs.get("account_ids") or kwargs.get("account_id", "")
        if account_ids_str:
            account_ids = [aid.strip() for aid in account_ids_str.split(",")]
            accounts_display = ", ".join(account_ids)
        else:
            accounts_display = "the flagged accounts"

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


def create_account_relationships_tool(llm: Any, data_dir: str) -> dict:
    """Create LangChain-compatible tool for account relationships lookup.

    Args:
        llm: LangChain LLM instance
        data_dir: Path to data directory

    Returns:
        Dictionary with tool function and metadata
    """
    tool = AccountRelationshipsTool(llm, data_dir)

    def account_relationships_func(account_ids: str) -> str:
        """Query beneficial ownership and find linked accounts.

        Args:
            account_ids: Comma-separated list of account IDs to look up relationships for

        Returns:
            Analysis of beneficial ownership and related accounts
        """
        return tool(account_ids=account_ids)

    return {
        "func": account_relationships_func,
        "name": tool.name,
        "description": tool.description,
        "tool_instance": tool,
    }
