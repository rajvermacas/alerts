"""Reports package for SMARTS Alert Analyzer.

This package contains report generation modules for outputting
analysis results in various formats.
"""

from alerts.reports.html_generator import HTMLReportGenerator
from alerts.reports.wash_trade_report import (
    WashTradeHTMLReportGenerator,
    WashTradeAlertSummary,
)

__all__ = [
    "HTMLReportGenerator",
    "WashTradeHTMLReportGenerator",
    "WashTradeAlertSummary",
]
