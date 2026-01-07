"""Alert reader tool for SMARTS Alert Analyzer.

This tool reads and parses alert XML content, extracting key information
for the agent to analyze. This is a shared tool used by all agent types.

In Proactive Info Flow mode, XML content is injected via execute(data=...).
"""

import logging
from pathlib import Path
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin, DataFormat

logger = logging.getLogger(__name__)


class AlertReaderTool(BaseTool, DataLoadingMixin):
    """Tool to read and summarize SMARTS alert XML content.

    This tool takes XML content (injected in Proactive Info Flow mode)
    and uses the LLM to extract and summarize the key alert information.

    Expected format: xml
    """

    # Expected data format for this tool
    expected_format: DataFormat = "xml"

    def __init__(self, llm: Any, data_dir: Path | None = None) -> None:
        """Initialize the alert reader tool.

        Args:
            llm: LangChain LLM instance
            data_dir: DEPRECATED - kept for backward compatibility only
        """
        super().__init__(
            llm=llm,
            name="read_alert",
            description=(
                "Read and parse a SMARTS alert XML. "
                "Returns a structured summary of the alert including trader info, "
                "suspicious activity details, anomaly indicators, and related events."
            ),
            expected_format="xml"
        )
        # Keep data_dir for backward compatibility but log deprecation
        if data_dir is not None:
            self.data_dir = data_dir
            self.alerts_dir = data_dir / "alerts"
            self.logger.warning(
                "data_dir parameter is deprecated. In Proactive Info Flow mode, "
                "data is injected via execute(data=...)."
            )
        else:
            self.data_dir = None
            self.alerts_dir = None

        self.logger.info("Alert reader initialized (Proactive Info Flow mode)")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        In Proactive Info Flow mode, no file path validation is needed
        as data is injected directly.

        Args:
            **kwargs: Additional parameters (unused in new mode)

        Returns:
            Error message if invalid, None if valid
        """
        # No validation needed in Proactive Info Flow mode
        # Data validation is handled by execute()
        return None

    def _build_interpretation_prompt(self, raw_data: str, **kwargs: Any) -> str:
        """Build prompt for LLM to interpret the alert XML.

        Args:
            raw_data: XML content
            **kwargs: Additional parameters (unused)

        Returns:
            Interpretation prompt
        """
        return f"""You are a compliance analyst reviewing a SMARTS surveillance alert.

Parse the following alert XML and provide a structured summary covering:

1. **Alert Identification**
   - Alert ID
   - Alert Type
   - Rule Violated
   - Generated Timestamp

2. **Trader Information**
   - Trader ID
   - Name
   - Department

3. **Suspicious Activity Details**
   - Symbol traded
   - Trade date
   - Side (BUY/SELL)
   - Quantity
   - Price
   - Total Value

4. **Anomaly Indicators**
   - Anomaly Score
   - Confidence Level
   - Temporal Proximity to event
   - Estimated Profit

5. **Related Event** (if present)
   - Event Type
   - Event Date
   - Event Description

Provide this information in a clear, structured format that a compliance analyst can quickly review.

Alert XML:
{raw_data}

Summary:"""
