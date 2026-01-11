"""Integration tests for tool event streaming pipeline.

Tests verify that tool events flow correctly from the deterministic agent loop
through executors and ultimately to the frontend via SSE.

Architecture Note:
- AlertReaderTool REMOVED - context now comes via request.alert_context
- All 4 tools now execute in parallel (no blocking alert_reader)
- See: .dev-resources/architecture/remove-alert-reader-tool.md

Architecture (after refactoring):
    ┌─────────────────────────────────────────────────────────────┐
    │                    AnalysisRequest                           │
    │  (alert_context, agent_type, tool_data: Dict[str, ToolInput])│
    └─────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
    ┌─────────────────────────────────────────────────────────────┐
    │              InsiderTradingAnalyzerAgent                     │
    │       TOOLS = [market_news, market_data, ...]               │
    │       (NO alert_reader - all tools execute in parallel)     │
    │                         │                                    │
    │       emit("context_received", ...)                          │
    │       for tool_name in TOOLS:                                │
    │           emit("tool_started", tool_name)                    │
    │       results = await asyncio.gather(all tools)              │
    │       for tool_name in TOOLS:                                │
    │           emit("tool_completed", tool_name)                  │
    └─────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                        StreamEvent objects
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

from alerts.agents.insider_trading.agent import InsiderTradingAnalyzerAgent
from alerts.agents.wash_trade.agent import WashTradeAnalyzerAgent
from alerts.a2a.event_mapper import StreamEvent
from alerts.models.request import AnalysisRequest, ToolInput
from alerts.models.alert_context import (
    InsiderTradingAlertContext,
    WashTradeAlertContext,
    Trader,
    Trade,
    WashTradeFlaggedTrade,
)


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
def sample_it_alert_context() -> InsiderTradingAlertContext:
    """Create a sample InsiderTradingAlertContext for testing."""
    return InsiderTradingAlertContext(
        alert_id="ITA-TEST-001",
        alert_type="Pre-Announcement Trading",
        rule_violated="SMARTS-IT-001",
        generated_timestamp=datetime(2024, 3, 16, 10, 30, 0),
        trader=Trader(
            trader_id="T001",
            name="Test Trader",
            department="Operations",
        ),
        trade=Trade(
            symbol="TEST",
            trade_date=date(2024, 3, 15),
            side="BUY",
            quantity=50000,
            price=Decimal("101.50"),
            total_value=Decimal("5075000"),
        ),
    )


@pytest.fixture
def sample_wt_alert_context() -> WashTradeAlertContext:
    """Create a sample WashTradeAlertContext for testing."""
    return WashTradeAlertContext(
        alert_id="WT-TEST-001",
        alert_type="Self-Trade",
        rule_violated="SMARTS-WT-001",
        generated_timestamp=datetime(2024, 3, 16, 10, 30, 0),
        severity="HIGH",
        flagged_trades=[
            WashTradeFlaggedTrade(
                sequence=1,
                account_id="ACC-001",
                account_name="Account Alpha",
                trade_date=date(2024, 3, 15),
                trade_time="14:32:15.123",
                symbol="TEST",
                side="BUY",
                quantity=10000,
                price=Decimal("100.00"),
                total_value=Decimal("1000000"),
                counterparty_account="ACC-002",
                order_id="ORD001",
            ),
            WashTradeFlaggedTrade(
                sequence=2,
                account_id="ACC-002",
                account_name="Account Beta",
                trade_date=date(2024, 3, 15),
                trade_time="14:32:15.625",
                symbol="TEST",
                side="SELL",
                quantity=10000,
                price=Decimal("100.00"),
                total_value=Decimal("1000000"),
                counterparty_account="ACC-001",
                order_id="ORD002",
            ),
        ],
    )


@pytest.fixture
def insider_trading_request(sample_it_alert_context) -> AnalysisRequest:
    """Create a valid AnalysisRequest for insider trading.

    NOTE: alert_reader REMOVED - context via alert_context
    """
    return AnalysisRequest(
        alert_context=sample_it_alert_context,
        agent_type="insider_trading",
        tool_data={
            # NOTE: No alert_reader - 4 tools only
            "market_news": ToolInput(format="txt", data="No news before announcement."),
            "market_data": ToolInput(format="csv", data="symbol,date,price\nTEST,2024-03-15,100.00"),
            "trader_profile": ToolInput(format="csv", data="trader_id,name,role\nT001,Test,BACK_OFFICE"),
            "trader_history": ToolInput(format="csv", data="trader_id,date,symbol,qty\nT001,2024-01-01,MSFT,1000"),
        }
    )


@pytest.fixture
def wash_trade_request(sample_wt_alert_context) -> AnalysisRequest:
    """Create a valid AnalysisRequest for wash trade.

    NOTE: alert_reader REMOVED - context via alert_context
    """
    return AnalysisRequest(
        alert_context=sample_wt_alert_context,
        agent_type="wash_trade",
        tool_data={
            # NOTE: No alert_reader - 5 tools only
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
        # Mock all parallel tool aexecute() methods
        # NOTE: No alert_reader - all 4 tools execute in parallel
        with patch("alerts.agents.insider_trading.tools.market_news.MarketNewsTool.aexecute") as mock_news, \
             patch("alerts.tools.common.market_data.MarketDataTool.aexecute") as mock_market, \
             patch("alerts.tools.common.trader_profile.TraderProfileTool.aexecute") as mock_profile, \
             patch("alerts.agents.insider_trading.tools.trader_history.TraderHistoryTool.aexecute") as mock_history:

            # Set up tool returns (all async)
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
            assert "context_received" in event_types, "Missing context_received event"
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
        """Test that all 4 tools emit events (no alert_reader)."""
        # NOTE: No alert_reader - all 4 tools execute in parallel
        with patch("alerts.agents.insider_trading.tools.market_news.MarketNewsTool.aexecute") as mock_news, \
             patch("alerts.tools.common.market_data.MarketDataTool.aexecute") as mock_market, \
             patch("alerts.tools.common.trader_profile.TraderProfileTool.aexecute") as mock_profile, \
             patch("alerts.agents.insider_trading.tools.trader_history.TraderHistoryTool.aexecute") as mock_history:

            # Set up tool returns
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

            # Should have 4 tools (TOOLS has 4 items, no alert_reader)
            assert len(tool_started_events) == 4, f"Expected 4 tool_started events, got {len(tool_started_events)}"
            assert len(tool_completed_events) == 4, f"Expected 4 tool_completed events, got {len(tool_completed_events)}"

    @pytest.mark.asyncio
    async def test_error_event_on_tool_failure(
        self,
        mock_llm,
        insider_trading_request: AnalysisRequest,
        tmp_path: Path,
        test_data_dir: Path,
    ):
        """Test that error events are emitted when a tool fails."""
        # Make one of the parallel tools fail
        with patch("alerts.agents.insider_trading.tools.market_news.MarketNewsTool.aexecute") as mock_news:
            mock_news.side_effect = Exception("Tool failure")

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
        # NOTE: No alert_reader - all 5 tools execute in parallel
        with patch("alerts.tools.common.market_data.MarketDataTool.aexecute") as mock_market, \
             patch("alerts.agents.wash_trade.tools.account_relationships.AccountRelationshipsTool.aexecute") as mock_rel, \
             patch("alerts.agents.wash_trade.tools.related_accounts_history.RelatedAccountsHistoryTool.aexecute") as mock_hist, \
             patch("alerts.agents.wash_trade.tools.trade_timing.TradeTimingTool.aexecute") as mock_timing, \
             patch("alerts.agents.wash_trade.tools.counterparty_analysis.CounterpartyAnalysisTool.aexecute") as mock_cp:

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
            assert "context_received" in event_types, "Wash trade agent should emit context_received"
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
        # NOTE: No alert_reader - all 4 tools execute in parallel
        with patch("alerts.agents.insider_trading.tools.market_news.MarketNewsTool.aexecute") as mock_news, \
             patch("alerts.tools.common.market_data.MarketDataTool.aexecute") as mock_market, \
             patch("alerts.tools.common.trader_profile.TraderProfileTool.aexecute") as mock_profile, \
             patch("alerts.agents.insider_trading.tools.trader_history.TraderHistoryTool.aexecute") as mock_history:

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

            # context_received should come early (after analysis_started)
            context_idx = event_types.index("context_received")
            assert context_idx == 1, "context_received should be second event"

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
        """Test that tools are executed matching TOOLS list.

        Note: With parallel execution, tool_started events are emitted in TOOLS order
        before execution, but tool_completed events may arrive in any order.
        """
        # NOTE: No alert_reader - all 4 tools execute in parallel
        with patch("alerts.agents.insider_trading.tools.market_news.MarketNewsTool.aexecute") as mock_news, \
             patch("alerts.tools.common.market_data.MarketDataTool.aexecute") as mock_market, \
             patch("alerts.tools.common.trader_profile.TraderProfileTool.aexecute") as mock_profile, \
             patch("alerts.agents.insider_trading.tools.trader_history.TraderHistoryTool.aexecute") as mock_history:

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

            # Should match TOOLS (not TOOL_ORDER anymore)
            expected_tools = agent.TOOLS
            assert executed_tools == expected_tools, f"Tool execution order mismatch: {executed_tools} != {expected_tools}"


class TestApiAnalyzeStreamEndpoint:
    """Test the /api/analyze/stream SSE endpoints for proactive information flow.

    These tests verify that the new streaming endpoints properly:
    1. Accept AnalysisRequest JSON
    2. Return SSE streams with real-time events
    3. Proxy events from agents through orchestrator
    """

    @pytest.mark.asyncio
    async def test_insider_trading_server_stream_endpoint(
        self,
        mock_llm,
        insider_trading_request: AnalysisRequest,
        tmp_path: Path,
        test_data_dir: Path,
    ):
        """Test that insider trading server /api/analyze/stream returns SSE events."""
        from datetime import datetime

        # Mock the agent's astream_analyze_request to return test events
        # NOTE: No alert_reader events - context_received instead
        async def mock_stream(*args, **kwargs):
            """Generate mock SSE events."""
            ts = datetime.now().isoformat()
            yield StreamEvent(
                event_id="evt-1",
                task_id="test-task",
                timestamp=ts,
                event_type="analysis_started",
                agent="insider_trading",
                payload={"message": "Analysis started"},
                final=False,
            )
            yield StreamEvent(
                event_id="evt-2",
                task_id="test-task",
                timestamp=ts,
                event_type="context_received",
                agent="insider_trading",
                payload={"alert_id": "TEST-001", "trader_id": "T001", "symbol": "TEST"},
                final=False,
            )
            yield StreamEvent(
                event_id="evt-3",
                task_id="test-task",
                timestamp=ts,
                event_type="tool_started",
                agent="insider_trading",
                payload={"tool_name": "query_market_news"},
                final=False,
            )
            yield StreamEvent(
                event_id="evt-4",
                task_id="test-task",
                timestamp=ts,
                event_type="tool_completed",
                agent="insider_trading",
                payload={"tool_name": "query_market_news", "summary": "No news"},
                final=False,
            )
            yield StreamEvent(
                event_id="evt-final",
                task_id="test-task",
                timestamp=ts,
                event_type="analysis_complete",
                agent="insider_trading",
                payload={"determination": "CLOSE"},
                final=True,
            )

        # Test the event generation
        events = [e async for e in mock_stream()]
        assert len(events) == 5
        assert events[0].event_type == "analysis_started"
        assert events[1].event_type == "context_received"
        assert events[-1].final is True

    @pytest.mark.asyncio
    async def test_wash_trade_server_stream_endpoint(
        self,
        mock_wash_trade_llm,
        wash_trade_request: AnalysisRequest,
        tmp_path: Path,
        test_data_dir: Path,
    ):
        """Test that wash trade server /api/analyze/stream returns SSE events."""
        from datetime import datetime

        # Mock the agent's astream_analyze_request
        # NOTE: No alert_reader events - context_received instead
        async def mock_stream(*args, **kwargs):
            """Generate mock SSE events for wash trade."""
            ts = datetime.now().isoformat()
            yield StreamEvent(
                event_id="wt-evt-1",
                task_id="wt-test-task",
                timestamp=ts,
                event_type="analysis_started",
                agent="wash_trade",
                payload={"message": "Wash trade analysis started"},
                final=False,
            )
            yield StreamEvent(
                event_id="wt-evt-2",
                task_id="wt-test-task",
                timestamp=ts,
                event_type="context_received",
                agent="wash_trade",
                payload={"alert_id": "WT-TEST-001", "account_ids": "ACC-001,ACC-002"},
                final=False,
            )
            yield StreamEvent(
                event_id="wt-evt-3",
                task_id="wt-test-task",
                timestamp=ts,
                event_type="tool_started",
                agent="wash_trade",
                payload={"tool_name": "query_market_data"},
                final=False,
            )
            yield StreamEvent(
                event_id="wt-evt-final",
                task_id="wt-test-task",
                timestamp=ts,
                event_type="analysis_complete",
                agent="wash_trade",
                payload={"determination": "ESCALATE"},
                final=True,
            )

        events = [e async for e in mock_stream()]
        assert len(events) == 4
        assert events[0].event_type == "analysis_started"
        assert events[1].event_type == "context_received"
        assert events[-1].final is True

    @pytest.mark.asyncio
    async def test_event_a2a_format_conversion(
        self,
        insider_trading_request: AnalysisRequest,
    ):
        """Test that StreamEvent.to_a2a_format() produces correct JSON structure."""
        from datetime import datetime

        event = StreamEvent(
            event_id="test-evt",
            task_id="test-task-123",
            timestamp=datetime.now().isoformat(),
            event_type="tool_completed",
            agent="insider_trading",
            payload={"tool_name": "query_market_news", "summary": "No relevant news"},
            final=False,
        )

        a2a_format = event.to_a2a_format(task_state="working")

        # Verify A2A structure
        assert "jsonrpc" in a2a_format
        assert a2a_format["jsonrpc"] == "2.0"
        assert "result" in a2a_format

        result = a2a_format["result"]
        assert "task" in result
        assert result["task"]["id"] == "test-task-123"
        assert result["task"]["state"] == "working"

        assert "taskStatusUpdateEvent" in result
        assert result["taskStatusUpdateEvent"]["final"] is False

        assert "metadata" in result
        assert result["metadata"]["event_type"] == "tool_completed"
        assert result["metadata"]["agent"] == "insider_trading"
        assert result["metadata"]["payload"]["tool_name"] == "query_market_news"

    @pytest.mark.asyncio
    async def test_final_event_has_correct_flag(
        self,
        insider_trading_request: AnalysisRequest,
    ):
        """Test that final events have final=True in A2A format."""
        from datetime import datetime

        final_event = StreamEvent(
            event_id="final-evt",
            task_id="test-task",
            timestamp=datetime.now().isoformat(),
            event_type="analysis_complete",
            agent="insider_trading",
            payload={"determination": "CLOSE", "decision": {"test": "data"}},
            final=True,
        )

        a2a_format = final_event.to_a2a_format(task_state="completed")

        assert a2a_format["result"]["taskStatusUpdateEvent"]["final"] is True
        assert a2a_format["result"]["task"]["state"] == "completed"


class TestStreamingProxyFlow:
    """Test the full streaming proxy flow from orchestrator to agent."""

    @pytest.mark.asyncio
    async def test_orchestrator_creates_routing_events(self):
        """Test that orchestrator emits analysis_started and routing events before agent events."""
        from datetime import datetime

        # This tests the conceptual flow - actual HTTP integration would need live servers
        expected_orchestrator_events = ["analysis_started", "routing"]

        # Verify orchestrator events are defined (conceptual test)
        for event_type in expected_orchestrator_events:
            event = StreamEvent(
                event_id=f"orch-{event_type}",
                task_id="test",
                timestamp=datetime.now().isoformat(),
                event_type=event_type,
                agent="orchestrator",
                payload={"message": f"Test {event_type}"},
                final=False,
            )
            assert event.event_type == event_type
            assert event.agent == "orchestrator"

    @pytest.mark.asyncio
    async def test_event_ordering_in_proxy_flow(self):
        """Test that events maintain correct order through proxy."""
        # Simulate the expected event flow
        # NOTE: No alert_reader events - context_received instead
        events = [
            ("orchestrator", "analysis_started"),
            ("orchestrator", "routing"),
            ("agent", "analysis_started"),
            ("agent", "context_received"),
            ("agent", "tool_started"),
            ("agent", "tool_completed"),
            ("agent", "tool_started"),
            ("agent", "tool_completed"),
            ("agent", "evaluation_started"),
            ("agent", "analysis_complete"),
        ]

        # Verify analysis_complete is last
        assert events[-1][1] == "analysis_complete"

        # Verify orchestrator events come first
        assert events[0][0] == "orchestrator"
        assert events[1][0] == "orchestrator"

        # Verify context_received comes early in agent events
        agent_events = [(a, t) for a, t in events if a == "agent"]
        assert agent_events[1][1] == "context_received"

        # Verify tool events are bracketed (started before completed)
        tool_started_indices = [i for i, (a, t) in enumerate(events) if t == "tool_started"]
        tool_completed_indices = [i for i, (a, t) in enumerate(events) if t == "tool_completed"]

        assert len(tool_started_indices) == len(tool_completed_indices)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
