"""Account Relationships Tool for wash trade analysis.

This tool queries beneficial ownership data and finds linked accounts
to identify potential wash trading relationships.
"""

import json
import logging
import os
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin

logger = logging.getLogger(__name__)


class AccountRelationshipsTool(BaseTool, DataLoadingMixin):
    """Tool to query beneficial ownership and find linked accounts.

    This tool queries the account relationships database to find:
    - Beneficial owner information for an account
    - Related/linked accounts under the same beneficial owner
    - Relationship types (direct, family trust, corporate, nominee, etc.)
    - Relationship degrees (1st degree = direct, 2nd = through intermediary)

    The tool uses an LLM to interpret the relationships and identify
    potential wash trading risk based on beneficial ownership patterns.

    Data Source: test_data/wash_trade/account_relationships.csv

    CSV Fields:
        - account_id: Account identifier
        - beneficial_owner_id: ID of the beneficial owner
        - beneficial_owner_name: Name of the beneficial owner
        - relationship_type: Type of ownership (direct, family_trust, corporate, etc.)
        - linked_accounts: JSON array of related account IDs
        - relationship_degree: 1 = direct, 2 = through intermediary
    """

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
        self.csv_path = os.path.join(
            data_dir, "wash_trade", "account_relationships.csv"
        )
        self.logger.info(f"AccountRelationshipsTool initialized with data_dir: {data_dir}")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        Args:
            **kwargs: Must include 'account_ids' (comma-separated list or single ID)

        Returns:
            Error message if invalid, None if valid
        """
        # Support both 'account_ids' (new) and 'account_id' (legacy) for backward compatibility
        account_ids = kwargs.get("account_ids") or kwargs.get("account_id")
        if not account_ids:
            return "account_ids is required"

        if not isinstance(account_ids, str):
            return "account_ids must be a non-empty string"

        return None

    def _load_data(self, **kwargs: Any) -> str:
        """Load account relationship data from CSV.

        Args:
            **kwargs: Must include 'account_ids' (comma-separated list or single ID)

        Returns:
            Filtered CSV content for the accounts and their related accounts

        Raises:
            FileNotFoundError: If CSV file doesn't exist
        """
        # Support both 'account_ids' (new) and 'account_id' (legacy) for backward compatibility
        account_ids_str = kwargs.get("account_ids") or kwargs.get("account_id")
        # Parse comma-separated list of account IDs
        requested_account_ids = [aid.strip() for aid in account_ids_str.split(",")]
        self.logger.info(f"Loading relationship data for accounts: {requested_account_ids}")

        # Load full CSV
        csv_content = self.load_csv_as_string(self.csv_path)

        # Parse CSV to find account and all related accounts
        lines = csv_content.strip().split("\n")
        header = lines[0]
        columns = header.split(",")

        # Find column indices
        try:
            account_idx = columns.index("account_id")
            linked_accounts_idx = columns.index("linked_accounts")
        except ValueError as e:
            self.logger.error(f"Required column not found: {e}")
            raise ValueError(f"Invalid CSV format: {e}")

        # Find all requested accounts and collect all related account IDs
        related_account_ids = set(requested_account_ids)
        relevant_rows = [header]

        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) <= max(account_idx, linked_accounts_idx):
                continue

            row_account_id = parts[account_idx]

            if row_account_id in requested_account_ids:
                relevant_rows.append(line)
                # Parse linked accounts (JSON array format)
                try:
                    linked_str = parts[linked_accounts_idx].strip('"')
                    # Handle JSON array format: ["ACC-002","ACC-003"]
                    if linked_str.startswith("["):
                        linked = json.loads(linked_str.replace("'", '"'))
                        related_account_ids.update(linked)
                except (json.JSONDecodeError, IndexError):
                    self.logger.warning(f"Could not parse linked_accounts for {row_account_id}")

        # Now also get rows for all related accounts
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) <= account_idx:
                continue

            row_account_id = parts[account_idx]
            if row_account_id in related_account_ids and line not in relevant_rows:
                relevant_rows.append(line)

        filtered_csv = "\n".join(relevant_rows)
        self.logger.debug(f"Found {len(relevant_rows) - 1} related account records")

        return filtered_csv

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM interpretation of relationship data.

        Args:
            raw_data: Filtered CSV content with relationship data
            **kwargs: Must include 'account_ids' (comma-separated list or single ID)

        Returns:
            Prompt for LLM interpretation
        """
        # Support both 'account_ids' (new) and 'account_id' (legacy) for backward compatibility
        account_ids_str = kwargs.get("account_ids") or kwargs.get("account_id")
        account_ids = [aid.strip() for aid in account_ids_str.split(",")]
        accounts_display = ", ".join(account_ids)

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
