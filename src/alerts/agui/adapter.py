"""AG-UI Protocol Adapter.

This module provides an adapter that converts the existing StreamEvent/A2A
event format to AG-UI protocol events using the official AG-UI SDK.

The adapter uses ag_ui.core event types and ag_ui.encoder.EventEncoder
for proper SSE formatting.

The adapter maps:
- analysis_started -> RUN_STARTED
- tool_started -> TOOL_CALL_START + TEXT_MESSAGE_START
- tool_completed -> TOOL_CALL_END + TEXT_MESSAGE_END
- agent_thinking -> TEXT_MESSAGE_START/CONTENT/END
- evaluation_started -> STEP_STARTED
- analysis_complete -> RUN_FINISHED + STATE_SNAPSHOT
- error -> RUN_ERROR
- node_started/completed -> STEP_STARTED/FINISHED
"""

import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

# Import from official AG-UI SDK
from ag_ui.core import (
    BaseEvent,
    EventType,
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

logger = logging.getLogger(__name__)


class AGUIAdapter:
    """Adapter for converting internal events to AG-UI protocol format.

    This adapter bridges the existing StreamEvent/A2A event system with
    the AG-UI protocol using the official AG-UI SDK.

    Usage:
        adapter = AGUIAdapter(run_id="task-123", thread_id="thread-456")
        encoder = EventEncoder()

        # Convert and encode events
        for agui_event in adapter.convert_event(internal_event):
            yield encoder.encode(agui_event)
    """

    def __init__(
        self,
        run_id: str,
        thread_id: Optional[str] = None,
    ):
        """Initialize the AG-UI adapter.

        Args:
            run_id: Unique identifier for this run/task
            thread_id: Optional thread/conversation ID
        """
        self.run_id = run_id
        self.thread_id = thread_id or str(uuid4())
        self.logger = logging.getLogger(f"{__name__}.{run_id[:8]}")

        # Track state for event conversion
        self._tool_call_ids: Dict[str, str] = {}  # tool_name -> tool_call_id
        self._tool_start_times: Dict[str, datetime] = {}  # tool_call_id -> start_time
        self._step_ids: Dict[str, str] = {}  # step_name -> step_id
        self._step_start_times: Dict[str, datetime] = {}  # step_id -> start_time
        self._message_counter = 0

        # State accumulator for STATE_SNAPSHOT
        self._state: Dict[str, Any] = {
            "alert_file": None,
            "alert_type": None,
            "tools_completed": [],
            "determination": None,
            "confidence": None,
        }

    def _next_message_id(self) -> str:
        """Generate a unique message ID."""
        self._message_counter += 1
        return f"msg_{self.run_id[:8]}_{self._message_counter}"

    def convert_event(self, event: Dict[str, Any]) -> List[BaseEvent]:
        """Convert an internal event to AG-UI event(s).

        One internal event may produce multiple AG-UI events.

        Args:
            event: Internal StreamEvent or A2A event dictionary

        Returns:
            List of AG-UI BaseEvent objects
        """
        # Extract event from A2A wrapper if present
        if "result" in event:
            metadata = event.get("result", {}).get("metadata", {})
            event_type = metadata.get("event_type", "unknown")
            payload = metadata.get("payload", {})
            agent = metadata.get("agent", "unknown")
        else:
            event_type = event.get("event_type", "unknown")
            payload = event.get("payload", {})
            agent = event.get("agent", "unknown")

        self.logger.debug(f"Converting event: {event_type}")

        # Map event type to handler
        handlers = {
            "analysis_started": self._handle_analysis_started,
            "tool_started": self._handle_tool_started,
            "tool_completed": self._handle_tool_completed,
            "tool_progress": self._handle_tool_progress,
            "agent_thinking": self._handle_agent_thinking,
            "evaluation_started": self._handle_evaluation_started,
            "analysis_complete": self._handle_analysis_complete,
            "error": self._handle_error,
            "node_started": self._handle_node_started,
            "node_completed": self._handle_node_completed,
            "routing_started": self._handle_routing_started,
            "routing_completed": self._handle_routing_completed,
            "keep_alive": self._handle_keep_alive,
            "llm_started": self._handle_llm_started,
            "llm_completed": self._handle_llm_completed,
        }

        handler = handlers.get(event_type)
        if handler:
            return handler(payload, agent)

        # Unknown event type - emit as custom event
        self.logger.warning(f"Unknown event type: {event_type}")
        return [
            CustomEvent(
                type=EventType.CUSTOM,
                name=event_type,
                value=payload,
            )
        ]

    async def convert_stream(
        self,
        event_stream: AsyncIterator[Dict[str, Any]],
    ) -> AsyncIterator[BaseEvent]:
        """Convert a stream of internal events to AG-UI events.

        Args:
            event_stream: Async iterator of internal events

        Yields:
            AG-UI BaseEvent objects
        """
        async for event in event_stream:
            agui_events = self.convert_event(event)
            for agui_event in agui_events:
                yield agui_event

    def _handle_analysis_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle analysis_started -> RUN_STARTED."""
        alert_file = payload.get("alert_file", "unknown")
        self._state["alert_file"] = alert_file

        return [
            RunStartedEvent(
                type=EventType.RUN_STARTED,
                thread_id=self.thread_id,
                run_id=self.run_id,
            ),
            StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=self._state.copy(),
            ),
        ]

    def _handle_tool_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle tool_started -> TOOL_CALL_START + TEXT_MESSAGE_*."""
        tool_name = payload.get("tool_name", "unknown")
        message = payload.get("message", f"Starting {tool_name}...")

        # Generate tool call ID
        tool_call_id = str(uuid4())
        self._tool_call_ids[tool_name] = tool_call_id
        self._tool_start_times[tool_call_id] = datetime.now(timezone.utc)

        # Generate message ID
        message_id = self._next_message_id()

        return [
            ToolCallStartEvent(
                type=EventType.TOOL_CALL_START,
                tool_call_id=tool_call_id,
                tool_call_name=tool_name,
            ),
            TextMessageStartEvent(
                type=EventType.TEXT_MESSAGE_START,
                message_id=message_id,
                role="assistant",
            ),
            TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT,
                message_id=message_id,
                delta=message,
            ),
            TextMessageEndEvent(
                type=EventType.TEXT_MESSAGE_END,
                message_id=message_id,
            ),
        ]

    def _handle_tool_completed(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle tool_completed -> TOOL_CALL_END + STATE_DELTA."""
        tool_name = payload.get("tool_name", "unknown")
        summary = payload.get("summary", payload.get("output_summary", ""))

        # Get tool call ID
        tool_call_id = self._tool_call_ids.get(tool_name, str(uuid4()))

        # Update state
        self._state["tools_completed"].append(tool_name)

        events: List[BaseEvent] = [
            ToolCallEndEvent(
                type=EventType.TOOL_CALL_END,
                tool_call_id=tool_call_id,
                tool_call_name=tool_name,
                result=summary[:500] if summary else None,
            ),
        ]

        # Add text message if there's a summary
        if summary:
            message_id = self._next_message_id()
            events.extend([
                TextMessageStartEvent(
                    type=EventType.TEXT_MESSAGE_START,
                    message_id=message_id,
                    role="assistant",
                ),
                TextMessageContentEvent(
                    type=EventType.TEXT_MESSAGE_CONTENT,
                    message_id=message_id,
                    delta=f"**{tool_name}**: {summary[:300]}...",
                ),
                TextMessageEndEvent(
                    type=EventType.TEXT_MESSAGE_END,
                    message_id=message_id,
                ),
            ])

        # Add state delta
        events.append(
            StateDeltaEvent(
                type=EventType.STATE_DELTA,
                delta=[
                    {"op": "add", "path": "/tools_completed/-", "value": tool_name}
                ],
            )
        )

        return events

    def _handle_tool_progress(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle tool_progress -> TEXT_MESSAGE_*."""
        message = payload.get("message", "Processing...")
        message_id = self._next_message_id()

        return [
            TextMessageStartEvent(
                type=EventType.TEXT_MESSAGE_START,
                message_id=message_id,
                role="assistant",
            ),
            TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT,
                message_id=message_id,
                delta=message,
            ),
            TextMessageEndEvent(
                type=EventType.TEXT_MESSAGE_END,
                message_id=message_id,
            ),
        ]

    def _handle_agent_thinking(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle agent_thinking -> TEXT_MESSAGE_*."""
        message = payload.get("message", "Agent is analyzing...")
        message_id = self._next_message_id()

        return [
            TextMessageStartEvent(
                type=EventType.TEXT_MESSAGE_START,
                message_id=message_id,
                role="assistant",
            ),
            TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT,
                message_id=message_id,
                delta=f"*{message}*",
            ),
            TextMessageEndEvent(
                type=EventType.TEXT_MESSAGE_END,
                message_id=message_id,
            ),
        ]

    def _handle_evaluation_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle evaluation_started -> STEP_STARTED."""
        step_id = str(uuid4())
        self._step_ids["evaluation"] = step_id
        self._step_start_times[step_id] = datetime.now(timezone.utc)

        return [
            StepStartedEvent(
                type=EventType.STEP_STARTED,
                step_name="evaluation",
            ),
        ]

    def _handle_analysis_complete(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle analysis_complete -> STATE_SNAPSHOT + RUN_FINISHED."""
        determination = payload.get("determination", "UNKNOWN")
        confidence = payload.get("confidence", 0)
        summary = payload.get("summary", "")
        decision = payload.get("decision", {})

        # Update state
        self._state["determination"] = determination
        self._state["confidence"] = confidence
        if decision:
            self._state["decision"] = decision

        events: List[BaseEvent] = []

        # Finish evaluation step if started
        if "evaluation" in self._step_ids:
            events.append(
                StepFinishedEvent(
                    type=EventType.STEP_FINISHED,
                    step_name="evaluation",
                )
            )

        # Final message
        message_id = self._next_message_id()
        final_message = f"## Analysis Complete\n\n**Determination**: {determination}\n**Confidence**: {confidence}%"
        if summary:
            final_message += f"\n\n{summary}"

        events.extend([
            TextMessageStartEvent(
                type=EventType.TEXT_MESSAGE_START,
                message_id=message_id,
                role="assistant",
            ),
            TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT,
                message_id=message_id,
                delta=final_message,
            ),
            TextMessageEndEvent(
                type=EventType.TEXT_MESSAGE_END,
                message_id=message_id,
            ),
            StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot=self._state.copy(),
            ),
            RunFinishedEvent(
                type=EventType.RUN_FINISHED,
                thread_id=self.thread_id,
                run_id=self.run_id,
            ),
        ])

        return events

    def _handle_error(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle error -> RUN_ERROR."""
        error_message = payload.get("message", payload.get("error", "Unknown error"))

        return [
            RunErrorEvent(
                type=EventType.RUN_ERROR,
                message=error_message,
            )
        ]

    def _handle_node_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle node_started -> STEP_STARTED."""
        node_name = payload.get("node_name", "unknown")
        step_id = str(uuid4())
        self._step_ids[node_name] = step_id
        self._step_start_times[step_id] = datetime.now(timezone.utc)

        return [
            StepStartedEvent(
                type=EventType.STEP_STARTED,
                step_name=node_name,
            )
        ]

    def _handle_node_completed(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle node_completed -> STEP_FINISHED."""
        node_name = payload.get("node_name", "unknown")

        return [
            StepFinishedEvent(
                type=EventType.STEP_FINISHED,
                step_name=node_name,
            )
        ]

    def _handle_routing_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle routing_started -> STEP_STARTED + TEXT_MESSAGE_*."""
        alert_type = payload.get("alert_type", "unknown")
        self._state["alert_type"] = alert_type

        step_id = str(uuid4())
        self._step_ids["routing"] = step_id
        self._step_start_times[step_id] = datetime.now(timezone.utc)

        message_id = self._next_message_id()

        return [
            StepStartedEvent(
                type=EventType.STEP_STARTED,
                step_name="routing",
            ),
            TextMessageStartEvent(
                type=EventType.TEXT_MESSAGE_START,
                message_id=message_id,
                role="assistant",
            ),
            TextMessageContentEvent(
                type=EventType.TEXT_MESSAGE_CONTENT,
                message_id=message_id,
                delta=f"Detected **{alert_type}** alert. Routing to specialized agent...",
            ),
            TextMessageEndEvent(
                type=EventType.TEXT_MESSAGE_END,
                message_id=message_id,
            ),
            StateDeltaEvent(
                type=EventType.STATE_DELTA,
                delta=[{"op": "replace", "path": "/alert_type", "value": alert_type}],
            ),
        ]

    def _handle_routing_completed(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle routing_completed -> STEP_FINISHED."""
        return [
            StepFinishedEvent(
                type=EventType.STEP_FINISHED,
                step_name="routing",
            )
        ]

    def _handle_keep_alive(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle keep_alive -> CustomEvent."""
        return [
            CustomEvent(
                type=EventType.CUSTOM,
                name="keep_alive",
                value={"message": "Processing..."},
            )
        ]

    def _handle_llm_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle llm_started -> STEP_STARTED."""
        return [
            StepStartedEvent(
                type=EventType.STEP_STARTED,
                step_name="llm_call",
            )
        ]

    def _handle_llm_completed(
        self, payload: Dict[str, Any], agent: str
    ) -> List[BaseEvent]:
        """Handle llm_completed -> STEP_FINISHED."""
        return [
            StepFinishedEvent(
                type=EventType.STEP_FINISHED,
                step_name="llm_call",
            )
        ]

    def get_state(self) -> Dict[str, Any]:
        """Get the current state."""
        return self._state.copy()
