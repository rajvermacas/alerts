"""Tests for AG-UI Protocol implementation.

This module tests the AG-UI event models, adapter, and router
for CopilotKit compatibility.
"""

import json
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from alerts.agui.events import (
    AGUIEventType,
    BaseAGUIEvent,
    CustomEvent,
    Message,
    MessagesSnapshotEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    StateDeltaEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    TextPart,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from alerts.agui.adapter import AGUIAdapter


class TestAGUIEventModels:
    """Test AG-UI event model creation and serialization."""

    def test_run_started_event(self):
        """Test RunStartedEvent creation and serialization."""
        run_id = str(uuid4())
        thread_id = str(uuid4())

        event = RunStartedEvent(
            run_id=run_id,
            thread_id=thread_id,
            metadata={"alert_file": "test.xml"},
        )

        assert event.type == AGUIEventType.RUN_STARTED
        assert event.run_id == run_id
        assert event.thread_id == thread_id
        assert event.metadata["alert_file"] == "test.xml"

        # Test serialization
        json_str = event.to_sse_data()
        data = json.loads(json_str)
        assert data["type"] == "RUN_STARTED"
        assert data["run_id"] == run_id

    def test_run_finished_event(self):
        """Test RunFinishedEvent creation."""
        run_id = str(uuid4())

        event = RunFinishedEvent(
            run_id=run_id,
            result={"determination": "ESCALATE", "confidence": 85},
        )

        assert event.type == AGUIEventType.RUN_FINISHED
        assert event.result["determination"] == "ESCALATE"

    def test_run_error_event(self):
        """Test RunErrorEvent creation."""
        run_id = str(uuid4())

        event = RunErrorEvent(
            run_id=run_id,
            error="Analysis failed: file not found",
            error_code="FILE_NOT_FOUND",
        )

        assert event.type == AGUIEventType.RUN_ERROR
        assert "file not found" in event.error
        assert event.error_code == "FILE_NOT_FOUND"

    def test_text_message_events(self):
        """Test text message event sequence."""
        run_id = str(uuid4())
        message_id = str(uuid4())

        start = TextMessageStartEvent(
            run_id=run_id,
            message_id=message_id,
            role="assistant",
        )

        content = TextMessageContentEvent(
            run_id=run_id,
            message_id=message_id,
            delta="Analyzing the alert...",
        )

        end = TextMessageEndEvent(
            run_id=run_id,
            message_id=message_id,
        )

        assert start.type == AGUIEventType.TEXT_MESSAGE_START
        assert content.type == AGUIEventType.TEXT_MESSAGE_CONTENT
        assert end.type == AGUIEventType.TEXT_MESSAGE_END
        assert start.message_id == content.message_id == end.message_id

    def test_tool_call_events(self):
        """Test tool call event sequence."""
        run_id = str(uuid4())
        tool_call_id = str(uuid4())

        start = ToolCallStartEvent(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name="trader_history",
        )

        end = ToolCallEndEvent(
            run_id=run_id,
            tool_call_id=tool_call_id,
            tool_name="trader_history",
            result="Found 247 historical trades...",
            duration_ms=1500,
        )

        assert start.type == AGUIEventType.TOOL_CALL_START
        assert end.type == AGUIEventType.TOOL_CALL_END
        assert start.tool_call_id == end.tool_call_id
        assert end.duration_ms == 1500

    def test_state_events(self):
        """Test state snapshot and delta events."""
        run_id = str(uuid4())

        snapshot = StateSnapshotEvent(
            run_id=run_id,
            state={
                "alert_file": "test.xml",
                "tools_completed": ["trader_history"],
                "determination": None,
            },
        )

        delta = StateDeltaEvent(
            run_id=run_id,
            delta=[
                {"op": "replace", "path": "/determination", "value": "ESCALATE"},
                {"op": "add", "path": "/tools_completed/-", "value": "market_news"},
            ],
        )

        assert snapshot.type == AGUIEventType.STATE_SNAPSHOT
        assert delta.type == AGUIEventType.STATE_DELTA
        assert len(delta.delta) == 2

    def test_step_events(self):
        """Test step started/finished events."""
        run_id = str(uuid4())
        step_id = str(uuid4())

        start = StepStartedEvent(
            run_id=run_id,
            step_name="evaluation",
            step_id=step_id,
            metadata={"stage": "final"},
        )

        end = StepFinishedEvent(
            run_id=run_id,
            step_name="evaluation",
            step_id=step_id,
            duration_ms=5000,
        )

        assert start.type == AGUIEventType.STEP_STARTED
        assert end.type == AGUIEventType.STEP_FINISHED
        assert start.step_id == end.step_id

    def test_custom_event(self):
        """Test custom event for extensions."""
        run_id = str(uuid4())

        event = CustomEvent(
            run_id=run_id,
            event_name="keep_alive",
            data={"message": "Processing..."},
        )

        assert event.type == AGUIEventType.CUSTOM
        assert event.event_name == "keep_alive"

    def test_message_model(self):
        """Test Message model with parts."""
        message = Message(
            role="assistant",
            parts=[
                TextPart(text="Here are the results:"),
            ],
        )

        assert message.role == "assistant"
        assert len(message.parts) == 1
        assert message.parts[0].text == "Here are the results:"


class TestAGUIAdapter:
    """Test AG-UI adapter for converting internal events."""

    @pytest.fixture
    def adapter(self):
        """Create a test adapter instance."""
        return AGUIAdapter(
            run_id="test-run-123",
            thread_id="test-thread-456",
        )

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
        assert agui_events[0].type == AGUIEventType.RUN_STARTED
        assert agui_events[1].type == AGUIEventType.STATE_SNAPSHOT

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
        assert AGUIEventType.TOOL_CALL_START in event_types
        assert AGUIEventType.TEXT_MESSAGE_START in event_types

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
        assert AGUIEventType.TOOL_CALL_END in event_types
        assert AGUIEventType.STATE_DELTA in event_types

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
        assert AGUIEventType.STATE_SNAPSHOT in event_types
        assert AGUIEventType.RUN_FINISHED in event_types

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
        assert agui_events[0].type == AGUIEventType.RUN_ERROR
        assert "Failed to load" in agui_events[0].error

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
        assert AGUIEventType.TOOL_CALL_START in event_types

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
        assert AGUIEventType.STEP_STARTED in event_types
        assert AGUIEventType.STATE_DELTA in event_types

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
        assert agui_events[0].type == AGUIEventType.CUSTOM
        assert agui_events[0].event_name == "unknown_event_type"

    def test_duration_tracking(self, adapter):
        """Test that tool durations are tracked correctly."""
        import time

        # Start tool
        adapter.convert_event({
            "event_type": "tool_started",
            "payload": {"tool_name": "peer_trades"},
            "agent": "insider_trading",
        })

        # Small delay to measure
        time.sleep(0.01)

        # End tool
        agui_events = adapter.convert_event({
            "event_type": "tool_completed",
            "payload": {"tool_name": "peer_trades", "summary": "Done"},
            "agent": "insider_trading",
        })

        # Find TOOL_CALL_END event
        tool_end = next(
            e for e in agui_events if e.type == AGUIEventType.TOOL_CALL_END
        )
        assert tool_end.duration_ms is not None
        assert tool_end.duration_ms >= 10  # At least 10ms


class TestAGUIEventSerialization:
    """Test that all events serialize correctly for SSE."""

    @pytest.mark.parametrize("event_class,kwargs", [
        (RunStartedEvent, {"run_id": "test", "metadata": {}}),
        (RunFinishedEvent, {"run_id": "test", "result": {}}),
        (RunErrorEvent, {"run_id": "test", "error": "test error"}),
        (TextMessageStartEvent, {"message_id": "msg-1", "role": "assistant"}),
        (TextMessageContentEvent, {"message_id": "msg-1", "delta": "test"}),
        (TextMessageEndEvent, {"message_id": "msg-1"}),
        (ToolCallStartEvent, {"tool_call_id": "tc-1", "tool_name": "test_tool"}),
        (ToolCallEndEvent, {"tool_call_id": "tc-1", "tool_name": "test_tool"}),
        (StateSnapshotEvent, {"state": {"key": "value"}}),
        (StateDeltaEvent, {"delta": [{"op": "add", "path": "/test", "value": 1}]}),
        (StepStartedEvent, {"step_name": "test", "step_id": "step-1"}),
        (StepFinishedEvent, {"step_name": "test", "step_id": "step-1"}),
        (CustomEvent, {"event_name": "test", "data": {}}),
    ])
    def test_event_serialization(self, event_class, kwargs):
        """Test that events serialize to valid JSON."""
        event = event_class(**kwargs)

        # Should not raise
        json_str = event.to_sse_data()

        # Should be valid JSON
        data = json.loads(json_str)

        # Should have type field
        assert "type" in data

        # Type should match
        assert data["type"] == event.type.value if hasattr(event.type, 'value') else event.type
