"""AlertContext models for structured alert data.

This module defines Pydantic models for structured alert context data
that replaces raw XML in AnalysisRequest. The Big Data Layer parses
XML into these models before sending to the orchestrator.

Design Decisions:
    - Discriminated union with context_type as discriminator
    - EXCLUDES AnomalyIndicators/WashTradeIndicators (SMARTS pre-analysis)
    - Pure 1:1 mapping from XML structure
    - Agent computes date ranges (not Big Data Layer)

Architecture Reference:
    .dev-resources/architecture/remove-alert-reader-tool.md
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Insider Trading Nested Models
# =============================================================================


class Trader(BaseModel):
    """Trader information from IT alert XML <Trader> element.

    Maps directly to:
        <Trader>
            <TraderID>T001</TraderID>
            <Name>John Smith</Name>
            <Department>Operations</Department>
        </Trader>
    """

    trader_id: str = Field(..., description="Trader identifier from <TraderID>")
    name: str = Field(..., description="Trader name from <Name>")
    department: str = Field(..., description="Department from <Department>")


class Trade(BaseModel):
    """Single trade from IT alert XML <SuspiciousActivity> element.

    Maps directly to:
        <SuspiciousActivity>
            <Symbol>ACME</Symbol>
            <TradeDate>2024-03-15</TradeDate>
            <Side>BUY</Side>
            <Quantity>50000</Quantity>
            <Price>101.50</Price>
            <TotalValue>5075000</TotalValue>
        </SuspiciousActivity>
    """

    symbol: str = Field(..., description="Stock symbol from <Symbol>")
    trade_date: date = Field(..., description="Trade date from <TradeDate>")
    side: Literal["BUY", "SELL"] = Field(..., description="Trade side from <Side>")
    quantity: int = Field(..., ge=1, description="Quantity from <Quantity>")
    price: Decimal = Field(..., gt=0, description="Price from <Price>")
    total_value: Decimal = Field(..., gt=0, description="Total value from <TotalValue>")


class RelatedEvent(BaseModel):
    """Related event from IT alert XML <RelatedEvent> element.

    This is optional - not all alerts have a related event.

    Maps directly to:
        <RelatedEvent>
            <EventType>M&A Announcement</EventType>
            <EventDate>2024-03-16</EventDate>
            <EventDescription>ACME Corp acquired by TechGiant</EventDescription>
        </RelatedEvent>
    """

    event_type: str = Field(..., description="Event type from <EventType>")
    event_date: date = Field(..., description="Event date from <EventDate>")
    description: str = Field(..., description="Description from <EventDescription>")


# =============================================================================
# Wash Trade Nested Models
# =============================================================================


class WashTradeFlaggedTrade(BaseModel):
    """Single flagged trade from WT alert XML <Trade> element.

    Maps directly to:
        <Trade sequence="1">
            <AccountID>ACC-001</AccountID>
            <AccountName>Smith Family Trust</AccountName>
            <TradeDate>2024-01-15</TradeDate>
            <TradeTime>14:32:15.123</TradeTime>
            <Symbol>AAPL</Symbol>
            <Side>BUY</Side>
            <Quantity>10000</Quantity>
            <Price>150.00</Price>
            <TotalValue>1500000.00</TotalValue>
            <CounterpartyAccount>ACC-002</CounterpartyAccount>
            <OrderID>ORD-001</OrderID>
        </Trade>
    """

    sequence: int = Field(..., ge=1, description="Trade sequence from @sequence attr")
    account_id: str = Field(..., description="Account ID from <AccountID>")
    account_name: str = Field(..., description="Account name from <AccountName>")
    trade_date: date = Field(..., description="Trade date from <TradeDate>")
    trade_time: str = Field(..., description="Trade time from <TradeTime>")
    symbol: str = Field(..., description="Stock symbol from <Symbol>")
    side: Literal["BUY", "SELL"] = Field(..., description="Trade side from <Side>")
    quantity: int = Field(..., ge=1, description="Quantity from <Quantity>")
    price: Decimal = Field(..., gt=0, description="Price from <Price>")
    total_value: Decimal = Field(..., gt=0, description="Total value from <TotalValue>")
    counterparty_account: str = Field(
        ..., description="Counterparty from <CounterpartyAccount>"
    )
    order_id: str = Field(..., description="Order ID from <OrderID>")


# =============================================================================
# Alert Context Models (Discriminated Union)
# =============================================================================


class InsiderTradingAlertContext(BaseModel):
    """Structured context for Insider Trading alerts.

    Maps 1:1 from <SMARTSAlert> XML structure.

    EXCLUDES (per architecture decision - SMARTS pre-analysis, not raw data):
        - <AnomalyIndicators> entire section
            - AnomalyScore
            - ConfidenceLevel
            - TemporalProximity
            - EstimatedProfit

    The agent computes date ranges internally:
        - start_date = trade_date - 30 days
        - end_date = trade_date + 7 days

    Example XML:
        <SMARTSAlert>
            <AlertID>ITA-2024-001847</AlertID>
            <AlertType>Pre-Announcement Trading</AlertType>
            <RuleViolated>MAR-03-001</RuleViolated>
            <GeneratedTimestamp>2024-03-16T10:30:00Z</GeneratedTimestamp>
            <Trader>...</Trader>
            <SuspiciousActivity>...</SuspiciousActivity>
            <RelatedEvent>...</RelatedEvent>  <!-- optional -->
        </SMARTSAlert>
    """

    # Discriminator field - enables Union type discrimination
    context_type: Literal["insider_trading"] = Field(
        default="insider_trading",
        description="Discriminator for AlertContext union type",
    )

    # Root attributes from XML
    alert_id: str = Field(..., description="Alert ID from <AlertID>")
    alert_type: str = Field(..., description="Alert type from <AlertType>")
    rule_violated: str = Field(..., description="Rule violated from <RuleViolated>")
    generated_timestamp: datetime = Field(
        ..., description="Timestamp from <GeneratedTimestamp>"
    )

    # Nested structures
    trader: Trader = Field(..., description="Trader info from <Trader>")
    trade: Trade = Field(..., description="Suspicious activity from <SuspiciousActivity>")
    related_event: Optional[RelatedEvent] = Field(
        default=None, description="Related event from <RelatedEvent> (optional)"
    )


class WashTradeAlertContext(BaseModel):
    """Structured context for Wash Trade alerts.

    Maps 1:1 from <SmartsAlert> XML structure.

    EXCLUDES (per architecture decision - SMARTS pre-analysis, not raw data):
        - <WashTradeIndicators> entire section
            - TimeDelta
            - SameSymbol
            - SameQuantity
            - SamePrice
            - OffsettingTrades
            - VolumeImpact
            - DailyVolume
        - <AnomalyScore> and <ConfidenceLevel> from metadata

    The agent computes date ranges internally:
        - start_date = trade_date - 30 days
        - end_date = trade_date + 7 days

    Example XML:
        <SmartsAlert>
            <AlertMetadata>
                <AlertID>WT-2024-001</AlertID>
                <AlertType>WashTrade</AlertType>
                <RuleViolated>WT-001</RuleViolated>
                <GeneratedTimestamp>2024-01-15T14:35:00Z</GeneratedTimestamp>
                <Severity>HIGH</Severity>
            </AlertMetadata>
            <FlaggedTrades>
                <Trade sequence="1">...</Trade>
                <Trade sequence="2">...</Trade>
            </FlaggedTrades>
        </SmartsAlert>
    """

    # Discriminator field - enables Union type discrimination
    context_type: Literal["wash_trade"] = Field(
        default="wash_trade",
        description="Discriminator for AlertContext union type",
    )

    # Metadata from <AlertMetadata>
    alert_id: str = Field(..., description="Alert ID from <AlertID>")
    alert_type: str = Field(..., description="Alert type from <AlertType>")
    rule_violated: str = Field(..., description="Rule violated from <RuleViolated>")
    generated_timestamp: datetime = Field(
        ..., description="Timestamp from <GeneratedTimestamp>"
    )
    severity: str = Field(..., description="Severity level from <Severity>")

    # Flagged trades from <FlaggedTrades>
    flagged_trades: List[WashTradeFlaggedTrade] = Field(
        ...,
        min_length=2,
        description="List of flagged trades (min 2 for wash trade pattern)",
    )


# =============================================================================
# Discriminated Union Type
# =============================================================================

AlertContext = Annotated[
    Union[InsiderTradingAlertContext, WashTradeAlertContext],
    Field(discriminator="context_type"),
]
"""Union type for alert context.

Uses Pydantic's discriminated union feature with `context_type` as the
discriminator field. This enables:
    - Type-safe deserialization based on context_type value
    - Clear separation between IT and WT alert structures
    - Easy extensibility for new alert types

Usage:
    # Deserialize from dict (Pydantic will pick the right type)
    context = AlertContext.model_validate(data)

    # Type narrowing in code
    if context.context_type == "insider_trading":
        # context is InsiderTradingAlertContext
        trader_id = context.trader.trader_id
    elif context.context_type == "wash_trade":
        # context is WashTradeAlertContext
        accounts = [t.account_id for t in context.flagged_trades]
"""
