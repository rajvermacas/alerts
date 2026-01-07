"""Integration tests for Deterministic Agents (Proactive Info Flow).

This module tests the deterministic agents for alert analysis.
Tests verify:
- Agent initialization with proper tool setup
- Fixed tool execution order
- Data injection via AnalysisRequest
- Decision synthesis
- HTML report generation
- Audit log writing
- Streaming event emission

Tests use mocked LLMs to avoid actual API calls while verifying the
complete agent flow.
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import asyncio

from alerts.agents.insider_trading import (
    DeterministicInsiderTradingAgent,
    IT_TOOL_ORDER,
)
from alerts.agents.wash_trade import (
    DeterministicWashTradeAgent,
    WT_TOOL_ORDER,
)
from alerts.models.request import AnalysisRequest, ToolInput
from alerts.models.insider_trading import InsiderTradingDecision
from alerts.models.wash_trade import WashTradeDecision


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_it_alert_xml() -> str:
    """Sample XML for insider trading alert."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
  <AlertID>ITA-2024-TEST</AlertID>
  <AlertType>Pre-Announcement Trading</AlertType>
  <RuleViolated>SMARTS-IT-001</RuleViolated>
  <GeneratedTimestamp>2024-03-16T10:30:00Z</GeneratedTimestamp>
  <Trader>
    <TraderID>T001</TraderID>
    <Name>Test Trader</Name>
    <Department>Operations</Department>
  </Trader>
  <SuspiciousActivity>
    <Symbol>ACME</Symbol>
    <TradeDate>2024-03-15</TradeDate>
    <Side>BUY</Side>
    <Quantity>50000</Quantity>
    <Price>101.50</Price>
    <TotalValue>5075000</TotalValue>
  </SuspiciousActivity>
  <AnomalyIndicators>
    <AnomalyScore>87</AnomalyScore>
    <ConfidenceLevel>HIGH</ConfidenceLevel>
    <TemporalProximity>36 hours before announcement</TemporalProximity>
    <EstimatedProfit>675000</EstimatedProfit>
  </AnomalyIndicators>
  <RelatedEvent>
    <EventType>M&amp;A Announcement</EventType>
    <EventDate>2024-03-16</EventDate>
    <Description>Acquisition announcement</Description>
  </RelatedEvent>
</SMARTSAlert>
"""


@pytest.fixture
def sample_wt_alert_xml() -> str:
    """Sample XML for wash trade alert."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<SMARTSAlert>
  <AlertID>WTA-2024-TEST</AlertID>
  <AlertType>Wash Trade</AlertType>
  <RuleViolated>SMARTS-WT-001</RuleViolated>
  <GeneratedTimestamp>2024-03-16T10:30:00Z</GeneratedTimestamp>
  <Trader>
    <TraderID>T002</TraderID>
    <Name>Wash Trader</Name>
    <Department>Trading</Department>
  </Trader>
  <SuspiciousActivity>
    <Symbol>TEST</Symbol>
    <TradeDate>2024-03-15</TradeDate>
    <Side>BUY</Side>
    <Quantity>10000</Quantity>
    <Price>100.00</Price>
    <TotalValue>1000000</TotalValue>
  </SuspiciousActivity>
  <AnomalyIndicators>
    <AnomalyScore>92</AnomalyScore>
    <ConfidenceLevel>HIGH</ConfidenceLevel>
  </AnomalyIndicators>
  <WashTradeIndicators>
    <SameAccount>False</SameAccount>
    <RelatedAccounts>True</RelatedAccounts>
    <TimingPattern>Sub-second</TimingPattern>
  </WashTradeIndicators>
