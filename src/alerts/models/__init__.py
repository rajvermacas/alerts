"""Models package for SMARTS Alert Analyzer.

This package contains all Pydantic models used throughout the application,
organized by alert type and with shared base classes.
"""

from alerts.models.base import (
    BaseAlertDecision,
    AlertSummary,
    FewShotExample,
    FewShotExamplesCollection,
)
from alerts.models.insider_trading import (
    TraderBaselineAnalysis,
    MarketContext,
    InsiderTradingDecision,
    # Backward compatibility alias
    AlertDecision,
)
from alerts.models.wash_trade import (
    RelationshipNode,
    RelationshipEdge,
    RelationshipNetwork,
    TimingPattern,
    TradeFlow,
    CounterpartyPattern,
    HistoricalPatternSummary,
    WashTradeDecision,
    WashTradeFewShotExample,
    WashTradeFewShotCollection,
)

__all__ = [
    # Base models
    "BaseAlertDecision",
    "AlertSummary",
    "FewShotExample",
    "FewShotExamplesCollection",
    # Insider trading models
    "TraderBaselineAnalysis",
    "MarketContext",
    "InsiderTradingDecision",
    "AlertDecision",  # Backward compatibility
    # Wash trade models
    "RelationshipNode",
    "RelationshipEdge",
    "RelationshipNetwork",
    "TimingPattern",
    "TradeFlow",
    "CounterpartyPattern",
    "HistoricalPatternSummary",
    "WashTradeDecision",
    "WashTradeFewShotExample",
    "WashTradeFewShotCollection",
]
