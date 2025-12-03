"""Counterparty Analysis Tool for wash trade analysis.

This tool maps trade flows and detects circular patterns that
are indicative of wash trading schemes.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin

logger = logging.getLogger(__name__)


class CounterpartyAnalysisTool(BaseTool, DataLoadingMixin):
    """Tool to map trade flow and detect circular patterns.

    This tool analyzes the flow of trades between accounts to detect
    patterns indicative of wash trading:
    - DIRECT_WASH: A -> B where A and B have same beneficial owner
    - LAYERED_WASH: A -> B -> C -> A (circular pattern)
    - INTERMEDIARY_WASH: A -> X -> B where X is unrelated intermediary

    The tool builds a trade flow graph and identifies suspicious patterns.

    Data Sources:
    - Trade data from alert and history
    - Account relationships for beneficial owner mapping
    """

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
        self.relationships_path = os.path.join(
            data_dir, "wash_trade", "account_relationships.csv"
        )
        self.history_path = os.path.join(
            data_dir, "wash_trade", "related_accounts_history.csv"
        )
        self.logger.info(f"CounterpartyAnalysisTool initialized with data_dir: {data_dir}")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        Args:
            **kwargs: Must include 'trades' (list of trade dicts)

        Returns:
            Error message if invalid, None if valid
        """
        if "trades" not in kwargs:
            return "trades parameter is required"

        trades = kwargs.get("trades")
        if not trades:
            return "trades must be a non-empty list or JSON string"

        return None

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

    def _load_beneficial_owner_map(self) -> Dict[str, Dict]:
        """Load beneficial owner mapping from relationships CSV.

        Returns:
            Dict mapping account_id to owner info
        """
        owner_map = {}

        try:
            csv_content = self.load_csv_as_string(self.relationships_path)
            lines = csv_content.strip().split("\n")
            header = lines[0].split(",")

            # Find column indices
            account_idx = header.index("account_id")
            owner_id_idx = header.index("beneficial_owner_id")
            owner_name_idx = header.index("beneficial_owner_name")
            rel_type_idx = header.index("relationship_type")

            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) <= max(account_idx, owner_id_idx, owner_name_idx, rel_type_idx):
                    continue

                account_id = parts[account_idx]
                owner_map[account_id] = {
                    "beneficial_owner_id": parts[owner_id_idx],
                    "beneficial_owner_name": parts[owner_name_idx],
                    "relationship_type": parts[rel_type_idx],
                }

        except (FileNotFoundError, ValueError) as e:
            self.logger.warning(f"Could not load beneficial owner map: {e}")

        return owner_map

    def _detect_pattern_type(
        self,
        trades: List[Dict],
        owner_map: Dict[str, Dict]
    ) -> Dict:
        """Detect the type of wash trade pattern.

        Args:
            trades: List of trade dictionaries
            owner_map: Mapping of accounts to beneficial owners

        Returns:
            Dict with pattern_type, confidence, and analysis
        """
        if len(trades) < 2:
            return {
                "pattern_type": "INSUFFICIENT_DATA",
                "confidence": 0,
                "analysis": "Need at least 2 trades to analyze pattern"
            }

        # Extract accounts from trades
        accounts_in_trades = set()
        trade_flow = []

        for trade in trades:
            account = trade.get("account_id") or trade.get("account")
            counterparty = trade.get("counterparty_account") or trade.get("counterparty")
            if account:
                accounts_in_trades.add(account)
            if counterparty:
                accounts_in_trades.add(counterparty)
                trade_flow.append((account, counterparty))

        # Get beneficial owners for all accounts
        owners = {}
        for account in accounts_in_trades:
            if account in owner_map:
                owners[account] = owner_map[account]["beneficial_owner_id"]

        # Check for same beneficial owner (DIRECT_WASH)
        unique_owners = set(owners.values())
        if len(unique_owners) == 1 and len(accounts_in_trades) >= 2:
            return {
                "pattern_type": "DIRECT_WASH",
                "confidence": 95,
                "analysis": (
                    f"All accounts ({', '.join(accounts_in_trades)}) share the same "
                    f"beneficial owner ({list(unique_owners)[0]}). This is a direct wash trade pattern."
                )
            }

        # Check for circular pattern (LAYERED_WASH)
        # Build adjacency for cycle detection
        if len(trade_flow) >= 3:
            # Simple cycle detection: check if any account appears as both source and destination
            sources = [t[0] for t in trade_flow if t[0]]
            destinations = [t[1] for t in trade_flow if t[1]]

            cycle_accounts = set(sources) & set(destinations)
            if cycle_accounts:
                # Check if cycle accounts share beneficial owner
                cycle_owners = {owners.get(acc) for acc in cycle_accounts if acc in owners}
                if len(cycle_owners) == 1:
                    return {
                        "pattern_type": "LAYERED_WASH",
                        "confidence": 90,
                        "analysis": (
                            f"Circular trade pattern detected involving accounts: "
                            f"{', '.join(cycle_accounts)}. All controlled by same beneficial owner."
                        )
                    }

        # Check for intermediary pattern (INTERMEDIARY_WASH)
        if len(trade_flow) >= 2:
            # Look for A -> X -> B where A and B share owner but X doesn't
            intermediary_accounts = set()
            related_accounts = set()

            for account, owner_id in owners.items():
                owner_count = sum(1 for o in owners.values() if o == owner_id)
                if owner_count >= 2:
                    related_accounts.add(account)
                else:
                    intermediary_accounts.add(account)

            if intermediary_accounts and len(related_accounts) >= 2:
                return {
                    "pattern_type": "INTERMEDIARY_WASH",
                    "confidence": 75,
                    "analysis": (
                        f"Potential intermediary wash pattern. Related accounts: "
                        f"{', '.join(related_accounts)} may be trading through "
                        f"intermediary: {', '.join(intermediary_accounts)}"
                    )
                }

        # No clear pattern detected
        return {
            "pattern_type": "NO_PATTERN",
            "confidence": 20,
            "analysis": (
                "No clear wash trade pattern detected. Accounts have different "
                "beneficial owners and no circular flow identified."
            )
        }

    def _load_data(self, **kwargs: Any) -> str:
        """Load and analyze trade flow data.

        Args:
            **kwargs: Must include 'trades'

        Returns:
            Formatted analysis data
        """
        trades = self._parse_trades(kwargs.get("trades", []))

        self.logger.info(f"Analyzing counterparty patterns for {len(trades)} trades")

        # Load beneficial owner mapping
        owner_map = self._load_beneficial_owner_map()

        # Detect pattern
        pattern_result = self._detect_pattern_type(trades, owner_map)

        # Format trade flow for display
        trade_flow_str = ""
        for i, trade in enumerate(trades, 1):
            account = trade.get("account_id") or trade.get("account", "Unknown")
            counterparty = trade.get("counterparty_account") or trade.get("counterparty", "Unknown")
            side = trade.get("side", "Unknown")
            quantity = trade.get("quantity", "Unknown")
            price = trade.get("price", "Unknown")
            symbol = trade.get("symbol", "Unknown")

            trade_flow_str += f"""
Trade {i}:
  - Account: {account}
  - Side: {side}
  - Symbol: {symbol}
  - Quantity: {quantity}
  - Price: {price}
  - Counterparty: {counterparty}
"""

        # Format beneficial owner info
        accounts_in_trades = set()
        for trade in trades:
            acc = trade.get("account_id") or trade.get("account")
            cp = trade.get("counterparty_account") or trade.get("counterparty")
            if acc:
                accounts_in_trades.add(acc)
            if cp:
                accounts_in_trades.add(cp)

        owner_info_str = ""
        for account in accounts_in_trades:
            if account in owner_map:
                info = owner_map[account]
                owner_info_str += f"""
- {account}:
    Beneficial Owner: {info['beneficial_owner_name']} ({info['beneficial_owner_id']})
    Relationship Type: {info['relationship_type']}
"""
            else:
                owner_info_str += f"\n- {account}: Owner information not found"

        data = f"""## Counterparty Analysis Data

### Trades Being Analyzed
{trade_flow_str}

### Beneficial Ownership Information
{owner_info_str}

### Pattern Detection Result
- Pattern Type: {pattern_result['pattern_type']}
- Detection Confidence: {pattern_result['confidence']}%
- Analysis: {pattern_result['analysis']}

### Pattern Type Definitions
- DIRECT_WASH: Trade between accounts with same beneficial owner
- LAYERED_WASH: Circular pattern (A->B->C->A) where accounts share beneficial owner
- INTERMEDIARY_WASH: Trade routed through unrelated intermediary to obscure ownership
- NO_PATTERN: No clear wash trade indicators detected
"""
        return data

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM interpretation of counterparty analysis.

        Args:
            raw_data: Analysis data
            **kwargs: Trade parameters

        Returns:
            Prompt for LLM interpretation
        """
        prompt = f"""You are analyzing trade counterparty relationships for wash trade detection.

## Task
Analyze the trade flow and beneficial ownership to classify the wash trade pattern.

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


def create_counterparty_analysis_tool(llm: Any, data_dir: str) -> dict:
    """Create LangChain-compatible tool for counterparty analysis.

    Args:
        llm: LangChain LLM instance
        data_dir: Path to data directory

    Returns:
        Dictionary with tool function and metadata
    """
    tool = CounterpartyAnalysisTool(llm, data_dir)

    def counterparty_analysis_func(trades: str) -> str:
        """Map trade flow and detect circular trading patterns.

        Args:
            trades: JSON string of trades with format:
                [{"account_id": "ACC-001", "side": "BUY", "quantity": 10000,
                  "price": 150.0, "counterparty_account": "ACC-002", "symbol": "AAPL"}, ...]

        Returns:
            Analysis of trade flow patterns and wash trade classification
        """
        return tool(trades=trades)

    return {
        "func": counterparty_analysis_func,
        "name": tool.name,
        "description": tool.description,
        "tool_instance": tool,
    }
