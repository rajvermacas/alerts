"""Integration tests for tool event streaming pipeline.

Tests verify that tool events flow correctly from the deterministic agent loop
through executors and ultimately to the frontend via SSE.

Architecture (after refactoring):
    ┌─────────────────────────────────────────────────────────────┐
    │                    AnalysisRequest                           │
    │  (alert_xml, agent_type, tool_data: Dict[str, ToolInput])    │
    └─────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
    ┌─────────────────────────────────────────────────────────────┐
    │              InsiderTradingAnalyzerAgent                     │
    │       TOOL_ORDER = [read_alert, market_news, ...]            │
    │                         │                                    │
    │       for tool_name in TOOL_ORDER:                           │
    │           emit("tool_started", tool_name)                    │
    │           insight = tool.execute(data, format)               │
    │           emit("tool_completed", tool_name)                  │
    └─────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                        StreamEvent objects
"""

import pytest
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

from alerts.agents.insider_trading.agent import InsiderTradingAnalyzerAgent
from alerts.agents.wash_trade.agent import WashTradeAnalyzerAgent
from alerts.a2a.event_mapper import StreamEvent
from alerts.models.request import AnalysisRequest, ToolInput


@pytest.fixture
def mock_llm(sample_insider_trading_decision):
    """Create a mock LLM for testing with valid InsiderTradingDecision."""
    mock = MagicMock()

    # Mock with_structured_output for synthesis step
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = sample_insider_trading_decision
    mock.with_structured_output.return_value = mock_structured

    return mock


@pytest.fixture
def mock_wash_trade_llm():
    """Create a mock LLM for wash trade testing with valid WashTradeDecision."""
    from alerts.models.wash_trade import (
        WashTradeDecision,
        RelationshipNetwork,
        RelationshipNode,
        RelationshipEdge,
        TimingPattern,
        CounterpartyPattern,
        TradeFlow,
        HistoricalPatternSummary,
    )

    mock = MagicMock()
    mock_structured = MagicMock()

    # Build a valid WashTradeDecision
    mock_decision = WashTradeDecision(
        alert_id="WT-TEST-001",
        alert_type="WASH_TRADE",
        determination="ESCALATE",
        genuine_alert_confidence=85,
        false_positive_confidence=15,
        key_findings=["Test wash trade finding"],
        favorable_indicators=["Test indicator"],
        risk_mitigating_factors=["Test factor"],
        reasoning_narrative=(
            "This case presents clear indicators of wash trading. "
            "The accounts share the same beneficial owner and trades were "
            "executed within milliseconds of each other with offsetting positions. "
            "There is no legitimate economic purpose identified for these trades."
        ),
        similar_precedent="wt_ex_001",
        recommended_action="ESCALATE",
        data_gaps=[],
        relationship_network=RelationshipNetwork(
            nodes=[
                RelationshipNode(
                    account_id="ACC-001",
                    beneficial_owner_id="BO-001",
                    beneficial_owner_name="Test Owner",
                    relationship_type="direct",
                    is_flagged=True
                ),
                RelationshipNode(
                    account_id="ACC-002",
                    beneficial_owner_id="BO-001",
                    beneficial_owner_name="Test Owner",
                    relationship_type="family_trust",
                    is_flagged=True
                ),
            ],
            edges=[
                RelationshipEdge(
                    from_account="ACC-001",
                    to_account="ACC-002",
                    edge_type="trade",
                    trade_details="10K TEST @ $100",
                    is_suspicious=True
                ),
            ],
            pattern_type="DIRECT_WASH",
            pattern_confidence=85,
            pattern_description="Direct wash trade between accounts with same beneficial owner"
        ),
        timing_patterns=TimingPattern(
            time_delta_ms=500,
            time_delta_description="500ms",
            market_phase="regular_session",
            liquidity_assessment="medium",
            is_pre_arranged=True,
            pre_arrangement_confidence=80,
            timing_analysis="Trades executed within 500ms suggest pre-arranged execution"
        ),
        counterparty_pattern=CounterpartyPattern(
            trade_flow=[
                TradeFlow(
                    sequence_number=1,
                    account_id="ACC-001",
                    side="BUY",
                    quantity=10000,
                    price=100.0,
                    timestamp="2024-03-15T10:00:00Z",
                    counterparty_account="ACC-002"
                ),
                TradeFlow(
                    sequence_number=2,
                    account_id="ACC-002",
                    side="SELL",
                    quantity=10000,
                    price=100.0,
                    timestamp="2024-03-15T10:00:00.500Z",
                    counterparty_account="ACC-001"
                ),
            ],
            is_circular=False,
            is_offsetting=True,
            same_beneficial_owner=True,
            intermediary_accounts=[],
            economic_purpose_identified=False,
            economic_purpose_description=None
        ),
        historical_patterns=HistoricalPatternSummary(
            pattern_count=5,
            time_window_days=30,
            average_frequency="0.17 per day",
            pattern_trend="stable",
            historical_analysis="Similar patterns detected 5 times in past 30 days"
        ),
        volume_impact_percentage=2.5,
        beneficial_ownership_match=True,
        economic_purpose_identified=False,
        regulatory_flags=["MAS_SFA_S199"]
    )

    mock_structured.invoke.return_value = mock_decision
    mock.with_structured_output.return_value = mock_structured

    return mock


