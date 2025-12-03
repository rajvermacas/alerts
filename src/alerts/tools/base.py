"""Base tool class for SMARTS Alert Analyzer.

This module provides the base class for all tools, implementing
common functionality like logging, statistics tracking, and LLM
interpretation of raw data.

Supports optional streaming of progress events via stream_writer callback.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Type alias for stream writer callback
StreamWriter = Callable[[Dict[str, Any]], None]

__all__ = ["BaseTool", "DataLoadingMixin", "StreamWriter"]


class BaseTool(ABC):
    """Base class for all analysis tools.

    Each tool reads from a data source and uses an LLM internally
    to interpret the data and return insights (not raw data).

    Attributes:
        llm: LangChain LLM instance for interpretation
        name: Tool name for identification
        description: Tool description for agent prompt
        call_count: Number of times the tool has been called
        total_processing_time: Cumulative processing time in seconds
    """

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
    def _load_data(self, **kwargs: Any) -> str:
        """Load raw data from the data source.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            Raw data as string

        Raises:
            FileNotFoundError: If data source is missing
            ValueError: If data is invalid
        """
        pass

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

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        Override in subclasses for custom validation.

        Args:
            **kwargs: Parameters to validate

        Returns:
            Error message if invalid, None if valid
        """
        return None

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

    def __call__(self, config: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
        """Execute the tool.

        This method:
        1. Validates input
        2. Loads raw data (emits tool_started event)
        3. Builds interpretation prompt
        4. Calls LLM for interpretation (emits tool_progress event)
        5. Returns insights (emits tool_completed event)

        Args:
            config: Optional configuration dict containing 'stream_writer' callback
            **kwargs: Tool-specific parameters

        Returns:
            LLM-interpreted insights as string
        """
        self.call_count += 1
        start_time = datetime.now(timezone.utc)

        # Extract stream_writer from config if provided
        # Also check kwargs for config (LangChain may pass it there via StructuredTool)
        stream_writer: Optional[StreamWriter] = None
        effective_config = config

        if effective_config is None and "config" in kwargs:
            effective_config = kwargs.pop("config")

        if effective_config is not None:
            stream_writer = effective_config.get("stream_writer")

        self.logger.info(f"Tool invocation #{self.call_count}: {kwargs}")

        try:
            # Validate input
            error = self._validate_input(**kwargs)
            if error:
                self.logger.warning(f"Input validation failed: {error}")
                self._emit_event(stream_writer, "error", {
                    "message": f"Input validation failed: {error}",
                    "stage": "validation",
                })
                return f"Error: {error}"

            # Emit tool_started event
            self._emit_event(stream_writer, "tool_started", {
                "message": f"Starting {self.name}...",
                "parameters": {k: str(v)[:100] for k, v in kwargs.items()},
            })

            # Load raw data
            self.logger.debug("Loading raw data")
            raw_data = self._load_data(**kwargs)
            self.logger.debug(f"Raw data loaded: {len(raw_data)} chars")

            # Emit progress event after data loading
            self._emit_event(stream_writer, "tool_progress", {
                "message": f"Loaded {len(raw_data)} characters of data, analyzing...",
                "stage": "data_loaded",
                "data_size": len(raw_data),
            })

            # Build interpretation prompt
            prompt = self._build_interpretation_prompt(raw_data, **kwargs)
            self.logger.debug(f"Interpretation prompt built: {len(prompt)} chars")

            # Emit progress event before LLM call
            self._emit_event(stream_writer, "tool_progress", {
                "message": f"Interpreting data with LLM...",
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
            # Extract first 200 chars as summary for the event
            summary = insights[:200] + "..." if len(insights) > 200 else insights
            self._emit_event(stream_writer, "tool_completed", {
                "message": f"Completed {self.name} analysis",
                "duration_seconds": round(elapsed, 2),
                "insights_size": len(insights),
                "summary": summary,
            })

            return insights

        except FileNotFoundError as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.logger.error(f"Data source not found: {e}")
            self._emit_event(stream_writer, "error", {
                "message": f"Data source not found: {e}",
                "stage": "data_loading",
                "duration_seconds": round(elapsed, 2),
            })
            raise  # Fail-fast as per architecture

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


class DataLoadingMixin:
    """Mixin providing common data loading utilities."""

    @staticmethod
    def load_csv_as_string(path: str) -> str:
        """Load CSV file as string.

        Args:
            path: Path to CSV file

        Returns:
            CSV contents as string

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        logger.debug(f"Loading CSV from {path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def load_text_file(path: str) -> str:
        """Load text file as string.

        Args:
            path: Path to text file

        Returns:
            File contents as string

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        logger.debug(f"Loading text file from {path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def load_xml_file(path: str) -> str:
        """Load XML file as string.

        Args:
            path: Path to XML file

        Returns:
            XML contents as string

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        logger.debug(f"Loading XML from {path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def filter_csv_by_column(
        csv_content: str,
        column_name: str,
        value: str,
        include_header: bool = True
    ) -> str:
        """Filter CSV content by column value.

        Args:
            csv_content: CSV content as string
            column_name: Column to filter on
            value: Value to match
            include_header: Whether to include header row

        Returns:
            Filtered CSV content
        """
        lines = csv_content.strip().split("\n")
        if not lines:
            return ""

        header = lines[0]
        columns = header.split(",")

        try:
            col_idx = columns.index(column_name)
        except ValueError:
            logger.warning(f"Column '{column_name}' not found in CSV")
            return csv_content

        filtered = []
        if include_header:
            filtered.append(header)

        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) > col_idx and parts[col_idx] == value:
                filtered.append(line)

        return "\n".join(filtered)

    @staticmethod
    def filter_csv_by_date_range(
        csv_content: str,
        date_column: str,
        start_date: str,
        end_date: str,
        include_header: bool = True
    ) -> str:
        """Filter CSV content by date range.

        Args:
            csv_content: CSV content as string
            date_column: Date column name
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            include_header: Whether to include header row

        Returns:
            Filtered CSV content
        """
        lines = csv_content.strip().split("\n")
        if not lines:
            return ""

        header = lines[0]
        columns = header.split(",")

        try:
            col_idx = columns.index(date_column)
        except ValueError:
            logger.warning(f"Date column '{date_column}' not found in CSV")
            return csv_content

        filtered = []
        if include_header:
            filtered.append(header)

        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) > col_idx:
                row_date = parts[col_idx]
                if start_date <= row_date <= end_date:
                    filtered.append(line)

        return "\n".join(filtered)
