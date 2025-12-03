"""Wash trade specific models for SMARTS Alert Analyzer.

This module defines the data models specific to wash trade
alert analysis, extending the base models.

Wash trading occurs when the same beneficial owner is on both sides
of a trade, creating artificial trading volume and false appearance
of market liquidity.
"""

import logging
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from alerts.models.base import BaseAlertDecision

logger = logging.getLogger(__name__)


class RelationshipNode(BaseModel):
    """Node in the relationship network representing an account.

    Attributes:
        account_id: Unique identifier for the account
        beneficial_owner_id: ID of the beneficial owner
        beneficial_owner_name: Name of the beneficial owner
        relationship_type: Type of ownership relationship
        is_flagged: Whether this account is directly involved in flagged trades
    """

    account_id: str = Field(
        description="Unique identifier for the account (e.g., 'ACC-001')"
    )
    beneficial_owner_id: str = Field(
        description="ID of the beneficial owner (e.g., 'BO-123')"
    )
    beneficial_owner_name: str = Field(
        description="Name of the beneficial owner (e.g., 'John Smith')"
    )
    relationship_type: Literal[
        "direct", "family_trust", "corporate", "nominee", "market_maker",
        "hedge_book", "spousal", "intermediary"
    ] = Field(
        description="Type of ownership relationship"
    )
    is_flagged: bool = Field(
        default=False,
        description="Whether this account is directly involved in the flagged trades"
    )


class RelationshipEdge(BaseModel):
    """Edge representing a trade or ownership link between accounts.

    Attributes:
        from_account: Source account ID
        to_account: Target account ID
        edge_type: Type of relationship (trade or ownership)
        trade_details: Details of the trade if edge_type is 'trade'
        is_suspicious: Whether this edge is part of a suspicious pattern
    """

    from_account: str = Field(
        description="Source account ID"
    )
    to_account: str = Field(
        description="Target account ID"
    )
    edge_type: Literal["trade", "ownership", "beneficial_owner"] = Field(
        description="Type of relationship - trade flow or ownership link"
    )
    trade_details: Optional[str] = Field(
        default=None,
        description="Trade details if edge_type is 'trade' (e.g., '10K AAPL @ $150')"
    )
    is_suspicious: bool = Field(
        default=False,
        description="Whether this edge is part of a suspicious pattern"
    )


class RelationshipNetwork(BaseModel):
    """Network of account relationships and trade flows.

    This model captures the complete relationship graph for visualization
    in the HTML report as an SVG network diagram.

    Attributes:
        nodes: List of account nodes in the network
        edges: List of edges (trades and ownership links)
        pattern_type: Type of wash trade pattern detected
        pattern_confidence: Confidence in the pattern detection (0-100)
        pattern_description: Human-readable description of the pattern
    """

    nodes: List[RelationshipNode] = Field(
        min_length=1,
        description="List of account nodes in the relationship network"
    )
    edges: List[RelationshipEdge] = Field(
        min_length=1,
        description="List of edges representing trades and ownership links"
    )
    pattern_type: Literal[
        "DIRECT_WASH", "LAYERED_WASH", "INTERMEDIARY_WASH", "NO_PATTERN"
    ] = Field(
        description="Type of wash trade pattern detected"
    )
    pattern_confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence in the pattern detection (0-100)"
    )
    pattern_description: str = Field(
        description="Human-readable description of the detected pattern"
    )

    def get_flagged_accounts(self) -> List[str]:
        """Get list of flagged account IDs.

        Returns:
            List of account IDs that are flagged in the network
        """
        return [node.account_id for node in self.nodes if node.is_flagged]

    def get_beneficial_owners(self) -> List[str]:
        """Get list of unique beneficial owner IDs.

        Returns:
            List of unique beneficial owner IDs in the network
        """
        return list(set(node.beneficial_owner_id for node in self.nodes))

    def has_same_beneficial_owner(self) -> bool:
        """Check if all flagged accounts share the same beneficial owner.

        Returns:
            True if all flagged accounts have the same beneficial owner
        """
        flagged_owners = [
            node.beneficial_owner_id
            for node in self.nodes
            if node.is_flagged
        ]
        return len(set(flagged_owners)) == 1 if flagged_owners else False


class TimingPattern(BaseModel):
    """Temporal analysis of the flagged trades.

    Attributes:
        time_delta_ms: Time difference between trades in milliseconds
        time_delta_description: Human-readable time delta description
        market_phase: Phase of the market when trades occurred
        liquidity_assessment: Assessment of market liquidity at trade time
        is_pre_arranged: Whether timing suggests pre-arranged execution
        pre_arrangement_confidence: Confidence that trades were pre-arranged (0-100)
        timing_analysis: Detailed timing analysis narrative
    """

    time_delta_ms: int = Field(
        ge=0,
        description="Time difference between trades in milliseconds"
    )
    time_delta_description: str = Field(
        description="Human-readable time delta (e.g., '502ms', '2.5 seconds', '30 minutes')"
    )
    market_phase: Literal[
        "pre_market", "opening_auction", "regular_session",
        "closing_auction", "after_hours", "unknown"
    ] = Field(
        description="Phase of the market when trades occurred"
    )
    liquidity_assessment: Literal["high", "medium", "low", "very_low"] = Field(
        description="Assessment of market liquidity at the time of trades"
    )
    is_pre_arranged: bool = Field(
        description="Whether the timing pattern suggests pre-arranged execution"
    )
    pre_arrangement_confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence that trades were pre-arranged (0-100)"
    )
    timing_analysis: str = Field(
        description="Detailed narrative analysis of the timing pattern"
    )


