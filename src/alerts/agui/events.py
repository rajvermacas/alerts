"""AG-UI Protocol Event Types.

This module re-exports AG-UI event types from the official ag_ui.core SDK.
It also provides type aliases for convenience.

The AG-UI protocol defines ~17 standard event types for agent-frontend communication.

Event Categories:
1. Lifecycle Events: RUN_STARTED, RUN_FINISHED, RUN_ERROR, STEP_STARTED, STEP_FINISHED
2. Text Message Events: TEXT_MESSAGE_START, TEXT_MESSAGE_CONTENT, TEXT_MESSAGE_END
3. Tool Call Events: TOOL_CALL_START, TOOL_CALL_ARGS, TOOL_CALL_END
4. State Events: STATE_SNAPSHOT, STATE_DELTA
5. Special Events: RAW, CUSTOM

See: https://docs.ag-ui.com/sdk/python/core/events
"""

# Re-export from official AG-UI SDK
from ag_ui.core import (
    # Input model for agent runs
    RunAgentInput,
    # Base event class
    BaseEvent,
    # Event type enum
    EventType,
    # Lifecycle events
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    StepStartedEvent,
    StepFinishedEvent,
    # Text message events
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    MessagesSnapshotEvent,
    # Tool call events
    ToolCallStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    # State events
    StateSnapshotEvent,
    StateDeltaEvent,
    # Message types
    Message,
    # Custom event
    CustomEvent,
)

# Re-export EventEncoder from ag_ui.encoder
from ag_ui.encoder import EventEncoder

__all__ = [
    # Input model
    "RunAgentInput",
    # Base
    "BaseEvent",
    "EventType",
    # Lifecycle
    "RunStartedEvent",
    "RunFinishedEvent",
    "RunErrorEvent",
    "StepStartedEvent",
    "StepFinishedEvent",
    # Text messages
    "TextMessageStartEvent",
    "TextMessageContentEvent",
    "TextMessageEndEvent",
    "MessagesSnapshotEvent",
    # Tool calls
    "ToolCallStartEvent",
    "ToolCallArgsEvent",
    "ToolCallEndEvent",
    # State
    "StateSnapshotEvent",
    "StateDeltaEvent",
    # Messages
    "Message",
    # Special
    "CustomEvent",
    # Encoder
    "EventEncoder",
]
