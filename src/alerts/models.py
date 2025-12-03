"""Pydantic models for structured output.

This module re-exports models from the new models package for
backward compatibility. New code should import from alerts.models.

Model structure:
- alerts.models.base: Base classes and common models
- alerts.models.insider_trading: Insider trading specific models
- alerts.models.wash_trade: Wash trade specific models (coming soon)
"""

# Re-export all models for backward compatibility
from alerts.models import (
    # Base models
    BaseAlertDecision,
    AlertSummary,
    FewShotExample,
    FewShotExamplesCollection,
    # Insider trading models
    TraderBaselineAnalysis,
    MarketContext,
    InsiderTradingDecision,
    AlertDecision,  # Backward compatibility alias
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
]