class TradeFlow(BaseModel):
    """Individual trade in a trade flow sequence.

    Attributes:
        sequence_number: Order of this trade in the flow
        account_id: Account that executed this trade
        side: Trade side (BUY or SELL)
        quantity: Number of shares traded
        price: Trade price
        timestamp: Trade timestamp
        counterparty_account: Account on the other side of the trade
    """

    sequence_number: int = Field(
        ge=1,
        description="Order of this trade in the flow sequence"
    )
    account_id: str = Field(
        description="Account that executed this trade"
    )
    side: Literal["BUY", "SELL"] = Field(
        description="Trade side"
    )
    quantity: int = Field(
        gt=0,
        description="Number of shares traded"
    )
    price: float = Field(
        gt=0,
        description="Trade price"
    )
    timestamp: str = Field(
        description="Trade timestamp (ISO format)"
    )
    counterparty_account: Optional[str] = Field(
        default=None,
        description="Account on the other side of the trade"
    )


class CounterpartyPattern(BaseModel):
    """Analysis of counterparty relationships and trade patterns.

    Attributes:
        trade_flow: Sequence of trades in the pattern
        is_circular: Whether trades form a circular pattern (A->B->C->A)
        is_offsetting: Whether trades are offsetting (same qty, opposite sides)
        same_beneficial_owner: Whether all parties have same beneficial owner
        intermediary_accounts: Any intermediary accounts used for obfuscation
        economic_purpose_identified: Whether legitimate economic purpose exists
        economic_purpose_description: Description of any identified economic purpose
    """

    trade_flow: List[TradeFlow] = Field(
        min_length=2,
        description="Sequence of trades in the pattern"
    )
    is_circular: bool = Field(
        description="Whether trades form a circular pattern (A->B->C->A)"
    )
    is_offsetting: bool = Field(
        description="Whether trades are offsetting (same quantity, opposite sides)"
    )
    same_beneficial_owner: bool = Field(
        description="Whether all accounts in the flow share the same beneficial owner"
    )
    intermediary_accounts: List[str] = Field(
        default_factory=list,
        description="List of intermediary accounts used for potential obfuscation"
    )
    economic_purpose_identified: bool = Field(
        description="Whether a legitimate economic purpose has been identified"
    )
    economic_purpose_description: Optional[str] = Field(
        default=None,
        description="Description of the legitimate economic purpose if identified"
    )


class HistoricalPatternSummary(BaseModel):
    """Summary of historical trading patterns between related accounts.

    Attributes:
        pattern_count: Number of similar patterns found in history
        time_window_days: Time window analyzed (in days)
        average_frequency: Average frequency of similar patterns
        pattern_trend: Whether pattern is increasing, stable, or decreasing
        historical_analysis: Detailed narrative of historical patterns
    """

    pattern_count: int = Field(
        ge=0,
        description="Number of similar trading patterns found in history"
    )
    time_window_days: int = Field(
        gt=0,
        description="Time window analyzed in days"
    )
    average_frequency: str = Field(
        description="Average frequency of similar patterns (e.g., '0.5 per day')"
    )
    pattern_trend: Literal["increasing", "stable", "decreasing", "new"] = Field(
        description="Trend of the pattern over time"
    )
    historical_analysis: str = Field(
        description="Detailed narrative analysis of historical patterns"
    )


