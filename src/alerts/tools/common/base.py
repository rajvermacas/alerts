"""Base tool class for SMARTS Alert Analyzer.

This module provides the base class for all tools, implementing
common functionality like logging, statistics tracking, and LLM
interpretation of raw data.

Uses the proactive information flow pattern where data is injected
via execute() method from the Big Data Layer, rather than tools
loading their own data from files.

Supports optional streaming of progress events via stream_writer callback.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from alerts.exceptions import MissingToolDataError, InvalidFormatError

logger = logging.getLogger(__name__)

# Type alias for stream writer callback
StreamWriter = Callable[[Dict[str, Any]], None]

__all__ = ["BaseTool", "StreamWriter"]


class BaseTool(ABC):
    """Base class for all analysis tools.

    Each tool uses an LLM internally to interpret data and return
    insights (not raw data). Data is injected via execute() method
    from the Big Data Layer (proactive information flow pattern).

    Attributes:
        llm: LangChain LLM instance for interpretation
        name: Tool name for identification
        description: Tool description for agent prompt
        expected_format: Expected data format for execute() (csv, xml, txt)
        call_count: Number of times the tool has been called
        total_processing_time: Cumulative processing time in seconds
    """

    # Subclasses should override this with their expected format
    expected_format: str = "txt"

    def __init__(self, llm: Any, name: str, description: str) -> None:
        """Initialize the tool.

        Args:
            llm: LangChain LLM instance
            name: Tool name
            description: Tool description for agent
        """
        self.llm = llm
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"alerts.tools.{name}")
        self.call_count = 0
        self.total_processing_time = 0.0

        self.logger.info(f"Tool '{name}' initialized")

    @abstractmethod
    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build the prompt for LLM interpretation.

        Args:
            raw_data: Raw data loaded from source
            **kwargs: Tool-specific parameters

        Returns:
            Prompt string for LLM
        """
        pass

    def _interpret_with_llm(self, prompt: str) -> str:
        """Use LLM to interpret data and return insights.

        Args:
            prompt: Interpretation prompt

        Returns:
            LLM-generated insights as string
        """
        self.logger.debug(f"Sending interpretation prompt ({len(prompt)} chars)")

        try:
            response = self.llm.invoke(prompt)
            content = response.content

            self.logger.debug(f"LLM response received ({len(content)} chars)")
            return content

        except Exception as e:
            self.logger.error(f"LLM interpretation failed: {e}", exc_info=True)
            raise

    async def _ainterpret_with_llm(self, prompt: str) -> str:
        """Async version: Use LLM to interpret data and return insights.

        Uses LangChain's ainvoke() for non-blocking LLM calls in async contexts.

        Args:
            prompt: Interpretation prompt

        Returns:
            LLM-generated insights as string
        """
        self.logger.debug(f"Sending async interpretation prompt ({len(prompt)} chars)")

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content

            self.logger.debug(f"LLM async response received ({len(content)} chars)")
            return content

        except Exception as e:
            self.logger.error(f"LLM async interpretation failed: {e}", exc_info=True)
            raise

    def execute(
        self,
        data: str,
        format: str,
        config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Execute the tool with injected data (proactive info flow pattern).

        This method accepts data directly instead of loading it from files,
        enabling the proactive information flow architecture where the
        Big Data Layer aggregates and provides all required data.

        Args:
            data: Raw data content as string (pre-loaded by caller)
            format: Data format identifier (csv, xml, txt)
            config: Optional configuration dict containing 'stream_writer' callback
            **kwargs: Additional tool-specific parameters for prompt building

        Returns:
            LLM-interpreted insights as string

        Raises:
            MissingToolDataError: If data is None or empty
            InvalidFormatError: If format doesn't match expected_format
        """
        self.call_count += 1
        start_time = datetime.now(timezone.utc)

        # Extract stream_writer from config if provided
        stream_writer: Optional[StreamWriter] = None
        if config is not None:
            stream_writer = config.get("stream_writer")

        self.logger.info(
            f"Tool execute() invocation #{self.call_count}: "
            f"format={format}, data_size={len(data) if data else 0}"
        )

        try:
            # Validate data is provided (fail-fast)
            if data is None or data == "":
                self.logger.error(f"Missing data for tool {self.name}")
                raise MissingToolDataError(self.name)

            # Validate format matches expected
            if format != self.expected_format:
                self.logger.error(
                    f"Format mismatch for {self.name}: "
                    f"expected {self.expected_format}, got {format}"
                )
                raise InvalidFormatError(self.name, self.expected_format, format)

            # Emit tool_started event
            self._emit_event(stream_writer, "tool_started", {
                "message": f"Starting {self.name}...",
                "data_size": len(data),
                "format": format,
            })

            self.logger.debug(f"Data provided: {len(data)} chars")

            # Emit progress event after data validation
            self._emit_event(stream_writer, "tool_progress", {
                "message": f"Processing {len(data)} characters of {format} data...",
                "stage": "data_validated",
                "data_size": len(data),
            })

            # Build interpretation prompt
            prompt = self._build_interpretation_prompt(data, **kwargs)
            self.logger.debug(f"Interpretation prompt built: {len(prompt)} chars")

            # Emit progress event before LLM call
            self._emit_event(stream_writer, "tool_progress", {
                "message": "Interpreting data with LLM...",
                "stage": "llm_interpreting",
                "prompt_size": len(prompt),
            })

            # Interpret with LLM
            insights = self._interpret_with_llm(prompt)

            # Track timing
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.total_processing_time += elapsed

            self.logger.info(
                f"Tool completed in {elapsed:.2f}s, returned {len(insights)} chars"
            )

            # Emit tool_completed event with summary
            summary = insights[:200] + "..." if len(insights) > 200 else insights
            self._emit_event(stream_writer, "tool_completed", {
                "message": f"Completed {self.name} analysis",
                "duration_seconds": round(elapsed, 2),
                "insights_size": len(insights),
                "summary": summary,
            })

            return insights

        except (MissingToolDataError, InvalidFormatError):
            # Re-raise validation errors without wrapping
            raise

        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.error(
                f"Tool execution failed after {elapsed:.2f}s: {e}",
                exc_info=True
            )
            self._emit_event(stream_writer, "error", {
                "message": f"Tool execution failed: {e}",
                "stage": "execution",
                "duration_seconds": round(elapsed, 2),
            })
            raise  # Fail-fast as per architecture

    async def aexecute(
        self,
        data: str,
        format: str,
        config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Async version of execute() for non-blocking LLM calls.

        This method uses ainvoke() for async LLM calls, enabling proper
        concurrency in async contexts (e.g., FastAPI/Starlette servers).
        Use this method with asyncio.gather() for parallel tool execution.

        Args:
            data: Raw data content as string (pre-loaded by caller)
            format: Data format identifier (csv, xml, txt)
            config: Optional configuration dict containing 'stream_writer' callback
            **kwargs: Additional tool-specific parameters for prompt building

        Returns:
            LLM-interpreted insights as string

        Raises:
            MissingToolDataError: If data is None or empty
            InvalidFormatError: If format doesn't match expected_format
        """
        self.call_count += 1
        start_time = datetime.now(timezone.utc)

        # Extract stream_writer from config if provided
        stream_writer: Optional[StreamWriter] = None
        if config is not None:
            stream_writer = config.get("stream_writer")

        self.logger.info(
            f"Tool async execute() invocation #{self.call_count}: "
            f"format={format}, data_size={len(data) if data else 0}"
        )

        try:
            # Validate data is provided (fail-fast)
            if data is None or data == "":
                self.logger.error(f"Missing data for tool {self.name}")
                raise MissingToolDataError(self.name)

            # Validate format matches expected
            if format != self.expected_format:
                self.logger.error(
                    f"Format mismatch for {self.name}: "
                    f"expected {self.expected_format}, got {format}"
                )
                raise InvalidFormatError(self.name, self.expected_format, format)

            # Emit tool_started event
            self._emit_event(stream_writer, "tool_started", {
                "message": f"Starting {self.name}...",
                "data_size": len(data),
                "format": format,
            })

            self.logger.debug(f"Data provided: {len(data)} chars")

            # Emit progress event after data validation
            self._emit_event(stream_writer, "tool_progress", {
                "message": f"Processing {len(data)} characters of {format} data...",
                "stage": "data_validated",
                "data_size": len(data),
            })

            # Build interpretation prompt (sync - just string operations)
            prompt = self._build_interpretation_prompt(data, **kwargs)
            self.logger.debug(f"Interpretation prompt built: {len(prompt)} chars")

            # Emit progress event before LLM call
            self._emit_event(stream_writer, "tool_progress", {
                "message": "Interpreting data with LLM (async)...",
                "stage": "llm_interpreting",
                "prompt_size": len(prompt),
            })

            # Interpret with LLM (async)
            insights = await self._ainterpret_with_llm(prompt)

            # Track timing
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.total_processing_time += elapsed

            self.logger.info(
                f"Async tool completed in {elapsed:.2f}s, returned {len(insights)} chars"
            )

            # Emit tool_completed event with summary
            summary = insights[:200] + "..." if len(insights) > 200 else insights
            self._emit_event(stream_writer, "tool_completed", {
                "message": f"Completed {self.name} analysis",
                "duration_seconds": round(elapsed, 2),
                "insights_size": len(insights),
                "summary": summary,
            })

            return insights

        except (MissingToolDataError, InvalidFormatError):
            # Re-raise validation errors without wrapping
            raise

        except Exception as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.error(
                f"Async tool execution failed after {elapsed:.2f}s: {e}",
                exc_info=True
            )
            self._emit_event(stream_writer, "error", {
                "message": f"Async tool execution failed: {e}",
                "stage": "execution",
                "duration_seconds": round(elapsed, 2),
            })
            raise  # Fail-fast as per architecture

    def _emit_event(
        self,
        stream_writer: Optional[StreamWriter],
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        """Emit a streaming event if stream_writer is available.

        Args:
            stream_writer: Optional callback to write events
            event_type: Type of event (tool_started, tool_progress, tool_completed, error)
            payload: Event payload data
        """
        if stream_writer is None:
            return

        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "tool_name": self.name,
            "payload": payload,
        }
        self.logger.debug(f"Emitting event: {event_type} for tool {self.name}")
        try:
            stream_writer(event)
        except Exception as e:
            self.logger.warning(f"Failed to emit event: {e}")
            # Don't raise - streaming failure shouldn't break tool execution

    def get_stats(self) -> dict:
        """Get tool usage statistics.

        Returns:
            Dictionary with tool statistics
        """
        return {
            "name": self.name,
            "call_count": self.call_count,
            "total_time_seconds": round(self.total_processing_time, 2),
            "avg_time_per_call": round(
                self.total_processing_time / self.call_count
                if self.call_count > 0 else 0,
                2
            ),
        }
