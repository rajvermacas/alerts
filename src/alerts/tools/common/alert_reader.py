"""Alert reader tool for SMARTS Alert Analyzer.

This tool reads and parses alert XML files, extracting key information
for the agent to analyze. This is a shared tool used by all agent types.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from alerts.tools.common.base import BaseTool, DataLoadingMixin

logger = logging.getLogger(__name__)


class AlertReaderTool(BaseTool, DataLoadingMixin):
    """Tool to read and summarize SMARTS alert XML files.

    This tool reads the full XML content and uses the LLM to
    extract and summarize the key alert information.
    """

    def __init__(self, llm: Any, data_dir: Path) -> None:
        """Initialize the alert reader tool.

        Args:
            llm: LangChain LLM instance
            data_dir: Path to data directory containing alerts
        """
        super().__init__(
            llm=llm,
            name="read_alert",
            description=(
                "Read and parse a SMARTS alert XML file. "
                "Returns a structured summary of the alert including trader info, "
                "suspicious activity details, anomaly indicators, and related events."
            )
        )
        self.data_dir = data_dir
        self.alerts_dir = data_dir / "alerts"
        self.logger.info(f"Alert reader initialized with alerts dir: {self.alerts_dir}")

    def _validate_input(self, **kwargs: Any) -> Optional[str]:
        """Validate input parameters.

        Args:
            **kwargs: Must contain 'alert_file_path'

        Returns:
            Error message if invalid, None if valid
        """
        alert_file_path = kwargs.get("alert_file_path")

        if not alert_file_path:
            return "alert_file_path is required"

        path = Path(alert_file_path)
        if not path.exists():
            return f"Alert file not found: {alert_file_path}"

        if not path.suffix.lower() == ".xml":
            return f"Alert file must be XML: {alert_file_path}"

        return None

    def _load_data(self, **kwargs: Any) -> str:
        """Load alert XML file.

        Args:
            **kwargs: Must contain 'alert_file_path'

        Returns:
            XML content as string
        """
        alert_file_path = kwargs["alert_file_path"]
        self.logger.info(f"Loading alert XML from: {alert_file_path}")

        return self.load_xml_file(str(alert_file_path))

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