class WashTradeDecision(BaseAlertDecision):
    """Wash trade specific decision with specialized fields.

    Extends BaseAlertDecision with wash-trade-specific analysis
    including relationship networks, timing patterns, and regulatory flags.

    Attributes:
        alert_type: Always "WASH_TRADE" for this model
        relationship_network: Network of account relationships and trade flows
        timing_patterns: Temporal analysis of the flagged trades
        counterparty_pattern: Analysis of counterparty relationships
        historical_patterns: Summary of historical trading patterns
        volume_impact_percentage: Percentage of daily volume affected
        beneficial_ownership_match: Whether beneficial ownership matches
        economic_purpose_identified: Whether legitimate economic purpose exists
        regulatory_flags: List of applicable regulatory violations
        recommended_action: Recommended next action
        data_gaps: Missing data that would improve analysis
    """

    alert_type: Literal["WASH_TRADE"] = Field(
        default="WASH_TRADE",
        description="Type of alert - always WASH_TRADE for this model"
    )

    relationship_network: RelationshipNetwork = Field(
        description="Network of account relationships and trade flows for SVG visualization"
    )

    timing_patterns: TimingPattern = Field(
        description="Temporal analysis of the flagged trades"
    )

    counterparty_pattern: CounterpartyPattern = Field(
        description="Analysis of counterparty relationships and trade flow"
    )

    historical_patterns: HistoricalPatternSummary = Field(
        description="Summary of historical trading patterns between related accounts"
    )

    volume_impact_percentage: float = Field(
        ge=0,
        le=100,
        description="Percentage of daily trading volume affected by the flagged trades"
    )

    beneficial_ownership_match: bool = Field(
        description="Whether the same beneficial owner is on both sides of trades"
    )

    economic_purpose_identified: bool = Field(
        description="Whether a legitimate economic purpose for the trades was identified"
    )

    regulatory_flags: List[str] = Field(
        min_length=0,
        max_length=10,
        description="List of applicable regulatory violations (e.g., 'MAS_SFA_S197', 'SFC_SFO_S274')"
    )

    recommended_action: Literal["ESCALATE", "CLOSE", "MONITOR", "REQUEST_MORE_DATA"] = Field(
        description="Recommended next action for the alert"
    )

    data_gaps: List[str] = Field(
        default_factory=list,
        description="List of missing data that would improve the analysis"
    )

    def get_regulatory_summary(self) -> str:
        """Get a human-readable summary of regulatory flags.

        Returns:
            Formatted string of regulatory violations
        """
        if not self.regulatory_flags:
            return "No specific regulatory flags identified."

        flag_descriptions = {
            "MAS_SFA_S197": "Singapore MAS SFA Section 197 - False trading and market rigging",
            "MAS_SFA_S198": "Singapore MAS SFA Section 198 - Market manipulation",
            "MAS_SFA_S199": "Singapore MAS SFA Section 199 - Wash trades",
            "SFC_SFO_S274": "Hong Kong SFC SFO Section 274 - Market misconduct",
            "ASIC_CA_S1041A": "Australia ASIC Corporations Act Section 1041A - Market manipulation",
            "FSA_FIEA_A159": "Japan FSA FIEA Article 159 - Wash trading prohibition",
        }

        summaries = []
        for flag in self.regulatory_flags:
            desc = flag_descriptions.get(flag, f"Regulatory flag: {flag}")
            summaries.append(f"- {desc}")

        return "\n".join(summaries)

    def is_high_confidence_violation(self) -> bool:
        """Check if this is a high-confidence wash trade violation.

        Returns:
            True if determination is ESCALATE and confidence is >= 80
        """
        return (
            self.determination == "ESCALATE"
            and self.genuine_alert_confidence >= 80
        )


class WashTradeFewShotExample(BaseModel):
    """A few-shot example for wash trade case law reasoning.

    Attributes:
        id: Unique identifier for the example
        title: Short title describing the case
        jurisdiction: Regulatory jurisdiction (e.g., 'Singapore', 'Hong Kong')
        regulation: Specific regulation reference
        scenario: Description of the scenario
        determination: The correct determination for this case
        reasoning: Explanation of why this determination was made
        key_factors: Key factors that led to this determination
    """

    id: str = Field(
        description="Unique identifier (e.g., 'WS-001')"
    )
    title: str = Field(
        description="Short title describing the case"
    )
    jurisdiction: str = Field(
        description="Regulatory jurisdiction (e.g., 'Singapore', 'Hong Kong')"
    )
    regulation: str = Field(
        description="Specific regulation reference (e.g., 'MAS SFA Section 197')"
    )
    scenario: dict = Field(
        description="Scenario details as key-value pairs"
    )
    determination: Literal["ESCALATE", "CLOSE", "NEEDS_HUMAN_REVIEW"] = Field(
        description="The correct determination for this case"
    )
    reasoning: str = Field(
        description="Explanation of why this determination was made"
    )
    key_factors: List[str] = Field(
        min_length=1,
        description="Key factors that led to this determination"
    )


class WashTradeFewShotCollection(BaseModel):
    """Collection of wash trade few-shot examples.

    Attributes:
        examples: List of wash trade few-shot examples
    """

    examples: List[WashTradeFewShotExample] = Field(
        min_length=1,
        description="List of wash trade few-shot examples for case law reasoning"
    )

    def get_examples_text(self) -> str:
        """Format examples as text for inclusion in prompts.

        Returns:
            Formatted string containing all examples
        """
        lines = ["## Wash Trade Precedent Cases (APAC Regulatory Framework)\n"]
        lines.append("Use these cases as reference for your reasoning. ")
        lines.append("Compare the current case to these precedents.\n")

        for ex in self.examples:
            lines.append(f"### Case {ex.id}: {ex.title}")
            lines.append(f"**Jurisdiction:** {ex.jurisdiction}")
            lines.append(f"**Regulation:** {ex.regulation}")
            lines.append(f"**Scenario:**")
            for key, value in ex.scenario.items():
                lines.append(f"  - {key}: {value}")
            lines.append(f"**Determination:** {ex.determination}")
            lines.append(f"**Reasoning:** {ex.reasoning}")
            lines.append(f"**Key Factors:**")
            for factor in ex.key_factors:
                lines.append(f"  - {factor}")
            lines.append("")

        return "\n".join(lines)
