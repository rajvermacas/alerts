"""Insider trading specific models for SMARTS Alert Analyzer.

This module defines the data models specific to insider trading
alert analysis, extending the base models.
"""

import logging
from typing import List, Literal

from pydantic import BaseModel, Field

from alerts.models.base import BaseAlertDecision

logger = logging.getLogger(__name__)


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


class InsiderTradingDecision(BaseAlertDecision):
    """Insider trading specific decision with additional fields.

    Extends BaseAlertDecision with insider-trading-specific analysis
    including trader baseline and market context.

    Attributes:
        alert_type: Always "INSIDER_TRADING" for this model
        trader_baseline_analysis: Detailed trader baseline analysis
        market_context: Market context analysis
        recommended_action: Recommended next action
        data_gaps: Missing data that would improve analysis
    """

    alert_type: Literal["INSIDER_TRADING"] = Field(
        default="INSIDER_TRADING",
        description="Type of alert - always INSIDER_TRADING for this model"
    )

    trader_baseline_analysis: TraderBaselineAnalysis = Field(
        description="Detailed analysis of the trader's historical trading baseline"
    )

    market_context: MarketContext = Field(
        description="Market context surrounding the flagged trade"
    )

    recommended_action: Literal["ESCALATE", "CLOSE", "MONITOR", "REQUEST_MORE_DATA"] = Field(
        description="Recommended next action for the alert"
    )

    data_gaps: List[str] = Field(
        default_factory=list,
        description="List of missing data that would improve the analysis"
    )


# Backward compatibility alias - AlertDecision is the old name
AlertDecision = InsiderTradingDecision