</SMARTSAlert>
"""


@pytest.fixture
def it_analysis_request(sample_it_alert_xml: str) -> AnalysisRequest:
    """Create a valid AnalysisRequest for insider trading."""
    return AnalysisRequest(
        alert_xml=sample_it_alert_xml,
        agent_type="insider_trading",
        tool_data={
            "alert_reader": ToolInput(format="xml", data=sample_it_alert_xml),
            "market_news": ToolInput(
                format="txt",
                data="2024-03-15: No significant news\n2024-03-16 09:00: M&A announcement"
            ),
            "market_data": ToolInput(
                format="csv",
                data="timestamp,symbol,price,volume,vix\n2024-03-15,ACME,101.50,1500000,18.5"
            ),
            "trader_profile": ToolInput(
                format="csv",
                data="trader_id,name,role,department,mnpi_access,restrictions\nT001,Test Trader,BACK_OFFICE,Operations,LOW,No trading allowed"
            ),
            "trader_history": ToolInput(
                format="csv",
                data="date,symbol,side,qty,price,sector\n2024-01-15,MSFT,BUY,1000,375.00,TECH\n2024-02-01,AAPL,SELL,500,180.00,TECH"
            ),
        }
    )


@pytest.fixture
def wt_analysis_request(sample_wt_alert_xml: str) -> AnalysisRequest:
    """Create a valid AnalysisRequest for wash trade."""
    return AnalysisRequest(
        alert_xml=sample_wt_alert_xml,
        agent_type="wash_trade",
        tool_data={
            "alert_reader": ToolInput(format="xml", data=sample_wt_alert_xml),
            "market_data": ToolInput(
                format="csv",
                data="timestamp,symbol,price,volume\n2024-03-15,TEST,100.00,500000"
            ),
            "trader_profile": ToolInput(
                format="csv",
                data="trader_id,name,role,department,mnpi_access\nT002,Wash Trader,TRADER,Trading,MEDIUM"
            ),
            "account_relationships": ToolInput(
                format="csv",
                data="account_a,account_b,relationship_type,confidence\nA001,A002,BENEFICIAL_OWNER,0.95"
            ),
            "related_accounts_history": ToolInput(
                format="csv",
                data="account_id,date,symbol,side,qty,price\nA001,2024-03-15,TEST,BUY,5000,100.00\nA002,2024-03-15,TEST,SELL,5000,100.00"
            ),
            "trade_timing": ToolInput(
                format="csv",
                data="trade_id,timestamp,account,symbol,side,qty,price\nT1,2024-03-15T10:00:00.100,A001,TEST,BUY,5000,100.00\nT2,2024-03-15T10:00:00.150,A002,TEST,SELL,5000,100.00"
            ),
            "counterparty_analysis": ToolInput(
                format="csv",
                data="trade_id,counterparty_account,beneficial_owner_overlap,same_broker,broker_name\nT1,A002,TRUE,TRUE,XYZ Brokers"
            ),
        }
    )


@pytest.fixture
def mock_it_decision() -> InsiderTradingDecision:
    """Create a mock InsiderTradingDecision."""
    from alerts.models.insider_trading import TraderBaselineAnalysis, MarketContext

    return InsiderTradingDecision(
        alert_id="ITA-2024-TEST",
        determination="ESCALATE",
        genuine_alert_confidence=85,
        false_positive_confidence=15,
        key_findings=[
            "Trader has no history of trading ACME",
            "Trade occurred 36 hours before M&A announcement",
            "Back-office role with no trading authority"
        ],
        favorable_indicators=[
            "Clear temporal proximity to material event",
            "Unusual sector deviation from baseline"
        ],
        risk_mitigating_factors=[
            "No direct evidence of information flow"
        ],
        trader_baseline_analysis=TraderBaselineAnalysis(
            typical_volume="1,000 shares/trade",
            typical_sectors="TECH only",
            typical_frequency="Monthly",
            deviation_assessment="50x normal volume, new sector"
        ),
        market_context=MarketContext(
            news_timeline="No public news before announcement",
            volatility_assessment="Normal VIX levels",
            peer_activity_summary="No other internal buying"
        ),
        reasoning_narrative="The trader's behavior shows significant deviation from baseline. " * 10,
        similar_precedent="Similar to case EX-001 where back-office employee traded before M&A",
        recommended_action="ESCALATE"
    )


@pytest.fixture
def mock_wt_decision() -> WashTradeDecision:
    """Create a mock WashTradeDecision."""
    from alerts.models.wash_trade import (
        RelationshipNetwork,
        RelationshipNode,
        RelationshipEdge,
        TimingPattern,
        CounterpartyPattern,
        TradeFlow,
        HistoricalPatternSummary,
    )

    return WashTradeDecision(
        alert_id="WTA-2024-TEST",
        determination="ESCALATE",
        genuine_alert_confidence=90,
        false_positive_confidence=10,
        key_findings=[
            "Accounts A001 and A002 share beneficial ownership",
            "Trades occurred within 50ms of each other",
            "Same broker used for both sides"
        ],
        favorable_indicators=[
            "Clear beneficial ownership overlap",
            "Sub-second timing suggests coordination"
        ],
        risk_mitigating_factors=[
            "Trades occurred on lit market"
        ],
        reasoning_narrative="The wash trade indicators are strong with beneficial ownership overlap. " * 10,
        similar_precedent="Similar to WT-EX-001 layering case",
        recommended_action="ESCALATE",
        relationship_network=RelationshipNetwork(
            nodes=[
                RelationshipNode(
                    account_id="A001",
                    beneficial_owner_id="BO-123",
                    beneficial_owner_name="John Smith",
                    relationship_type="direct",
                    is_flagged=True
                ),
                RelationshipNode(
                    account_id="A002",
                    beneficial_owner_id="BO-123",
                    beneficial_owner_name="John Smith",
                    relationship_type="family_trust",
                    is_flagged=True
                ),
            ],
            edges=[
                RelationshipEdge(
                    from_account="A001",
                    to_account="A002",
                    edge_type="trade",
                    trade_details="5000 TEST @ $100.00",
                    is_suspicious=True
                ),
            ],
            pattern_type="DIRECT_WASH",
            pattern_confidence=90,
            pattern_description="Direct wash trade between accounts with same beneficial owner"
        ),
        timing_patterns=TimingPattern(
            time_delta_ms=50,
            time_delta_description="50ms",
            market_phase="regular_session",
            liquidity_assessment="medium",
            is_pre_arranged=True,
            pre_arrangement_confidence=85,
            timing_analysis="Trades executed within 50ms of each other during regular session"
        ),
        counterparty_pattern=CounterpartyPattern(
            trade_flow=[
                TradeFlow(
                    sequence_number=1,
                    account_id="A001",
                    side="BUY",
                    quantity=5000,
                    price=100.0,
                    timestamp="2024-03-15T10:00:00.100Z",
                    counterparty_account="A002"
                ),
                TradeFlow(
                    sequence_number=2,
                    account_id="A002",
                    side="SELL",
                    quantity=5000,
                    price=100.0,
                    timestamp="2024-03-15T10:00:00.150Z",
                    counterparty_account="A001"
                ),
            ],
            is_circular=True,
            is_offsetting=True,
            same_beneficial_owner=True,
            intermediary_accounts=[],
            economic_purpose_identified=False,
            economic_purpose_description=None
        ),
        historical_patterns=HistoricalPatternSummary(
            pattern_count=5,
            time_window_days=90,
            average_frequency="0.5 per week",
            pattern_trend="stable",
            historical_analysis="Pattern consistent with previous wash trade cases"
        ),
        volume_impact_percentage=2.5,
        beneficial_ownership_match=True,
        economic_purpose_identified=False,
        regulatory_flags=["MAS_SFA_S197", "MAS_SFA_S199"],
    )


@pytest.fixture
def mock_tool_llm():
    """Create a mock LLM for tool-level interpretation."""
    mock = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Tool analysis: Data shows normal patterns. No significant anomalies detected."
    mock.invoke.return_value = mock_response
    return mock


# =============================================================================
# Tool Order Tests
# =============================================================================

class TestToolOrder:
    """Tests for tool execution order constants."""

    def test_it_tool_order_defined(self):
        """Test IT_TOOL_ORDER is properly exported."""
        assert IT_TOOL_ORDER is not None
        assert isinstance(IT_TOOL_ORDER, tuple)
        assert len(IT_TOOL_ORDER) == 5

    def test_it_tool_order_contains_required_tools(self):
        """Test IT_TOOL_ORDER contains all required tools."""
        expected = {"alert_reader", "market_news", "market_data", "trader_profile", "trader_history"}
        assert set(IT_TOOL_ORDER) == expected

    def test_wt_tool_order_defined(self):
        """Test WT_TOOL_ORDER is properly exported."""
        assert WT_TOOL_ORDER is not None
        assert isinstance(WT_TOOL_ORDER, tuple)
        assert len(WT_TOOL_ORDER) == 7

    def test_wt_tool_order_contains_required_tools(self):
        """Test WT_TOOL_ORDER contains all required tools."""
        expected = {
            "alert_reader", "market_data", "trader_profile",
            "account_relationships", "related_accounts_history",
            "trade_timing", "counterparty_analysis"
        }
        assert set(WT_TOOL_ORDER) == expected


# =============================================================================
# Insider Trading Agent Tests
# =============================================================================

class TestDeterministicInsiderTradingAgent:
    """Tests for DeterministicInsiderTradingAgent."""

    def test_initialization(self, mock_tool_llm, test_data_dir: Path, tmp_path: Path):
        """Test agent initializes correctly."""
        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        assert agent.llm == mock_tool_llm
        assert agent.data_dir == test_data_dir
        assert agent.output_dir == tmp_path
        assert len(agent.tool_instances) == 5
        assert agent.few_shot_examples is not None

    def test_initialization_validates_tool_order(self, mock_tool_llm, test_data_dir: Path, tmp_path: Path):
        """Test agent validates tool order matches requirements."""
        # This should not raise since TOOL_ORDER matches INSIDER_TRADING_REQUIRED_TOOLS
        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )
        assert len(agent.tool_instances) == len(IT_TOOL_ORDER)

    def test_creates_all_tool_instances(self, mock_tool_llm, test_data_dir: Path, tmp_path: Path):
        """Test all required tools are instantiated."""
        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        for tool_name in IT_TOOL_ORDER:
            assert tool_name in agent.tool_instances
            assert agent.tool_instances[tool_name] is not None

    def test_analyze_validates_agent_type(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        wt_analysis_request: AnalysisRequest,
    ):
        """Test analyze rejects wrong agent_type."""
        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        with pytest.raises(ValueError) as exc_info:
            agent.analyze(wt_analysis_request)

        assert "Invalid agent_type" in str(exc_info.value)
        assert "wash_trade" in str(exc_info.value)

    def test_analyze_full_flow(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        it_analysis_request: AnalysisRequest,
        mock_it_decision: InsiderTradingDecision,
    ):
        """Test full analysis flow with mocked LLM."""
        # Configure mock LLM for structured output
        mock_structured_llm = MagicMock()
        mock_structured_llm.invoke.return_value = mock_it_decision
        mock_tool_llm.with_structured_output.return_value = mock_structured_llm

        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        decision = agent.analyze(it_analysis_request)

        assert decision.alert_id == "ITA-2024-TEST"
        assert decision.determination == "ESCALATE"
        assert decision.genuine_alert_confidence == 85

        # Verify tool LLM was called for each tool
        assert mock_tool_llm.invoke.call_count == 5  # Once per tool

        # Verify structured output was used for synthesis
        mock_tool_llm.with_structured_output.assert_called_once()

    def test_analyze_writes_decision_json(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        it_analysis_request: AnalysisRequest,
        mock_it_decision: InsiderTradingDecision,
    ):
        """Test analysis writes JSON decision file."""
        mock_structured_llm = MagicMock()
        mock_structured_llm.invoke.return_value = mock_it_decision
        mock_tool_llm.with_structured_output.return_value = mock_structured_llm

        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        agent.analyze(it_analysis_request)

        json_file = tmp_path / "decision_ITA-2024-TEST.json"
        assert json_file.exists()

        with open(json_file) as f:
            saved_decision = json.load(f)

        assert saved_decision["alert_id"] == "ITA-2024-TEST"
        assert saved_decision["determination"] == "ESCALATE"

    def test_analyze_writes_html_report(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        it_analysis_request: AnalysisRequest,
        mock_it_decision: InsiderTradingDecision,
    ):
        """Test analysis writes HTML report file."""
        mock_structured_llm = MagicMock()
        mock_structured_llm.invoke.return_value = mock_it_decision
        mock_tool_llm.with_structured_output.return_value = mock_structured_llm

        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        agent.analyze(it_analysis_request)

        html_file = tmp_path / "decision_ITA-2024-TEST.html"
        assert html_file.exists()

        content = html_file.read_text()
        assert "ITA-2024-TEST" in content
        assert "ESCALATE" in content

    def test_analyze_writes_audit_log(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        it_analysis_request: AnalysisRequest,
        mock_it_decision: InsiderTradingDecision,
    ):
        """Test analysis appends to audit log."""
        mock_structured_llm = MagicMock()
        mock_structured_llm.invoke.return_value = mock_it_decision
        mock_tool_llm.with_structured_output.return_value = mock_structured_llm

        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        agent.analyze(it_analysis_request)

        audit_file = tmp_path / "audit_log.jsonl"
        assert audit_file.exists()

        with open(audit_file) as f:
            lines = f.readlines()

        assert len(lines) >= 1
        audit_entry = json.loads(lines[-1])
        assert audit_entry["alert_id"] == "ITA-2024-TEST"
        assert audit_entry["agent_type"] == "deterministic_insider_trading"

    def test_get_tool_stats(self, mock_tool_llm, test_data_dir: Path, tmp_path: Path):
        """Test get_tool_stats returns valid statistics."""
        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        stats = agent.get_tool_stats()

        assert stats["agent_type"] == "deterministic_insider_trading"
        assert stats["tool_order"] == IT_TOOL_ORDER
        assert len(stats["tools"]) == 5


# =============================================================================
# Wash Trade Agent Tests
# =============================================================================

class TestDeterministicWashTradeAgent:
    """Tests for DeterministicWashTradeAgent."""

    def test_initialization(self, mock_tool_llm, test_data_dir: Path, tmp_path: Path):
        """Test agent initializes correctly."""
        agent = DeterministicWashTradeAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        assert agent.llm == mock_tool_llm
        assert agent.data_dir == test_data_dir
        assert agent.output_dir == tmp_path
        assert len(agent.tool_instances) == 7

    def test_creates_all_tool_instances(self, mock_tool_llm, test_data_dir: Path, tmp_path: Path):
        """Test all required tools are instantiated."""
        agent = DeterministicWashTradeAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        for tool_name in WT_TOOL_ORDER:
            assert tool_name in agent.tool_instances
            assert agent.tool_instances[tool_name] is not None

    def test_analyze_validates_agent_type(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        it_analysis_request: AnalysisRequest,
    ):
        """Test analyze rejects wrong agent_type."""
        agent = DeterministicWashTradeAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        with pytest.raises(ValueError) as exc_info:
            agent.analyze(it_analysis_request)

        assert "Invalid agent_type" in str(exc_info.value)
        assert "insider_trading" in str(exc_info.value)

    def test_analyze_full_flow(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        wt_analysis_request: AnalysisRequest,
        mock_wt_decision: WashTradeDecision,
    ):
        """Test full analysis flow with mocked LLM."""
        mock_structured_llm = MagicMock()
        mock_structured_llm.invoke.return_value = mock_wt_decision
        mock_tool_llm.with_structured_output.return_value = mock_structured_llm

        agent = DeterministicWashTradeAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        decision = agent.analyze(wt_analysis_request)

        assert decision.alert_id == "WTA-2024-TEST"
        assert decision.determination == "ESCALATE"
        assert decision.genuine_alert_confidence == 90

        # Verify tool LLM was called for each tool
        assert mock_tool_llm.invoke.call_count == 7  # Once per tool

    def test_analyze_writes_decision_json(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        wt_analysis_request: AnalysisRequest,
        mock_wt_decision: WashTradeDecision,
    ):
        """Test analysis writes JSON decision file."""
        mock_structured_llm = MagicMock()
        mock_structured_llm.invoke.return_value = mock_wt_decision
        mock_tool_llm.with_structured_output.return_value = mock_structured_llm

        agent = DeterministicWashTradeAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        agent.analyze(wt_analysis_request)

        json_file = tmp_path / "wash_trade_decision_WTA-2024-TEST.json"
        assert json_file.exists()

    def test_analyze_writes_html_report(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        wt_analysis_request: AnalysisRequest,
        mock_wt_decision: WashTradeDecision,
    ):
        """Test analysis writes HTML report file."""
        mock_structured_llm = MagicMock()
        mock_structured_llm.invoke.return_value = mock_wt_decision
        mock_tool_llm.with_structured_output.return_value = mock_structured_llm

        agent = DeterministicWashTradeAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        agent.analyze(wt_analysis_request)

        html_file = tmp_path / "wash_trade_decision_WTA-2024-TEST.html"
        assert html_file.exists()

    def test_get_tool_stats(self, mock_tool_llm, test_data_dir: Path, tmp_path: Path):
        """Test get_tool_stats returns valid statistics."""
        agent = DeterministicWashTradeAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        stats = agent.get_tool_stats()

        assert stats["agent_type"] == "deterministic_wash_trade"
        assert stats["tool_order"] == WT_TOOL_ORDER
        assert len(stats["tools"]) == 7


# =============================================================================
# Streaming Tests
# =============================================================================

class TestDeterministicAgentStreaming:
    """Tests for streaming analysis methods."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="EventMapper needs create_tool_started_event method")
    async def test_it_agent_streaming_emits_events(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        it_analysis_request: AnalysisRequest,
        mock_it_decision: InsiderTradingDecision,
    ):
        """Test streaming analysis emits expected events."""
        mock_structured_llm = MagicMock()
        mock_structured_llm.invoke.return_value = mock_it_decision
        mock_tool_llm.with_structured_output.return_value = mock_structured_llm

        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        events = []
        async for event in agent.astream_analyze(it_analysis_request, "test-task-1"):
            events.append(event)

        # Verify event types
        event_types = [e.event_type for e in events]

        # Should have analysis_started
        assert "analysis_started" in event_types

        # Should have tool_started and tool_completed for each tool
        for tool_name in IT_TOOL_ORDER:
            tool_started = [e for e in events if e.event_type == "tool_started" and tool_name in str(e.data)]
            tool_completed = [e for e in events if e.event_type == "tool_completed" and tool_name in str(e.data)]
            assert len(tool_started) >= 1, f"Missing tool_started for {tool_name}"
            assert len(tool_completed) >= 1, f"Missing tool_completed for {tool_name}"

        # Should have evaluation_started
        assert "evaluation_started" in event_types

        # Should have analysis_complete
        assert "analysis_complete" in event_types

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="EventMapper needs create_tool_started_event method")
    async def test_wt_agent_streaming_emits_events(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        wt_analysis_request: AnalysisRequest,
        mock_wt_decision: WashTradeDecision,
    ):
        """Test streaming analysis emits expected events for wash trade."""
        mock_structured_llm = MagicMock()
        mock_structured_llm.invoke.return_value = mock_wt_decision
        mock_tool_llm.with_structured_output.return_value = mock_structured_llm

        agent = DeterministicWashTradeAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        events = []
        async for event in agent.astream_analyze(wt_analysis_request, "test-task-2"):
            events.append(event)

        event_types = [e.event_type for e in events]

        assert "analysis_started" in event_types
        assert "evaluation_started" in event_types
        assert "analysis_complete" in event_types

        # Verify 7 tools were processed
        tool_completed_count = sum(1 for e in events if e.event_type == "tool_completed")
        assert tool_completed_count == 7

    @pytest.mark.asyncio
    async def test_streaming_invalid_agent_type_emits_error(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        wt_analysis_request: AnalysisRequest,
    ):
        """Test streaming emits error for wrong agent type."""
        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        with pytest.raises(ValueError):
            events = []
            async for event in agent.astream_analyze(wt_analysis_request, "test-task-err"):
                events.append(event)

            # Should have emitted error event before raising
            error_events = [e for e in events if e.event_type == "error"]
            assert len(error_events) >= 1


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestDeterministicAgentErrors:
    """Tests for error handling in deterministic agents."""

    def test_tool_execution_failure_propagates(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        it_analysis_request: AnalysisRequest,
    ):
        """Test that tool execution failures propagate up (fail-fast)."""
        # Make the tool LLM raise an exception
        mock_tool_llm.invoke.side_effect = RuntimeError("LLM API failure")

        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        with pytest.raises(RuntimeError) as exc_info:
            agent.analyze(it_analysis_request)

        assert "LLM API failure" in str(exc_info.value)

    def test_synthesis_failure_propagates(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
        it_analysis_request: AnalysisRequest,
    ):
        """Test that synthesis failure propagates (fail-fast)."""
        # Tool LLM works fine
        mock_response = MagicMock()
        mock_response.content = "Tool analysis complete"
        mock_tool_llm.invoke.return_value = mock_response

        # But structured output returns None (synthesis failure)
        mock_structured_llm = MagicMock()
        mock_structured_llm.invoke.return_value = None
        mock_tool_llm.with_structured_output.return_value = mock_structured_llm

        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        with pytest.raises(ValueError) as exc_info:
            agent.analyze(it_analysis_request)

        assert "LLM returned None" in str(exc_info.value)


