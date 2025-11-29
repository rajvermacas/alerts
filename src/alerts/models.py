"""Pydantic models for structured output.

This module defines the data models used for agent output,
ensuring consistent, parseable results from the alert analysis.
"""

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class TraderBaselineAnalysis(BaseModel):
    """Analysis of trader's historical trading baseline.

    Attributes:
        typical_volume: Description of trader's typical trading volume
        typical_sectors: Sectors the trader typically trades in
        typical_frequency: How often the trader typically trades
        deviation_assessment: Assessment of how flagged trade deviates from baseline
    """

    typical_volume: str = Field(
        description="Description of trader's typical trading volume (e.g., '5,000 shares/day average')"
    )
    typical_sectors: str = Field(
        description="Sectors the trader typically trades in (e.g., 'Tech, Healthcare')"
    )
    typical_frequency: str = Field(
        description="Trading frequency description (e.g., 'Daily active trader', 'Weekly trades')"
    )
    deviation_assessment: str = Field(
        description="Assessment of how the flagged trade deviates from the trader's baseline"
    )


class MarketContext(BaseModel):
    """Market context surrounding the flagged trade.

    Attributes:
        news_timeline: Timeline of relevant news events
        volatility_assessment: Assessment of market volatility during the period
        peer_activity_summary: Summary of peer trading activity
    """

    news_timeline: str = Field(
        description="Timeline of relevant news events around the trade date"
    )
    volatility_assessment: str = Field(
        description="Assessment of market volatility and price movements"
    )
    peer_activity_summary: str = Field(
        description="Summary of how peers traded the same symbol in the period"
    )


class AlertDecision(BaseModel):
    """Final structured decision from the alert analysis.

    This is the primary output model for the agent, containing
    the determination, supporting evidence, and reasoning.

    Attributes:
        alert_id: Unique identifier of the analyzed alert
        determination: Final decision (ESCALATE, CLOSE, or NEEDS_HUMAN_REVIEW)
        genuine_alert_confidence: Confidence (0-100) that this is genuine insider trading
        false_positive_confidence: Confidence (0-100) that this is a false positive
        key_findings: List of key findings from the investigation
        favorable_indicators: Reasons supporting genuine insider trading suspicion
        risk_mitigating_factors: Reasons suggesting this is likely a false positive
        trader_baseline_analysis: Detailed trader baseline analysis
        market_context: Market context analysis
        reasoning_narrative: Human-readable explanation of the decision
        similar_precedent: Which few-shot example this case most resembles
        recommended_action: Recommended next action
        data_gaps: Missing data that would improve analysis
        timestamp: When this decision was generated
    """

    alert_id: str = Field(
        description="Unique identifier of the analyzed alert"
    )

    determination: Literal["ESCALATE", "CLOSE", "NEEDS_HUMAN_REVIEW"] = Field(
        description="Final decision: ESCALATE (genuine suspicion), CLOSE (false positive), or NEEDS_HUMAN_REVIEW (conflicting signals)"
    )

    genuine_alert_confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence level (0-100) that this is genuine insider trading"
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
        description="Indicators suggesting this might be genuine insider trading"
    )

    risk_mitigating_factors: List[str] = Field(
        description="Factors suggesting this is likely a false positive"
    )

    trader_baseline_analysis: TraderBaselineAnalysis = Field(
        description="Detailed analysis of the trader's historical trading baseline"
    )

    market_context: MarketContext = Field(
        description="Market context surrounding the flagged trade"
    )

    reasoning_narrative: str = Field(
        min_length=100,
        description="Human-readable explanation of the decision (2-4 paragraphs)"
    )

    similar_precedent: str = Field(
        description="Which few-shot example this case most closely resembles and why"
    )

    recommended_action: Literal["ESCALATE", "CLOSE", "MONITOR", "REQUEST_MORE_DATA"] = Field(
        description="Recommended next action for the alert"
    )

    data_gaps: List[str] = Field(
        default_factory=list,
        description="List of missing data that would improve the analysis"
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

    Attributes:
        alert_id: Unique alert identifier
        alert_type: Type of alert (e.g., 'Pre-Announcement Trading')
        rule_violated: Rule code that was violated
        generated_timestamp: When the alert was generated
        trader_id: ID of the flagged trader
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
