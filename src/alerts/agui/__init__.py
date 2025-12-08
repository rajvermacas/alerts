"""AG-UI Protocol Support for SMARTS Alert Analyzer.

This module provides AG-UI (Agent-User Interaction) protocol support,
enabling real-time streaming of agent events to frontend applications
compatible with CopilotKit and the AG-UI protocol.

AG-UI is an open, lightweight, event-based protocol that standardizes
how AI agents connect to user-facing applications.

This implementation uses the official AG-UI SDK packages:
- ag-ui-protocol: Core event types and encoder
- ag-ui-langgraph: LangGraph integration (optional)
- copilotkit: CopilotKit Python SDK (optional)

See: https://docs.ag-ui.com/introduction

Usage:
    # Using the AG-UI adapter with existing A2A events
    from alerts.agui import AGUIAdapter, EventEncoder

    adapter = AGUIAdapter(run_id="task-123")
    encoder = EventEncoder()

    for agui_event in adapter.convert_event(internal_event):
        yield encoder.encode(agui_event)

    # Using ag_ui_langgraph for direct LangGraph integration
    from alerts.agui import create_agui_langgraph_endpoint

    create_agui_langgraph_endpoint(app, agent.graph, "/agent")
"""

# Re-export from official AG-UI SDK via events module
from alerts.agui.events import (
    # Input model
    RunAgentInput,
    # Base event
    BaseEvent,
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
    # Encoder
    EventEncoder,
)

# Export adapter
from alerts.agui.adapter import AGUIAdapter

# Export router
from alerts.agui.router import router as agui_router

# Export LangGraph integration helpers
from alerts.agui.langgraph_integration import (
    create_agui_langgraph_endpoint,
    wrap_langgraph_agent,
    is_agui_langgraph_available,
)

__all__ = [
    # AG-UI SDK types
    "RunAgentInput",
    "BaseEvent",
    "EventType",
    "RunStartedEvent",
    "RunFinishedEvent",
    "RunErrorEvent",
    "StepStartedEvent",
    "StepFinishedEvent",
    "TextMessageStartEvent",
    "TextMessageContentEvent",
    "TextMessageEndEvent",
    "MessagesSnapshotEvent",
    "ToolCallStartEvent",
    "ToolCallArgsEvent",
    "ToolCallEndEvent",
    "StateSnapshotEvent",
    "StateDeltaEvent",
    "Message",
    "CustomEvent",
    "EventEncoder",
    # Adapter
    "AGUIAdapter",
    # Router
    "agui_router",
    # LangGraph integration
    "create_agui_langgraph_endpoint",
    "wrap_langgraph_agent",
    "is_agui_langgraph_available",
]
