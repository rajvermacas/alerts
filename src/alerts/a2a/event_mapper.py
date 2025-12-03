"""Event Mapper for converting LangGraph events to A2A format.

This module provides utilities for converting LangGraph streaming events
to A2A TaskStatusUpdateEvent format for real-time progress streaming.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


class StreamEvent:
    """Represents a streaming event in the pipeline.

    This is the intermediate format used between LangGraph events
    and A2A TaskStatusUpdateEvent format.
    """

    def __init__(
        self,
        event_id: str,
        task_id: str,
        timestamp: str,
        agent: str,
        event_type: str,
        payload: Dict[str, Any],
        final: bool = False,
    ):
        """Initialize a StreamEvent.

        Args:
            event_id: Unique event identifier
            task_id: Task this event belongs to
            timestamp: ISO format timestamp
            agent: Agent name (insider_trading, wash_trade, orchestrator)
            event_type: Type of event
            payload: Event-specific payload
            final: Whether this is the final event in the stream
        """
        self.event_id = event_id
        self.task_id = task_id
        self.timestamp = timestamp
        self.agent = agent
        self.event_type = event_type
        self.payload = payload
        self.final = final

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "agent": self.agent,
            "event_type": self.event_type,
            "payload": self.payload,
            "final": self.final,
        }

    def to_a2a_format(self, task_state: str = "working") -> Dict[str, Any]:
        """Convert to A2A TaskStatusUpdateEvent format.

        Args:
            task_state: Current task state (submitted, working, completed, failed)

        Returns:
            A2A-compliant JSON-RPC 2.0 response with TaskStatusUpdateEvent
        """
        return {
            "jsonrpc": "2.0",
            "result": {
                "task": {
                    "id": self.task_id,
                    "state": task_state,
                },
                "taskStatusUpdateEvent": {
                    "task": {
                        "id": self.task_id,
                        "state": task_state,
                        "messages": [
                            {
                                "role": "agent",
                                "parts": [
                                    {
                                        "type": "textPart",
                                        "text": self._format_message(),
                                    }
                                ],
                            }
                        ],
                    },
                    "final": self.final,
                },
                "metadata": {
                    "event_id": self.event_id,
                    "event_type": self.event_type,
                    "agent": self.agent,
                    "timestamp": self.timestamp,
                    "payload": self.payload,
                },
            },
        }

    def _format_message(self) -> str:
        """Format the payload as a human-readable message."""
        message = self.payload.get("message", "")
        if not message:
            # Try to construct a message from the event type
            if self.event_type == "tool_started":
                tool_name = self.payload.get("tool_name", "unknown")
                message = f"Starting {tool_name}..."
            elif self.event_type == "tool_completed":
                tool_name = self.payload.get("tool_name", "unknown")
                summary = self.payload.get("summary", "")
                message = f"Completed {tool_name}. {summary[:100]}..." if summary else f"Completed {tool_name}"
            elif self.event_type == "tool_progress":
                stage = self.payload.get("stage", "processing")
                message = f"Processing: {stage}"
            elif self.event_type == "agent_thinking":
                message = "Agent is analyzing the gathered evidence..."
            elif self.event_type == "analysis_complete":
                determination = self.payload.get("determination", "")
                message = f"Analysis complete. Determination: {determination}"
            elif self.event_type == "error":
                error_msg = self.payload.get("message", "Unknown error")
                message = f"Error: {error_msg}"
            elif self.event_type == "keep_alive":
                message = "Processing..."
            else:
                message = f"Event: {self.event_type}"
        return message


class EventMapper:
    """Maps events between different formats in the streaming pipeline.

    Handles conversion from:
    - LangGraph events -> StreamEvent
    - Tool events -> StreamEvent
    - StreamEvent -> A2A TaskStatusUpdateEvent
    """

    def __init__(self, task_id: str, agent_name: str):
        """Initialize the EventMapper.

        Args:
            task_id: Task ID for all events
            agent_name: Name of the agent (insider_trading, wash_trade, orchestrator)
        """
        self.task_id = task_id
        self.agent_name = agent_name
        self.event_count = 0
        self.logger = logging.getLogger(f"{__name__}.{agent_name}")

    def create_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        final: bool = False,
    ) -> StreamEvent:
        """Create a new StreamEvent.

        Args:
            event_type: Type of event
            payload: Event payload
            final: Whether this is the final event

        Returns:
            New StreamEvent instance
        """
        self.event_count += 1
        event = StreamEvent(
            event_id=str(uuid.uuid4()),
            task_id=self.task_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent=self.agent_name,
            event_type=event_type,
            payload=payload,
            final=final,
        )
        self.logger.debug(
            f"Created event #{self.event_count}: {event_type} (final={final})"
        )
        return event

    def map_tool_event(self, tool_event: Dict[str, Any]) -> StreamEvent:
        """Map a tool-emitted event to StreamEvent format.

        Tool events come from BaseTool._emit_event() and have this structure:
        {
            "event_id": "uuid",
            "timestamp": "iso-timestamp",
            "event_type": "tool_started|tool_progress|tool_completed|error",
            "tool_name": "tool_name",
            "payload": {...}
        }

        Args:
            tool_event: Event dict from tool execution

        Returns:
            StreamEvent with normalized format
        """
        event_type = tool_event.get("event_type", "unknown")
        tool_name = tool_event.get("tool_name", "unknown")
        payload = tool_event.get("payload", {})

        # Enrich payload with tool name
        enriched_payload = {
            "tool_name": tool_name,
            **payload,
        }

        return self.create_event(
            event_type=event_type,
            payload=enriched_payload,
            final=False,  # Tool events are never final
        )

    def map_langgraph_event(
        self,
        lg_event: Dict[str, Any],
        event_name: str,
    ) -> Optional[StreamEvent]:
        """Map a LangGraph event to StreamEvent format.

        LangGraph events from astream_events() have this structure:
        {
            "event": "on_chain_start|on_chain_end|on_tool_start|on_tool_end|...",
            "data": {...},
            "name": "node_name",
            "run_id": "...",
            "tags": [...],
            "metadata": {...}
        }

        Args:
            lg_event: Event from LangGraph's astream_events()
            event_name: The event name (e.g., "on_chain_start")

        Returns:
            StreamEvent or None if event should be skipped
        """
        # Map LangGraph event types to our event types
        event_type_map = {
            "on_chain_start": "node_started",
            "on_chain_end": "node_completed",
            "on_tool_start": "tool_started",
            "on_tool_end": "tool_completed",
            "on_chat_model_start": "llm_started",
            "on_chat_model_end": "llm_completed",
            "on_chat_model_stream": "llm_token",
        }

        mapped_type = event_type_map.get(event_name)
        if not mapped_type:
            self.logger.debug(f"Skipping unmapped LangGraph event: {event_name}")
            return None

        # Extract relevant data
        data = lg_event.get("data", {})
        name = lg_event.get("name", "unknown")
        run_id = lg_event.get("run_id", "")

        self.logger.debug(f"Mapping LangGraph event: {event_name} -> {mapped_type}, name={name}")

        # Build payload based on event type
        if event_name in ("on_chain_start", "on_chain_end"):
            payload = {
                "node_name": name,
                "message": f"{'Starting' if 'start' in event_name else 'Completed'} {name}",
            }
        elif event_name in ("on_tool_start", "on_tool_end"):
            tool_input = data.get("input", {})
            tool_output = data.get("output", "")
            payload = {
                "tool_name": name,
                "message": f"{'Starting' if 'start' in event_name else 'Completed'} tool: {name}",
            }
            if tool_input:
                payload["input"] = str(tool_input)[:200]
            if tool_output:
                payload["output_summary"] = str(tool_output)[:200]
            self.logger.debug(f"Created tool event payload: {event_name}, tool={name}")
        elif event_name in ("on_chat_model_start", "on_chat_model_end"):
            payload = {
                "model": name,
                "message": f"{'Starting' if 'start' in event_name else 'Completed'} LLM call",
            }
        elif event_name == "on_chat_model_stream":
            # Token streaming - typically skip these for high-level progress
            return None
        else:
            payload = {
                "message": f"Event: {event_name}",
                "raw_data": str(data)[:500],
            }

        return self.create_event(
            event_type=mapped_type,
            payload=payload,
            final=False,
        )

    def create_analysis_started_event(self, alert_file: str) -> StreamEvent:
        """Create an event for when analysis starts.

        Args:
            alert_file: Path to the alert file being analyzed

        Returns:
            StreamEvent indicating analysis started
        """
        return self.create_event(
            event_type="analysis_started",
            payload={
                "message": f"Starting analysis of alert: {alert_file}",
                "alert_file": alert_file,
            },
            final=False,
        )

    def create_analysis_complete_event(
        self,
        determination: str,
        confidence: int,
        summary: str,
        decision: Optional[Dict[str, Any]] = None,
    ) -> StreamEvent:
        """Create an event for when analysis completes.

        Args:
            determination: Final determination (ESCALATE, CLOSE, NEEDS_HUMAN_REVIEW)
            confidence: Confidence percentage
            summary: Brief summary of findings
            decision: Optional full decision object for downstream consumers

        Returns:
            StreamEvent indicating analysis complete (final=True)
        """
        payload = {
            "message": f"Analysis complete. Determination: {determination}",
            "determination": determination,
            "confidence": confidence,
            "summary": summary,
        }
        if decision is not None:
            payload["decision"] = decision
            self.logger.info(f"Including full decision in analysis_complete event")

        return self.create_event(
            event_type="analysis_complete",
            payload=payload,
            final=True,
        )

    def create_error_event(
        self,
        error_message: str,
        stage: str = "unknown",
        fatal: bool = True,
    ) -> StreamEvent:
        """Create an error event.

        Args:
            error_message: Error description
            stage: Stage where error occurred
            fatal: Whether this error terminates the stream

        Returns:
            StreamEvent for the error
        """
        return self.create_event(
            event_type="error",
            payload={
                "message": f"Error in {stage}: {error_message}",
                "error": error_message,
                "stage": stage,
            },
            final=fatal,
        )

    def create_keep_alive_event(self) -> StreamEvent:
        """Create a keep-alive event.

        Used to prevent connection timeouts during long processing.

        Returns:
            StreamEvent for keep-alive
        """
        return self.create_event(
            event_type="keep_alive",
            payload={
                "message": "Processing...",
            },
            final=False,
        )

    def create_agent_thinking_event(self, context: str = "") -> StreamEvent:
        """Create an event indicating agent is thinking/reasoning.

        Args:
            context: Optional context about what the agent is thinking about

        Returns:
            StreamEvent for agent thinking
        """
        message = "Agent is analyzing the gathered evidence..."
        if context:
            message = f"Agent is analyzing: {context}"

        return self.create_event(
            event_type="agent_thinking",
            payload={
                "message": message,
                "context": context,
            },
            final=False,
        )


def create_stream_writer_for_mapper(
    event_mapper: EventMapper,
    event_collector: List[StreamEvent],
) -> callable:
    """Create a stream_writer callback that uses an EventMapper.

    This is used to pass to tools via config so they can emit events
    that get collected and mapped to the proper format.

    Args:
        event_mapper: EventMapper instance for this task
        event_collector: List to append events to

    Returns:
        Callable that accepts tool event dicts
    """
    def stream_writer(tool_event: Dict[str, Any]) -> None:
        """Callback for tool event emission."""
        stream_event = event_mapper.map_tool_event(tool_event)
        event_collector.append(stream_event)
        logger.debug(
            f"Collected tool event: {stream_event.event_type} from {tool_event.get('tool_name', 'unknown')}"
        )

    return stream_writer


class EventBuffer:
    """Buffer for storing events for replay and reconnection.

    Keeps a rolling buffer of recent events that can be replayed
    when a client reconnects.
    """

    def __init__(self, max_size: int = 100):
        """Initialize the EventBuffer.

        Args:
            max_size: Maximum number of events to keep
        """
        self.max_size = max_size
        self.events: List[StreamEvent] = []
        self.event_ids: set = set()

    def add(self, event: StreamEvent) -> None:
        """Add an event to the buffer.

        Args:
            event: Event to add
        """
        if event.event_id in self.event_ids:
            return  # Already have this event

        self.events.append(event)
        self.event_ids.add(event.event_id)

        # Trim if over max size
        while len(self.events) > self.max_size:
            removed = self.events.pop(0)
            self.event_ids.discard(removed.event_id)

    def get_events_after(self, last_event_id: Optional[str]) -> List[StreamEvent]:
        """Get all events after a given event ID.

        Used for reconnection to replay missed events.

        Args:
            last_event_id: Last event ID client received, or None for all events

        Returns:
            List of events after the specified ID
        """
        if last_event_id is None:
            return list(self.events)

        # Find the index of the last received event
        for i, event in enumerate(self.events):
            if event.event_id == last_event_id:
                return self.events[i + 1:]

        # Event not found, return all events
        logger.warning(f"Event ID {last_event_id} not found in buffer, returning all")
        return list(self.events)

    def clear(self) -> None:
        """Clear all buffered events."""
        self.events.clear()
        self.event_ids.clear()

    def __len__(self) -> int:
        return len(self.events)