# =============================================================================
# Format Insights Tests
# =============================================================================

class TestFormatInsights:
    """Tests for insight formatting methods."""

    def test_format_insights_preserves_order(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
    ):
        """Test that insights are formatted in TOOL_ORDER."""
        agent = DeterministicInsiderTradingAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        insights = {
            "trader_history": "History insight",
            "alert_reader": "Alert insight",
            "market_news": "News insight",
            "trader_profile": "Profile insight",
            "market_data": "Market insight",
        }

        formatted = agent._format_insights_for_prompt(insights)

        # Check that alert_reader appears before market_news
        # (according to IT_TOOL_ORDER)
        alert_pos = formatted.find("Alert Reader")
        news_pos = formatted.find("Market News")
        assert alert_pos < news_pos, "Insights not in TOOL_ORDER"

    def test_format_insights_converts_names(
        self,
        mock_tool_llm,
        test_data_dir: Path,
        tmp_path: Path,
    ):
        """Test that tool names are converted to title case."""
        agent = DeterministicWashTradeAgent(
            llm=mock_tool_llm,
            data_dir=test_data_dir,
            output_dir=tmp_path,
        )

        insights = {
            "account_relationships": "Relationship insight",
            "related_accounts_history": "History insight",
        }

        formatted = agent._format_insights_for_prompt(insights)

        assert "Account Relationships" in formatted
        assert "Related Accounts History" in formatted
        assert "account_relationships" not in formatted  # Raw name not in output