@pytest.fixture
def insider_trading_request(sample_alert_xml) -> AnalysisRequest:
    """Create a valid AnalysisRequest for insider trading."""
    return AnalysisRequest(
        alert_xml=sample_alert_xml,
        agent_type="insider_trading",
        tool_data={
            "alert_reader": ToolInput(format="xml", data=sample_alert_xml),
            "market_news": ToolInput(format="txt", data="No news before announcement."),
            "market_data": ToolInput(format="csv", data="symbol,date,price\nTEST,2024-03-15,100.00"),
            "trader_profile": ToolInput(format="csv", data="trader_id,name,role\nT001,Test,BACK_OFFICE"),
            "trader_history": ToolInput(format="csv", data="trader_id,date,symbol,qty\nT001,2024-01-01,MSFT,1000"),
        }
    )


@pytest.fixture
def wash_trade_request() -> AnalysisRequest:
    """Create a valid AnalysisRequest for wash trade.

    The alert XML must contain the required fields for context extraction:
    - AccountID (at least one, can have multiple)
    - Symbol
    - TradeDate
    - TradeTime (optional, for timing analysis)
    - Quantity (optional)
    """
    alert_xml = """<?xml version="1.0" encoding="UTF-8"?>
<SmartsAlert>
    <AlertMetadata>
        <AlertID>WT-TEST-001</AlertID>
        <AlertType>WashTrade</AlertType>
    </AlertMetadata>
    <FlaggedTrades>
        <Trade sequence="1">
            <AccountID>ACC-001</AccountID>
            <TradeDate>2024-03-15</TradeDate>
            <TradeTime>14:32:15.123</TradeTime>
            <Symbol>TEST</Symbol>
            <Quantity>1000</Quantity>
        </Trade>
        <Trade sequence="2">
            <AccountID>ACC-002</AccountID>
            <TradeDate>2024-03-15</TradeDate>
            <TradeTime>14:32:15.625</TradeTime>
            <Symbol>TEST</Symbol>
            <Quantity>1000</Quantity>
        </Trade>
    </FlaggedTrades>
</SmartsAlert>"""

    return AnalysisRequest(
        alert_xml=alert_xml,
        agent_type="wash_trade",
        tool_data={
            "alert_reader": ToolInput(format="xml", data=alert_xml),
            "market_data": ToolInput(format="csv", data="symbol,date,price\nTEST,2024-03-15,100.00"),
            "account_relationships": ToolInput(format="csv", data="account_id,related_to,type\nACC-001,ACC-002,beneficial_owner"),
            "related_accounts_history": ToolInput(format="csv", data="account_id,date,symbol,qty\nACC-001,2024-01-01,TEST,1000"),
            "trade_timing": ToolInput(format="csv", data="trade_id,time_ms,account_id\nT1,100,ACC-001"),
            "counterparty_analysis": ToolInput(format="csv", data="account_id,counterparty_id,trade_count\nACC-001,ACC-002,45"),
        }
    )


