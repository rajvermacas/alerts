"""Base models for SMARTS Alert Analyzer.

This module defines the base data models that are shared across different
alert types, including the base decision class and common structures.
"""

import logging
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BaseAlertDecision(BaseModel):
    """Base class for all alert decision models.

    This provides common fields shared across different alert types
    (insider trading, wash trade, etc.).

    Attributes:
        alert_id: Unique identifier of the analyzed alert
        alert_type: Type of alert (INSIDER_TRADING, WASH_TRADE, etc.)
        determination: Final decision (ESCALATE, CLOSE, or NEEDS_HUMAN_REVIEW)
        genuine_alert_confidence: Confidence (0-100) that this is a genuine violation
        false_positive_confidence: Confidence (0-100) that this is a false positive
        key_findings: List of key findings from the investigation
        favorable_indicators: Reasons supporting genuine violation suspicion
        risk_mitigating_factors: Reasons suggesting this is likely a false positive
        reasoning_narrative: Human-readable explanation of the decision
        similar_precedent: Which few-shot example this case most resembles
        timestamp: When this decision was generated
    """

    alert_id: str = Field(
        description="Unique identifier of the analyzed alert"
    )

    alert_type: Literal["INSIDER_TRADING", "WASH_TRADE"] = Field(
        description="Type of alert being analyzed"
    )

    determination: Literal["ESCALATE", "CLOSE", "NEEDS_HUMAN_REVIEW"] = Field(
        description="Final decision: ESCALATE (genuine suspicion), CLOSE (false positive), or NEEDS_HUMAN_REVIEW (conflicting signals)"
    )

    genuine_alert_confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence level (0-100) that this is a genuine violation"
    )

    false_positive_confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence level (0-100) that this is a false positive"
    )

    key_findings: List[str] = Field(
        min_length=1,
        max_length=10,
        description="List of key findings from the investigation"
    )

    favorable_indicators: List[str] = Field(
        description="Indicators suggesting this might be a genuine violation"
    )

    risk_mitigating_factors: List[str] = Field(
        description="Factors suggesting this is likely a false positive"
    )

    reasoning_narrative: str = Field(
        min_length=100,
        description="Human-readable explanation of the decision (2-4 paragraphs)"
    )

    similar_precedent: str = Field(
        description="Which few-shot example this case most closely resembles and why"
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when this decision was generated"
    )

    def to_audit_entry(self) -> dict:
        """Convert to a compact audit log entry.

        Returns:
            Dictionary suitable for JSONL audit logging
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "determination": self.determination,
            "confidence": {
                "genuine": self.genuine_alert_confidence,
                "false_positive": self.false_positive_confidence,
            },
            "reasoning_summary": self.reasoning_narrative[:200] + "..."
            if len(self.reasoning_narrative) > 200
            else self.reasoning_narrative,
        }


class AlertSummary(BaseModel):
    """Summary of alert data extracted from XML.

    This is a generic alert summary that can be used for any alert type.
    Specific alert types may have additional fields.

    Attributes:
        alert_id: Unique alert identifier
        alert_type: Type of alert (e.g., 'Pre-Announcement Trading', 'Wash Trade')
        rule_violated: Rule code that was violated
        generated_timestamp: When the alert was generated
        trader_id: ID of the flagged trader/account
        trader_name: Name of the flagged trader
        trader_department: Department of the trader
        symbol: Trading symbol
        trade_date: Date of the suspicious trade
        side: Trade side (BUY/SELL)
        quantity: Number of shares traded
        price: Trade price
        total_value: Total trade value
        anomaly_score: SMARTS anomaly score
        confidence_level: SMARTS confidence level
        temporal_proximity: Time proximity to material event
        estimated_profit: Estimated profit from the trade
        related_event_type: Type of related material event
        related_event_date: Date of the related event
        related_event_description: Description of the related event
    """

    alert_id: str
    alert_type: str
    rule_violated: str
    generated_timestamp: str
    trader_id: str
    trader_name: str
    trader_department: str
    symbol: str
    trade_date: str
    side: str
    quantity: int
    price: float
    total_value: float
    anomaly_score: int
    confidence_level: str
    temporal_proximity: str
    estimated_profit: float
    related_event_type: Optional[str] = None
    related_event_date: Optional[str] = None
    related_event_description: Optional[str] = None


class FewShotExample(BaseModel):
    """A single few-shot example for case law reasoning.

    Few-shot examples serve as precedents that the agent compares
    current cases against.

    Attributes:
        id: Unique identifier for the example
        scenario: Scenario type (e.g., 'genuine_clear', 'false_positive_clear')
        alert_summary: Brief summary of the alert
        trader_baseline: Description of trader's baseline behavior
        market_context: Description of market context
        peer_activity: Description of peer trading activity
        determination: The correct determination for this case
        reasoning: Explanation of why this determination was made
    """

    id: str = Field(description="Unique identifier (e.g., 'ex_001')")
    scenario: str = Field(description="Scenario type for categorization")
    alert_summary: str = Field(description="Brief summary of the alert scenario")
    trader_baseline: str = Field(description="Description of trader's baseline behavior")
    market_context: str = Field(description="Description of market context")
    peer_activity: str = Field(description="Description of peer trading activity")
    determination: Literal["ESCALATE", "CLOSE", "NEEDS_HUMAN_REVIEW"] = Field(
        description="The correct determination for this case"
    )
    reasoning: str = Field(description="Explanation of why this determination was made")


class FewShotExamplesCollection(BaseModel):
    """Collection of few-shot examples.

    Attributes:
        examples: List of few-shot examples
    """

    examples: List[FewShotExample] = Field(
        min_length=1,
        description="List of few-shot examples for case law reasoning"
    )

    def get_examples_text(self) -> str:
        """Format examples as text for inclusion in prompts.

        Returns:
            Formatted string containing all examples
        """
        lines = ["## Precedent Cases (Use these as reference for your reasoning)\n"]

        for ex in self.examples:
            lines.append(f"### Example {ex.id}: {ex.scenario}")
            lines.append(f"**Alert Summary:** {ex.alert_summary}")
            lines.append(f"**Trader Baseline:** {ex.trader_baseline}")
            lines.append(f"**Market Context:** {ex.market_context}")
            lines.append(f"**Peer Activity:** {ex.peer_activity}")
            lines.append(f"**Determination:** {ex.determination}")
            lines.append(f"**Reasoning:** {ex.reasoning}")
            lines.append("")

        return "\n".join(lines)
