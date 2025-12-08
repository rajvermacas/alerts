"""Tests for AG-UI Protocol implementation.

This module tests the AG-UI adapter that converts internal events
to AG-UI protocol format using the official AG-UI SDK.
"""

import pytest
from uuid import uuid4

# Import from official AG-UI SDK
from ag_ui.core import (
    EventType,
    BaseEvent,
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    StepStartedEvent,
    StepFinishedEvent,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    ToolCallStartEvent,
    ToolCallEndEvent,
    StateSnapshotEvent,
    StateDeltaEvent,
    CustomEvent,
)
from ag_ui.encoder import EventEncoder

from alerts.agui.adapter import AGUIAdapter
from alerts.agui.langgraph_integration import is_agui_langgraph_available


class TestAGUIAdapter:
    """Test AG-UI adapter for converting internal events."""

    @pytest.fixture
    def adapter(self):
        """Create a test adapter instance."""
        return AGUIAdapter(
            run_id="test-run-123",
            thread_id="test-thread-456",
        )

    @pytest.fixture
    def encoder(self):
        """Create a test encoder instance."""
        return EventEncoder()

    def test_convert_analysis_started(self, adapter):
        """Test conversion of analysis_started event."""
        internal_event = {
            "event_type": "analysis_started",
            "payload": {
                "alert_file": "test_data/alerts/alert_genuine.xml",
                "message": "Starting analysis...",
            },
            "agent": "insider_trading",
        }

        agui_events = adapter.convert_event(internal_event)

        # Should produce RUN_STARTED and STATE_SNAPSHOT
        assert len(agui_events) == 2
        assert agui_events[0].type == EventType.RUN_STARTED
        assert agui_events[1].type == EventType.STATE_SNAPSHOT

    def test_convert_tool_started(self, adapter):
        """Test conversion of tool_started event."""
        internal_event = {
            "event_type": "tool_started",
            "payload": {
                "tool_name": "trader_history",
                "message": "Starting trader_history...",
            },
            "agent": "insider_trading",
        }

        agui_events = adapter.convert_event(internal_event)

        # Should produce TOOL_CALL_START + TEXT_MESSAGE_*
        event_types = [e.type for e in agui_events]
        assert EventType.TOOL_CALL_START in event_types
        assert EventType.TEXT_MESSAGE_START in event_types

    def test_convert_tool_completed(self, adapter):
        """Test conversion of tool_completed event."""
        # First start the tool to register it
        adapter.convert_event({
            "event_type": "tool_started",
            "payload": {"tool_name": "trader_history"},
            "agent": "insider_trading",
        })

        internal_event = {
            "event_type": "tool_completed",
            "payload": {
                "tool_name": "trader_history",
                "summary": "Found 10x volume anomaly in healthcare sector",
                "message": "Completed trader_history",
            },
            "agent": "insider_trading",
        }

        agui_events = adapter.convert_event(internal_event)

        # Should produce TOOL_CALL_END + TEXT_MESSAGE_* + STATE_DELTA
        event_types = [e.type for e in agui_events]
        assert EventType.TOOL_CALL_END in event_types
        assert EventType.STATE_DELTA in event_types

        # Check state was updated
        assert "trader_history" in adapter._state["tools_completed"]

    def test_convert_analysis_complete(self, adapter):
        """Test conversion of analysis_complete event."""
        internal_event = {
            "event_type": "analysis_complete",
            "payload": {
                "determination": "ESCALATE",
                "confidence": 85,
                "summary": "High confidence insider trading detected",
                "decision": {
                    "alert_id": "TEST-001",
                    "determination": "ESCALATE",
                },
            },
            "agent": "insider_trading",
        }

        agui_events = adapter.convert_event(internal_event)

        # Should produce TEXT_MESSAGE_* + STATE_SNAPSHOT + RUN_FINISHED
        event_types = [e.type for e in agui_events]
        assert EventType.STATE_SNAPSHOT in event_types
        assert EventType.RUN_FINISHED in event_types

        # Check final state
        assert adapter._state["determination"] == "ESCALATE"

    def test_convert_error(self, adapter):
        """Test conversion of error event."""
        internal_event = {
            "event_type": "error",
            "payload": {
                "message": "Failed to load trader_history.csv",
                "stage": "data_loading",
            },
            "agent": "insider_trading",
        }

        agui_events = adapter.convert_event(internal_event)

        assert len(agui_events) == 1
        assert agui_events[0].type == EventType.RUN_ERROR

    def test_convert_a2a_wrapped_event(self, adapter):
        """Test conversion of A2A protocol wrapped events."""
        # A2A events have a nested structure
        a2a_event = {
            "jsonrpc": "2.0",
            "result": {
                "task": {"id": "task-123", "state": "working"},
                "taskStatusUpdateEvent": {
                    "task": {"id": "task-123", "state": "working"},
                    "final": False,
                },
                "metadata": {
                    "event_type": "tool_started",
                    "agent": "insider_trading",
                    "payload": {
                        "tool_name": "market_news",
                        "message": "Starting market_news...",
                    },
                },
            },
        }

        agui_events = adapter.convert_event(a2a_event)

        # Should extract and convert the tool_started event
        event_types = [e.type for e in agui_events]
        assert EventType.TOOL_CALL_START in event_types

    def test_convert_routing_events(self, adapter):
        """Test conversion of orchestrator routing events."""
        start_event = {
            "event_type": "routing_started",
            "payload": {
                "alert_type": "insider_trading",
                "target_agent": "http://localhost:10001",
            },
            "agent": "orchestrator",
        }

        agui_events = adapter.convert_event(start_event)

        # Should produce STEP_STARTED + TEXT_MESSAGE_* + STATE_DELTA
        event_types = [e.type for e in agui_events]
        assert EventType.STEP_STARTED in event_types
        assert EventType.STATE_DELTA in event_types

        # Check state
        assert adapter._state["alert_type"] == "insider_trading"

    def test_convert_unknown_event(self, adapter):
        """Test conversion of unknown event types."""
        internal_event = {
            "event_type": "unknown_event_type",
            "payload": {"data": "test"},
            "agent": "test",
        }

        agui_events = adapter.convert_event(internal_event)

        # Should produce CUSTOM event
        assert len(agui_events) == 1
        assert agui_events[0].type == EventType.CUSTOM