class TestInsiderTradingAgentStreaming:
    """Test insider trading agent tool event streaming."""

    @pytest.mark.asyncio
    async def test_tool_events_are_yielded(
        self,
        mock_llm,
        insider_trading_request: AnalysisRequest,
        tmp_path: Path,
        test_data_dir: Path,
    ):
        """Test that tool events (tool_started, tool_completed) are yielded during streaming."""
        # Mock tool execute methods to avoid LLM calls within tools
        with patch("alerts.tools.common.alert_reader.AlertReaderTool.execute") as mock_alert, \
             patch("alerts.agents.insider_trading.tools.market_news.MarketNewsTool.execute") as mock_news, \
             patch("alerts.tools.common.market_data.MarketDataTool.execute") as mock_market, \
             patch("alerts.tools.common.trader_profile.TraderProfileTool.execute") as mock_profile, \
             patch("alerts.agents.insider_trading.tools.trader_history.TraderHistoryTool.execute") as mock_history:

            # Set up tool returns
            mock_alert.return_value = "Alert parsed: TEST-001"
            mock_news.return_value = "No news before announcement"
            mock_market.return_value = "Market stable"
            mock_profile.return_value = "Back office employee"
            mock_history.return_value = "Normal trading pattern"

            agent = InsiderTradingAnalyzerAgent(
                llm=mock_llm,
                data_dir=test_data_dir,
                output_dir=tmp_path,
            )

            # Collect events from streaming
            events: List[StreamEvent] = []
            async for event in agent.astream_analyze_request(insider_trading_request, "test-task-123"):
                events.append(event)
                print(f"Received event: {event.event_type}")

            # Verify tool events are present
            event_types = [e.event_type for e in events]

            assert "analysis_started" in event_types, "Missing analysis_started event"
            assert "tool_started" in event_types, "Missing tool_started event"
            assert "tool_completed" in event_types, "Missing tool_completed event"
            assert "analysis_complete" in event_types, "Missing analysis_complete event"

    @pytest.mark.asyncio
    async def test_all_tools_emit_events(
        self,
        mock_llm,
        insider_trading_request: AnalysisRequest,
        tmp_path: Path,
        test_data_dir: Path,
    ):
        """Test that all tools in TOOL_ORDER emit events."""
        with patch("alerts.tools.common.alert_reader.AlertReaderTool.execute") as mock_alert, \
             patch("alerts.agents.insider_trading.tools.market_news.MarketNewsTool.execute") as mock_news, \
             patch("alerts.tools.common.market_data.MarketDataTool.execute") as mock_market, \
             patch("alerts.tools.common.trader_profile.TraderProfileTool.execute") as mock_profile, \
             patch("alerts.agents.insider_trading.tools.trader_history.TraderHistoryTool.execute") as mock_history:

            # Set up tool returns
            mock_alert.return_value = "Alert parsed"
            mock_news.return_value = "News data"
            mock_market.return_value = "Market data"
            mock_profile.return_value = "Profile data"
            mock_history.return_value = "History data"

            agent = InsiderTradingAnalyzerAgent(
                llm=mock_llm,
                data_dir=test_data_dir,
                output_dir=tmp_path,
            )

            events: List[StreamEvent] = []
            async for event in agent.astream_analyze_request(insider_trading_request, "test-task-456"):
                events.append(event)

            # Count tool_started and tool_completed events
            tool_started_events = [e for e in events if e.event_type == "tool_started"]
            tool_completed_events = [e for e in events if e.event_type == "tool_completed"]

            # Should have 5 tools (TOOL_ORDER has 5 items)
            assert len(tool_started_events) == 5, f"Expected 5 tool_started events, got {len(tool_started_events)}"
            assert len(tool_completed_events) == 5, f"Expected 5 tool_completed events, got {len(tool_completed_events)}"

    @pytest.mark.asyncio
    async def test_error_event_on_tool_failure(
        self,
        mock_llm,
        insider_trading_request: AnalysisRequest,
        tmp_path: Path,
        test_data_dir: Path,
    ):
        """Test that error events are emitted when a tool fails."""
        with patch("alerts.tools.common.alert_reader.AlertReaderTool.execute") as mock_alert:
            # Make the first tool fail
            mock_alert.side_effect = Exception("Tool failure")

            agent = InsiderTradingAnalyzerAgent(
                llm=mock_llm,
                data_dir=test_data_dir,
                output_dir=tmp_path,
            )

            events: List[StreamEvent] = []
            with pytest.raises(Exception, match="Tool failure"):
                async for event in agent.astream_analyze_request(insider_trading_request, "test-task-err"):
                    events.append(event)

            # Should have emitted error event
            event_types = [e.event_type for e in events]
            assert "error" in event_types, "Missing error event on tool failure"


class TestWashTradeAgentStreaming:
    """Test wash trade agent tool event streaming."""

    @pytest.mark.asyncio
    async def test_wash_trade_tool_events(
        self,
        mock_wash_trade_llm,
        wash_trade_request: AnalysisRequest,
        tmp_path: Path,
        test_data_dir: Path,
    ):
        """Test that wash trade agent also yields tool events."""
        with patch("alerts.tools.common.alert_reader.AlertReaderTool.execute") as mock_alert, \
             patch("alerts.tools.common.market_data.MarketDataTool.execute") as mock_market, \
             patch("alerts.agents.wash_trade.tools.account_relationships.AccountRelationshipsTool.execute") as mock_rel, \
             patch("alerts.agents.wash_trade.tools.related_accounts_history.RelatedAccountsHistoryTool.execute") as mock_hist, \
             patch("alerts.agents.wash_trade.tools.trade_timing.TradeTimingTool.execute") as mock_timing, \
             patch("alerts.agents.wash_trade.tools.counterparty_analysis.CounterpartyAnalysisTool.execute") as mock_cp:

            mock_alert.return_value = "Alert parsed"
            mock_market.return_value = "Market data"
            mock_rel.return_value = "Relationships data"
            mock_hist.return_value = "History data"
            mock_timing.return_value = "Timing data"
            mock_cp.return_value = "Counterparty data"

            agent = WashTradeAnalyzerAgent(
                llm=mock_wash_trade_llm,
                data_dir=test_data_dir,
                output_dir=tmp_path,
            )

            events: List[StreamEvent] = []
            async for event in agent.astream_analyze_request(wash_trade_request, "test-wt-task"):
                events.append(event)

            event_types = [e.event_type for e in events]
            assert "tool_started" in event_types, "Wash trade agent should emit tool_started"
            assert "tool_completed" in event_types, "Wash trade agent should emit tool_completed"
            assert "analysis_complete" in event_types, "Wash trade agent should emit analysis_complete"


