"""AG-UI Protocol Event Models.

This module defines Pydantic models for all AG-UI protocol event types.
AG-UI defines ~17 standard event types for agent-to-frontend communication.

Event Categories:
1. Lifecycle Events: RUN_STARTED, RUN_FINISHED, RUN_ERROR, STEP_STARTED, STEP_FINISHED
2. Text Message Events: TEXT_MESSAGE_START, TEXT_MESSAGE_CONTENT, TEXT_MESSAGE_END, MESSAGES_SNAPSHOT
3. Tool Call Events: TOOL_CALL_START, TOOL_CALL_ARGS, TOOL_CALL_END
4. State Events: STATE_SNAPSHOT, STATE_DELTA
5. Special Events: RAW, CUSTOM

See: https://docs.ag-ui.com/sdk/python/core/events
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class AGUIEventType(str, Enum):
    """All AG-UI protocol event types."""

    # Lifecycle Events
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"

    # Text Message Events
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    MESSAGES_SNAPSHOT = "MESSAGES_SNAPSHOT"

    # Tool Call Events
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"

    # State Events
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    STATE_DELTA = "STATE_DELTA"

    # Special Events
    RAW = "RAW"
    CUSTOM = "CUSTOM"


class TextPart(BaseModel):
    """Text content part in a message."""

    type: Literal["text"] = "text"
    text: str = Field(description="The text content")


class ToolCallPart(BaseModel):
    """Tool call part in a message."""

    type: Literal["tool-call"] = "tool-call"
    tool_call_id: str = Field(description="Unique ID for this tool call")
    tool_name: str = Field(description="Name of the tool being called")
    args: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class ToolResultPart(BaseModel):
    """Tool result part in a message."""

    type: Literal["tool-result"] = "tool-result"
    tool_call_id: str = Field(description="ID of the tool call this result is for")
    result: str = Field(description="The result from the tool execution")


MessagePart = Union[TextPart, ToolCallPart, ToolResultPart]


class Message(BaseModel):
    """A message in the AG-UI conversation."""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique message ID")
    role: Literal["user", "assistant", "system", "tool"] = Field(
        description="Role of the message sender"
    )
    parts: List[MessagePart] = Field(
        default_factory=list, description="Content parts of the message"
    )
    created_at: Optional[str] = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp when message was created",
    )


class BaseAGUIEvent(BaseModel):
    """Base class for all AG-UI events.

    All events share common fields for identification and tracking.
    """

    type: AGUIEventType = Field(description="The event type")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp of the event",
    )
    run_id: Optional[str] = Field(default=None, description="Run/task ID this event belongs to")
    thread_id: Optional[str] = Field(default=None, description="Thread/conversation ID")

    def to_sse_data(self) -> str:
        """Convert event to SSE data format (JSON string)."""
        return self.model_dump_json()

    class Config:
        use_enum_values = True


# =============================================================================
# Lifecycle Events
# =============================================================================


class RunStartedEvent(BaseAGUIEvent):
    """Event emitted when an agent run starts.

    This is the first event in any agent execution.
    """

    type: Literal[AGUIEventType.RUN_STARTED] = AGUIEventType.RUN_STARTED
    run_id: str = Field(description="Unique ID for this run")
    thread_id: Optional[str] = Field(default=None, description="Thread ID if part of conversation")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata about the run"
    )


class RunFinishedEvent(BaseAGUIEvent):
    """Event emitted when an agent run completes successfully.

    This is the final event in a successful agent execution.
    """

    type: Literal[AGUIEventType.RUN_FINISHED] = AGUIEventType.RUN_FINISHED
    run_id: str = Field(description="ID of the completed run")
    result: Optional[Dict[str, Any]] = Field(
        default=None, description="Final result of the run"
    )


class RunErrorEvent(BaseAGUIEvent):
    """Event emitted when an agent run fails.

    Contains error details for debugging and display.
    """

    type: Literal[AGUIEventType.RUN_ERROR] = AGUIEventType.RUN_ERROR
    run_id: str = Field(description="ID of the failed run")
    error: str = Field(description="Error message")
    error_code: Optional[str] = Field(default=None, description="Error code if available")
    stack_trace: Optional[str] = Field(default=None, description="Stack trace for debugging")


class StepStartedEvent(BaseAGUIEvent):
    """Event emitted when a step/node in the agent graph starts."""

    type: Literal[AGUIEventType.STEP_STARTED] = AGUIEventType.STEP_STARTED
    step_name: str = Field(description="Name of the step/node starting")
    step_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique ID for this step"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Step metadata"
    )


class StepFinishedEvent(BaseAGUIEvent):
    """Event emitted when a step/node in the agent graph completes."""

    type: Literal[AGUIEventType.STEP_FINISHED] = AGUIEventType.STEP_FINISHED
    step_name: str = Field(description="Name of the completed step/node")
    step_id: str = Field(description="ID of the completed step")
    duration_ms: Optional[int] = Field(default=None, description="Duration in milliseconds")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Step completion metadata"
    )


# =============================================================================
# Text Message Events
# =============================================================================


class TextMessageStartEvent(BaseAGUIEvent):
    """Event emitted when a new text message begins streaming.

    Signals the start of a new message from the agent.
    """

    type: Literal[AGUIEventType.TEXT_MESSAGE_START] = AGUIEventType.TEXT_MESSAGE_START
    message_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique message ID"
    )
    role: Literal["assistant", "system"] = Field(
        default="assistant", description="Role of the message sender"
    )
    parent_message_id: Optional[str] = Field(
        default=None, description="ID of parent message if this is a reply"
    )


class TextMessageContentEvent(BaseAGUIEvent):
    """Event containing a chunk of text content.

    Multiple content events may be emitted for a single message
    to stream text progressively.
    """

    type: Literal[AGUIEventType.TEXT_MESSAGE_CONTENT] = AGUIEventType.TEXT_MESSAGE_CONTENT
    message_id: str = Field(description="ID of the message this content belongs to")
    delta: str = Field(description="The text content chunk")


class TextMessageEndEvent(BaseAGUIEvent):
    """Event emitted when a text message is complete.

    Signals that no more content will be added to this message.
    """

    type: Literal[AGUIEventType.TEXT_MESSAGE_END] = AGUIEventType.TEXT_MESSAGE_END
    message_id: str = Field(description="ID of the completed message")


class MessagesSnapshotEvent(BaseAGUIEvent):
    """Event containing a full snapshot of the message history.

    Used for synchronization, reconnection, and initial state.
    """

    type: Literal[AGUIEventType.MESSAGES_SNAPSHOT] = AGUIEventType.MESSAGES_SNAPSHOT
    messages: List[Message] = Field(
        default_factory=list, description="Full list of messages"
    )


# =============================================================================
# Tool Call Events
# =============================================================================


class ToolCallStartEvent(BaseAGUIEvent):
    """Event emitted when a tool call begins.

    Contains tool identification and initial metadata.
    """

    type: Literal[AGUIEventType.TOOL_CALL_START] = AGUIEventType.TOOL_CALL_START
    tool_call_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique ID for this tool call"
    )
    tool_name: str = Field(description="Name of the tool being called")
    parent_message_id: Optional[str] = Field(
        default=None, description="ID of the message that triggered this tool call"
    )


class ToolCallArgsEvent(BaseAGUIEvent):
    """Event containing tool call arguments.

    May be streamed progressively as arguments are determined.
    """

    type: Literal[AGUIEventType.TOOL_CALL_ARGS] = AGUIEventType.TOOL_CALL_ARGS
    tool_call_id: str = Field(description="ID of the tool call")
    delta: str = Field(description="JSON string fragment of arguments")


class ToolCallEndEvent(BaseAGUIEvent):
    """Event emitted when a tool call completes.

    Contains the tool result for display and further processing.
    """

    type: Literal[AGUIEventType.TOOL_CALL_END] = AGUIEventType.TOOL_CALL_END
    tool_call_id: str = Field(description="ID of the completed tool call")
    tool_name: str = Field(description="Name of the tool that was called")
    result: Optional[str] = Field(default=None, description="Result from the tool execution")
    error: Optional[str] = Field(default=None, description="Error message if tool failed")
    duration_ms: Optional[int] = Field(default=None, description="Duration in milliseconds")


# =============================================================================
# State Events
# =============================================================================


class StateSnapshotEvent(BaseAGUIEvent):
    """Event containing a full state snapshot.

    Used for synchronizing state between agent and frontend.
    """

    type: Literal[AGUIEventType.STATE_SNAPSHOT] = AGUIEventType.STATE_SNAPSHOT
    state: Dict[str, Any] = Field(description="Complete state object")
    snapshot_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique ID for this snapshot"
    )


class StateDeltaEvent(BaseAGUIEvent):
    """Event containing incremental state updates.

    Uses RFC 6902 JSON Patch format for efficient updates.
    """

    type: Literal[AGUIEventType.STATE_DELTA] = AGUIEventType.STATE_DELTA
    delta: List[Dict[str, Any]] = Field(
        description="JSON Patch operations (RFC 6902)"
    )


# =============================================================================
# Special Events
# =============================================================================


class RawEvent(BaseAGUIEvent):
    """Raw event for passthrough data.

    Used for data that doesn't fit other event types.
    """

    type: Literal[AGUIEventType.RAW] = AGUIEventType.RAW
    data: Any = Field(description="Raw event data")


class CustomEvent(BaseAGUIEvent):
    """Custom event for application-specific data.

    Allows extending the protocol with custom event types.
    """

    type: Literal[AGUIEventType.CUSTOM] = AGUIEventType.CUSTOM
    event_name: str = Field(description="Custom event name")
    data: Dict[str, Any] = Field(
        default_factory=dict, description="Custom event data"
    )


# Type alias for all event types
AGUIEvent = Union[
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
    RawEvent,
    CustomEvent,
]