class TestEventEncoder:
    """Test that EventEncoder properly encodes events."""

    @pytest.fixture
    def encoder(self):
        """Create a test encoder instance."""
        return EventEncoder()

    def test_encode_run_started(self, encoder):
        """Test encoding RunStartedEvent."""
        event = RunStartedEvent(
            type=EventType.RUN_STARTED,
            thread_id="thread-123",
            run_id="run-456",
        )

        encoded = encoder.encode(event)

        # Should be a valid SSE format
        assert encoded is not None
        assert isinstance(encoded, (str, bytes))

    def test_encode_text_message(self, encoder):
        """Test encoding text message events."""
        message_id = str(uuid4())

        events = [
            TextMessageStartEvent(
                type=EventType.TEXT_MESSAGE_START,
                message_id=message_id,
                role="assistant",
            ),
            TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT,
                message_id=message_id,
                delta="Hello, world!",
            ),
            TextMessageEndEvent(
                type=EventType.TEXT_MESSAGE_END,
                message_id=message_id,
            ),
        ]

        for event in events:
            encoded = encoder.encode(event)
            assert encoded is not None

    def test_encode_tool_call(self, encoder):
        """Test encoding tool call events."""
        tool_call_id = str(uuid4())

        start = ToolCallStartEvent(
            type=EventType.TOOL_CALL_START,
            tool_call_id=tool_call_id,
            tool_call_name="trader_history",
        )

        end = ToolCallEndEvent(
            type=EventType.TOOL_CALL_END,
            tool_call_id=tool_call_id,
            tool_call_name="trader_history",
            result="Analysis complete",
        )

        for event in [start, end]:
            encoded = encoder.encode(event)
            assert encoded is not None

    def test_encode_state_events(self, encoder):
        """Test encoding state events."""
        snapshot = StateSnapshotEvent(
            type=EventType.STATE_SNAPSHOT,
            snapshot={"key": "value", "count": 42},
        )

        delta = StateDeltaEvent(
            type=EventType.STATE_DELTA,
            delta=[{"op": "add", "path": "/new_key", "value": "new_value"}],
        )

        for event in [snapshot, delta]:
            encoded = encoder.encode(event)
            assert encoded is not None


class TestLangGraphIntegration:
    """Test AG-UI LangGraph integration helpers."""

    def test_is_agui_langgraph_available(self):
        """Test that the availability check works."""
        # This should return a boolean
        result = is_agui_langgraph_available()
        assert isinstance(result, bool)


class TestAdapterWithEncoder:
    """Test adapter and encoder working together."""

    def test_full_analysis_flow(self):
        """Test a complete analysis flow through adapter and encoder."""
        adapter = AGUIAdapter(run_id="flow-test-123")
        encoder = EventEncoder()

        # Simulate analysis events
        events_sequence = [
            {
                "event_type": "analysis_started",
                "payload": {"alert_file": "test.xml"},
                "agent": "test",
            },
            {
                "event_type": "tool_started",
                "payload": {"tool_name": "alert_reader"},
                "agent": "test",
            },
            {
                "event_type": "tool_completed",
                "payload": {"tool_name": "alert_reader", "summary": "Alert parsed"},
                "agent": "test",
            },
            {
                "event_type": "analysis_complete",
                "payload": {
                    "determination": "CLOSE",
                    "confidence": 90,
                    "summary": "False positive detected",
                },
                "agent": "test",
            },
        ]

        all_encoded = []
        for event in events_sequence:
            agui_events = adapter.convert_event(event)
            for agui_event in agui_events:
                encoded = encoder.encode(agui_event)
                all_encoded.append(encoded)

        # Should have generated multiple encoded events
        assert len(all_encoded) > len(events_sequence)

        # Final state should reflect the complete analysis
        state = adapter.get_state()
        assert state["determination"] == "CLOSE"
        assert state["confidence"] == 90
        assert "alert_reader" in state["tools_completed"]
