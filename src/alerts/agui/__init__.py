"""AG-UI Protocol Support for SMARTS Alert Analyzer.

This module provides AG-UI (Agent-User Interaction) protocol support,
enabling real-time streaming of agent events to frontend applications
compatible with CopilotKit and the AG-UI protocol.

AG-UI is an open, lightweight, event-based protocol that standardizes
how AI agents connect to user-facing applications.

See: https://docs.ag-ui.com/introduction
"""

from alerts.agui.events import (
    AGUIEventType,
    BaseAGUIEvent,
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    StepStartedEvent,
    StepFinishedEvent,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    MessagesSnapshotEvent,
    ToolCallStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    StateSnapshotEvent,
    StateDeltaEvent,
    CustomEvent,
    Message,
    TextPart,
    ToolCallPart,
)
from alerts.agui.adapter import AGUIAdapter

__all__ = [
    # Event Types Enum
    "AGUIEventType",
    # Base Event
    "BaseAGUIEvent",
    # Lifecycle Events
    "RunStartedEvent",
    "RunFinishedEvent",
    "RunErrorEvent",
    "StepStartedEvent",
    "StepFinishedEvent",
    # Text Message Events
    "TextMessageStartEvent",
    "TextMessageContentEvent",
    "TextMessageEndEvent",
    "MessagesSnapshotEvent",
    # Tool Call Events
    "ToolCallStartEvent",
    "ToolCallArgsEvent",
    "ToolCallEndEvent",
    # State Events
    "StateSnapshotEvent",
    "StateDeltaEvent",
    # Special Events
    "CustomEvent",
    # Message Types
    "Message",
    "TextPart",
    "ToolCallPart",
    # Adapter
    "AGUIAdapter",
]