class TestEventOrdering:
    """Test that events are emitted in the correct order."""

    @pytest.mark.asyncio
    async def test_event_order(
        self,
        mock_llm,
        insider_trading_request: AnalysisRequest,
        tmp_path: Path,
        test_data_dir: Path,
    ):
        """Test that events flow in the correct sequence."""
        with patch("alerts.tools.common.alert_reader.AlertReaderTool.execute") as mock_alert, \
             patch("alerts.agents.insider_trading.tools.market_news.MarketNewsTool.execute") as mock_news, \
             patch("alerts.tools.common.market_data.MarketDataTool.execute") as mock_market, \
             patch("alerts.tools.common.trader_profile.TraderProfileTool.execute") as mock_profile, \
             patch("alerts.agents.insider_trading.tools.trader_history.TraderHistoryTool.execute") as mock_history:

            mock_alert.return_value = "Alert data"
            mock_news.return_value = "News data"
            mock_market.return_value = "Market data"
            mock_profile.return_value = "Profile data"
            mock_history.return_value = "History data"

            agent = InsiderTradingAnalyzerAgent(
                llm=mock_llm,
                data_dir=test_data_dir,
                output_dir=tmp_path,
            )

            events: List[StreamEvent] = []
            async for event in agent.astream_analyze_request(insider_trading_request, "test-order"):
                events.append(event)

            event_types = [e.event_type for e in events]

            # analysis_started should be first
            assert event_types[0] == "analysis_started", "First event should be analysis_started"

            # tool events should come before analysis_complete
            tool_started_indices = [i for i, t in enumerate(event_types) if t == "tool_started"]
            analysis_complete_index = event_types.index("analysis_complete") if "analysis_complete" in event_types else len(event_types)

            for idx in tool_started_indices:
                assert idx < analysis_complete_index, "Tool events should come before analysis_complete"

            # evaluation_started should come after all tool_completed and before analysis_complete
            if "evaluation_started" in event_types:
                eval_index = event_types.index("evaluation_started")
                tool_completed_indices = [i for i, t in enumerate(event_types) if t == "tool_completed"]
                for tc_idx in tool_completed_indices:
                    assert tc_idx < eval_index, "All tool_completed events should come before evaluation_started"
                assert eval_index < analysis_complete_index, "evaluation_started should come before analysis_complete"

    @pytest.mark.asyncio
    async def test_tool_order_matches_definition(
        self,
        mock_llm,
        insider_trading_request: AnalysisRequest,
        tmp_path: Path,
        test_data_dir: Path,
    ):
        """Test that tools are executed in the order defined by TOOL_ORDER."""
        with patch("alerts.tools.common.alert_reader.AlertReaderTool.execute") as mock_alert, \
             patch("alerts.agents.insider_trading.tools.market_news.MarketNewsTool.execute") as mock_news, \
             patch("alerts.tools.common.market_data.MarketDataTool.execute") as mock_market, \
             patch("alerts.tools.common.trader_profile.TraderProfileTool.execute") as mock_profile, \
             patch("alerts.agents.insider_trading.tools.trader_history.TraderHistoryTool.execute") as mock_history:

            mock_alert.return_value = "Alert data"
            mock_news.return_value = "News data"
            mock_market.return_value = "Market data"
            mock_profile.return_value = "Profile data"
            mock_history.return_value = "History data"

            agent = InsiderTradingAnalyzerAgent(
                llm=mock_llm,
                data_dir=test_data_dir,
                output_dir=tmp_path,
            )

            events: List[StreamEvent] = []
            async for event in agent.astream_analyze_request(insider_trading_request, "test-order-check"):
                events.append(event)

            # Extract tool names from tool_started events (using payload attribute)
            tool_started_events = [e for e in events if e.event_type == "tool_started"]
            executed_tools = [e.payload.get("tool_name") for e in tool_started_events]

            # Should match TOOL_ORDER
            expected_order = agent.TOOL_ORDER
            assert executed_tools == expected_order, f"Tool execution order mismatch: {executed_tools} != {expected_order}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
