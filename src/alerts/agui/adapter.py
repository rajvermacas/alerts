"""AG-UI Protocol Adapter.

This module provides an adapter that converts the existing StreamEvent/A2A
event format to AG-UI protocol events, enabling integration with CopilotKit
and other AG-UI compatible frontends.

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

import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from alerts.agui.events import (
    AGUIEvent,
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
    ToolResultPart,
)

logger = logging.getLogger(__name__)


class AGUIAdapter:
    """Adapter for converting internal events to AG-UI protocol format.

    This adapter bridges the existing StreamEvent/A2A event system with
    the AG-UI protocol, enabling real-time streaming to CopilotKit and
    other AG-UI compatible frontends.

    Usage:
        adapter = AGUIAdapter(run_id="task-123", thread_id="thread-456")

        # Convert a single event
        agui_events = adapter.convert_event(internal_event)

        # Or use as an async generator
        async for agui_event in adapter.convert_stream(internal_event_stream):
            yield agui_event.to_sse_data()
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
        self._messages: List[Message] = []
        self._current_message_id: Optional[str] = None
        self._tool_call_ids: Dict[str, str] = {}  # tool_name -> tool_call_id
        self._tool_start_times: Dict[str, datetime] = {}  # tool_call_id -> start_time
        self._step_ids: Dict[str, str] = {}  # step_name -> step_id
        self._step_start_times: Dict[str, datetime] = {}  # step_id -> start_time

        # State accumulator for STATE_SNAPSHOT
        self._state: Dict[str, Any] = {
            "alert_file": None,
            "alert_type": None,
            "tools_completed": [],
            "determination": None,
            "confidence": None,
        }

    def convert_event(self, event: Dict[str, Any]) -> List[AGUIEvent]:
        """Convert an internal event to AG-UI event(s).

        One internal event may produce multiple AG-UI events.
        For example, a tool_completed event produces:
        - TOOL_CALL_END
        - TEXT_MESSAGE_START (for the result)
        - TEXT_MESSAGE_CONTENT
        - TEXT_MESSAGE_END

        Args:
            event: Internal StreamEvent or A2A event dictionary

        Returns:
            List of AG-UI events (may be empty if event should be skipped)
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
                run_id=self.run_id,
                thread_id=self.thread_id,
                event_name=event_type,
                data=payload,
            )
        ]

    async def convert_stream(
        self,
        event_stream: AsyncIterator[Dict[str, Any]],
    ) -> AsyncIterator[AGUIEvent]:
        """Convert a stream of internal events to AG-UI events.

        Args:
            event_stream: Async iterator of internal events

        Yields:
            AG-UI events
        """
        async for event in event_stream:
            agui_events = self.convert_event(event)
            for agui_event in agui_events:
                yield agui_event

    def _handle_analysis_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle analysis_started -> RUN_STARTED."""
        alert_file = payload.get("alert_file", "unknown")
        self._state["alert_file"] = alert_file

        return [
            RunStartedEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                metadata={
                    "alert_file": alert_file,
                    "agent": agent,
                    "message": payload.get("message", f"Starting analysis of {alert_file}"),
                },
            ),
            # Also send initial state snapshot
            StateSnapshotEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                state=self._state.copy(),
            ),
        ]

    def _handle_tool_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle tool_started -> TOOL_CALL_START + TEXT_MESSAGE_START."""
        tool_name = payload.get("tool_name", "unknown")
        message = payload.get("message", f"Starting {tool_name}...")

        # Generate tool call ID
        tool_call_id = str(uuid4())
        self._tool_call_ids[tool_name] = tool_call_id
        self._tool_start_times[tool_call_id] = datetime.now(timezone.utc)

        # Generate message ID for progress text
        message_id = str(uuid4())
        self._current_message_id = message_id

        return [
            ToolCallStartEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
            ),
            TextMessageStartEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
                role="assistant",
            ),
            TextMessageContentEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
                delta=message,
            ),
            TextMessageEndEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
            ),
        ]

    def _handle_tool_completed(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle tool_completed -> TOOL_CALL_END + TEXT_MESSAGE_*."""
        tool_name = payload.get("tool_name", "unknown")
        summary = payload.get("summary", payload.get("output_summary", ""))
        message = payload.get("message", f"Completed {tool_name}")

        # Get or generate tool call ID
        tool_call_id = self._tool_call_ids.get(tool_name, str(uuid4()))

        # Calculate duration if we have start time
        duration_ms = None
        if tool_call_id in self._tool_start_times:
            start_time = self._tool_start_times.pop(tool_call_id)
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        # Update state
        self._state["tools_completed"].append(tool_name)

        events: List[AGUIEvent] = [
            ToolCallEndEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                result=summary[:500] if summary else None,  # Truncate long results
                duration_ms=duration_ms,
            ),
        ]

        # Add text message for the result if there's a summary
        if summary:
            message_id = str(uuid4())
            events.extend([
                TextMessageStartEvent(
                    run_id=self.run_id,
                    thread_id=self.thread_id,
                    message_id=message_id,
                    role="assistant",
                ),
                TextMessageContentEvent(
                    run_id=self.run_id,
                    thread_id=self.thread_id,
                    message_id=message_id,
                    delta=f"**{tool_name}**: {summary[:300]}...",
                ),
                TextMessageEndEvent(
                    run_id=self.run_id,
                    thread_id=self.thread_id,
                    message_id=message_id,
                ),
            ])

        # Add state delta
        events.append(
            StateDeltaEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                delta=[
                    {
                        "op": "add",
                        "path": f"/tools_completed/-",
                        "value": tool_name,
                    }
                ],
            )
        )

        return events

    def _handle_tool_progress(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle tool_progress -> TEXT_MESSAGE_*."""
        stage = payload.get("stage", "processing")
        message = payload.get("message", f"Processing: {stage}")

        message_id = str(uuid4())

        return [
            TextMessageStartEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
                role="assistant",
            ),
            TextMessageContentEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
                delta=message,
            ),
            TextMessageEndEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
            ),
        ]

    def _handle_agent_thinking(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle agent_thinking -> TEXT_MESSAGE_*."""
        message = payload.get("message", "Agent is analyzing...")
        context = payload.get("context", "")

        message_id = str(uuid4())

        return [
            TextMessageStartEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
                role="assistant",
            ),
            TextMessageContentEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
                delta=f"*{message}*",  # Italicize thinking
            ),
            TextMessageEndEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
            ),
        ]

    def _handle_evaluation_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle evaluation_started -> STEP_STARTED."""
        step_id = str(uuid4())
        self._step_ids["evaluation"] = step_id
        self._step_start_times[step_id] = datetime.now(timezone.utc)

        return [
            StepStartedEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                step_name="evaluation",
                step_id=step_id,
                metadata={
                    "message": payload.get("message", "Generating final determination..."),
                    "stage": payload.get("stage", "evaluation"),
                },
            ),
        ]

    def _handle_analysis_complete(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle analysis_complete -> STEP_FINISHED + STATE_SNAPSHOT + RUN_FINISHED."""
        determination = payload.get("determination", "UNKNOWN")
        confidence = payload.get("confidence", 0)
        summary = payload.get("summary", "")
        decision = payload.get("decision", {})

        # Update state
        self._state["determination"] = determination
        self._state["confidence"] = confidence
        if decision:
            self._state["decision"] = decision

        events: List[AGUIEvent] = []

        # Finish evaluation step if started
        eval_step_id = self._step_ids.get("evaluation")
        if eval_step_id:
            duration_ms = None
            if eval_step_id in self._step_start_times:
                start_time = self._step_start_times.pop(eval_step_id)
                duration_ms = int(
                    (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                )

            events.append(
                StepFinishedEvent(
                    run_id=self.run_id,
                    thread_id=self.thread_id,
                    step_name="evaluation",
                    step_id=eval_step_id,
                    duration_ms=duration_ms,
                    metadata={"determination": determination},
                )
            )

        # Add final text message
        message_id = str(uuid4())
        final_message = f"## Analysis Complete\n\n**Determination**: {determination}\n**Confidence**: {confidence}%"
        if summary:
            final_message += f"\n\n{summary}"

        events.extend([
            TextMessageStartEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
                role="assistant",
            ),
            TextMessageContentEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
                delta=final_message,
            ),
            TextMessageEndEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
            ),
        ])

        # Add final state snapshot
        events.append(
            StateSnapshotEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                state=self._state.copy(),
            )
        )

        # Add run finished
        events.append(
            RunFinishedEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                result={
                    "determination": determination,
                    "confidence": confidence,
                    "summary": summary,
                    "decision": decision,
                },
            )
        )

        return events

    def _handle_error(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle error -> RUN_ERROR."""
        error_message = payload.get("message", payload.get("error", "Unknown error"))
        stage = payload.get("stage", "unknown")
        tool_name = payload.get("tool_name")

        return [
            RunErrorEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                error=error_message,
                error_code=f"{agent}:{stage}" if stage else agent,
                stack_trace=None,  # Don't expose stack traces
            )
        ]

    def _handle_node_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle node_started -> STEP_STARTED."""
        node_name = payload.get("node_name", "unknown")
        step_id = str(uuid4())
        self._step_ids[node_name] = step_id
        self._step_start_times[step_id] = datetime.now(timezone.utc)

        return [
            StepStartedEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                step_name=node_name,
                step_id=step_id,
                metadata={"message": payload.get("message", f"Starting {node_name}")},
            )
        ]

    def _handle_node_completed(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle node_completed -> STEP_FINISHED."""
        node_name = payload.get("node_name", "unknown")
        step_id = self._step_ids.get(node_name, str(uuid4()))

        duration_ms = None
        if step_id in self._step_start_times:
            start_time = self._step_start_times.pop(step_id)
            duration_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

        return [
            StepFinishedEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                step_name=node_name,
                step_id=step_id,
                duration_ms=duration_ms,
                metadata={"message": payload.get("message", f"Completed {node_name}")},
            )
        ]

    def _handle_routing_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle routing_started -> STEP_STARTED + TEXT_MESSAGE_*."""
        alert_type = payload.get("alert_type", "unknown")
        target_agent = payload.get("target_agent", "unknown")

        self._state["alert_type"] = alert_type

        step_id = str(uuid4())
        self._step_ids["routing"] = step_id
        self._step_start_times[step_id] = datetime.now(timezone.utc)

        message_id = str(uuid4())

        return [
            StepStartedEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                step_name="routing",
                step_id=step_id,
                metadata={
                    "alert_type": alert_type,
                    "target_agent": target_agent,
                },
            ),
            TextMessageStartEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
                role="assistant",
            ),
            TextMessageContentEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
                delta=f"Detected **{alert_type}** alert. Routing to specialized agent...",
            ),
            TextMessageEndEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                message_id=message_id,
            ),
            StateDeltaEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                delta=[
                    {"op": "replace", "path": "/alert_type", "value": alert_type},
                ],
            ),
        ]

    def _handle_routing_completed(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle routing_completed -> STEP_FINISHED."""
        step_id = self._step_ids.get("routing", str(uuid4()))

        duration_ms = None
        if step_id in self._step_start_times:
            start_time = self._step_start_times.pop(step_id)
            duration_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

        return [
            StepFinishedEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                step_name="routing",
                step_id=step_id,
                duration_ms=duration_ms,
                metadata={"target_agent": payload.get("target_agent")},
            )
        ]

    def _handle_keep_alive(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle keep_alive -> CustomEvent (for compatibility)."""
        # AG-UI doesn't have a specific keep-alive event type
        # Use CUSTOM to maintain connection
        return [
            CustomEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                event_name="keep_alive",
                data={"message": "Processing..."},
            )
        ]

    def _handle_llm_started(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle llm_started -> STEP_STARTED."""
        model = payload.get("model", "llm")
        step_id = str(uuid4())
        self._step_ids["llm"] = step_id
        self._step_start_times[step_id] = datetime.now(timezone.utc)

        return [
            StepStartedEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                step_name="llm_call",
                step_id=step_id,
                metadata={
                    "model": model,
                    "message": payload.get("message", "Starting LLM call"),
                },
            )
        ]

    def _handle_llm_completed(
        self, payload: Dict[str, Any], agent: str
    ) -> List[AGUIEvent]:
        """Handle llm_completed -> STEP_FINISHED."""
        step_id = self._step_ids.get("llm", str(uuid4()))

        duration_ms = None
        if step_id in self._step_start_times:
            start_time = self._step_start_times.pop(step_id)
            duration_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

        return [
            StepFinishedEvent(
                run_id=self.run_id,
                thread_id=self.thread_id,
                step_name="llm_call",
                step_id=step_id,
                duration_ms=duration_ms,
                metadata={"message": payload.get("message", "Completed LLM call")},
            )
        ]

    def get_messages_snapshot(self) -> MessagesSnapshotEvent:
        """Get a snapshot of all messages in the conversation.

        Returns:
            MessagesSnapshotEvent with all accumulated messages
        """
        return MessagesSnapshotEvent(
            run_id=self.run_id,
            thread_id=self.thread_id,
            messages=self._messages.copy(),
        )

    def get_state(self) -> Dict[str, Any]:
        """Get the current state.

        Returns:
            Current state dictionary
        """
        return self._state.copy()
