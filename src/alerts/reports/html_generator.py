"""HTML report generator for SMARTS Alert Analyzer.

This module generates professional HTML reports with Tailwind CSS
that display both the original alert data and AI analysis insights.
"""

import html
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from alerts.models import AlertDecision, AlertSummary

logger = logging.getLogger(__name__)


class HTMLReportGenerator:
    """Generates HTML reports combining alert data with AI analysis.

    This generator creates professional, Tailwind CSS-styled reports
    that display the original SMARTS alert alongside the AI-generated
    analysis insights.

    Attributes:
        alert_summary: Parsed alert data from XML
        decision: AI-generated analysis decision
    """

    # Color mappings for determination badges
    DETERMINATION_COLORS = {
        "ESCALATE": {
            "bg": "bg-red-600",
            "text": "text-white",
            "label": "ESCALATE",
        },
        "CLOSE": {
            "bg": "bg-green-600",
            "text": "text-white",
            "label": "CLOSE",
        },
        "NEEDS_HUMAN_REVIEW": {
            "bg": "bg-yellow-500",
            "text": "text-white",
            "label": "NEEDS HUMAN REVIEW",
        },
    }

    # Color mappings for recommended actions
    ACTION_COLORS = {
        "ESCALATE": "bg-red-100 text-red-800",
        "CLOSE": "bg-green-100 text-green-800",
        "MONITOR": "bg-blue-100 text-blue-800",
        "REQUEST_MORE_DATA": "bg-purple-100 text-purple-800",
    }

    def __init__(
        self,
        alert_summary: AlertSummary,
        decision: AlertDecision,
    ) -> None:
        """Initialize the HTML report generator.

        Args:
            alert_summary: Parsed alert data from XML
            decision: AI-generated analysis decision
        """
        self.alert_summary = alert_summary
        self.decision = decision
        self.logger = logger

    @classmethod
    def from_xml_file(
        cls,
        alert_xml_path: Path,
        decision: AlertDecision,
    ) -> "HTMLReportGenerator":
        """Create generator from XML file path.

        Args:
            alert_xml_path: Path to the alert XML file
            decision: AI-generated analysis decision

        Returns:
            HTMLReportGenerator instance

        Raises:
            FileNotFoundError: If XML file doesn't exist
            ValueError: If XML parsing fails
        """
        alert_summary = cls._parse_alert_xml(alert_xml_path)
        return cls(alert_summary, decision)

    @staticmethod
    def _parse_alert_xml(xml_path: Path) -> AlertSummary:
        """Parse SMARTS alert XML file into AlertSummary.

        Args:
            xml_path: Path to the XML file

        Returns:
            AlertSummary with parsed data

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If XML is malformed
        """
        logger.info(f"Parsing alert XML: {xml_path}")

        if not xml_path.exists():
            raise FileNotFoundError(f"Alert XML file not found: {xml_path}")

        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()

            # Helper function to safely get text from element
            def get_text(path: str, default: str = "") -> str:
                elem = root.find(path)
                return elem.text if elem is not None and elem.text else default

            def get_int(path: str, default: int = 0) -> int:
                text = get_text(path)
                return int(text) if text else default

            def get_float(path: str, default: float = 0.0) -> float:
                text = get_text(path)
                return float(text) if text else default

            # Parse all fields
            return AlertSummary(
                alert_id=get_text("AlertID", "UNKNOWN"),
                alert_type=get_text("AlertType", "Unknown"),
                rule_violated=get_text("RuleViolated", "Unknown"),
                generated_timestamp=get_text("GeneratedTimestamp", "Unknown"),
                trader_id=get_text("Trader/TraderID", "Unknown"),
                trader_name=get_text("Trader/Name", "Unknown"),
                trader_department=get_text("Trader/Department", "Unknown"),
                symbol=get_text("SuspiciousActivity/Symbol", "Unknown"),
                trade_date=get_text("SuspiciousActivity/TradeDate", "Unknown"),
                side=get_text("SuspiciousActivity/Side", "Unknown"),
                quantity=get_int("SuspiciousActivity/Quantity"),
                price=get_float("SuspiciousActivity/Price"),
                total_value=get_float("SuspiciousActivity/TotalValue"),
                anomaly_score=get_int("AnomalyIndicators/AnomalyScore"),
                confidence_level=get_text("AnomalyIndicators/ConfidenceLevel", "Unknown"),
                temporal_proximity=get_text("AnomalyIndicators/TemporalProximity", "Unknown"),
                estimated_profit=get_float("AnomalyIndicators/EstimatedProfit"),
                related_event_type=get_text("RelatedEvent/EventType") or None,
                related_event_date=get_text("RelatedEvent/EventDate") or None,
                related_event_description=get_text("RelatedEvent/EventDescription") or None,
            )

        except ET.ParseError as e:
            raise ValueError(f"Failed to parse XML: {e}") from e

    def generate(self) -> str:
        """Generate complete HTML report.

        Returns:
            Complete HTML document as string
        """
        self.logger.info(f"Generating HTML report for alert: {self.decision.alert_id}")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alert Analysis Report - {self._escape(self.decision.alert_id)}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen">
    <div class="max-w-5xl mx-auto py-8 px-4">
        {self._render_header()}
        {self._render_determination_banner()}
        {self._render_alert_section()}
        {self._render_analysis_section()}
        {self._render_baseline_analysis_section()}
        {self._render_market_context_section()}
        {self._render_reasoning_section()}
        {self._render_data_gaps_section()}
        {self._render_footer()}
    </div>
</body>
</html>"""

    def _escape(self, text: str) -> str:
        """Escape HTML special characters.

        Args:
            text: Text to escape

        Returns:
            HTML-escaped text
        """
        return html.escape(str(text))

    def _format_currency(self, value: float) -> str:
        """Format value as currency.

        Args:
            value: Numeric value

        Returns:
            Formatted currency string
        """
        return f"${value:,.2f}"

    def _format_number(self, value: int) -> str:
        """Format number with thousand separators.

        Args:
            value: Integer value

        Returns:
            Formatted number string
        """
        return f"{value:,}"

    def _get_confidence_color(self, confidence: int) -> str:
        """Get color class based on confidence level.

        Args:
            confidence: Confidence percentage (0-100)

        Returns:
            Tailwind color class
        """
        if confidence >= 70:
            return "text-red-600"
        elif confidence >= 40:
            return "text-yellow-600"
        return "text-green-600"

    def _render_header(self) -> str:
        """Render the report header section.

        Returns:
            HTML string for header
        """
        timestamp = self.decision.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        return f"""
        <!-- Header -->
        <header class="bg-white rounded-lg shadow-md p-6 mb-6">
            <div class="flex justify-between items-start">
                <div>
                    <h1 class="text-2xl font-bold text-gray-900">SMARTS Alert Analysis Report</h1>
                    <p class="text-gray-600 mt-1">AI-Powered Compliance Analysis</p>
                </div>
                <div class="text-right">
                    <p class="text-sm text-gray-500">Report Generated</p>
                    <p class="text-sm font-medium text-gray-700">{self._escape(timestamp)}</p>
                </div>
            </div>
            <div class="mt-4 pt-4 border-t border-gray-200">
                <p class="text-sm text-gray-600">
                    <span class="font-medium">Alert ID:</span>
                    <span class="font-mono bg-gray-100 px-2 py-1 rounded">{self._escape(self.decision.alert_id)}</span>
                </p>
            </div>
        </header>"""

    def _render_determination_banner(self) -> str:
        """Render the determination banner with confidence scores.

        Returns:
            HTML string for determination banner
        """
        colors = self.DETERMINATION_COLORS.get(
            self.decision.determination,
            self.DETERMINATION_COLORS["NEEDS_HUMAN_REVIEW"]
        )
        action_color = self.ACTION_COLORS.get(
            self.decision.recommended_action,
            "bg-gray-100 text-gray-800"
        )

        genuine_color = self._get_confidence_color(self.decision.genuine_alert_confidence)
        fp_color = self._get_confidence_color(100 - self.decision.false_positive_confidence)

        return f"""
        <!-- Determination Banner -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <div class="flex flex-col md:flex-row md:items-center md:justify-between">
                <div class="mb-4 md:mb-0">
                    <p class="text-sm font-medium text-gray-500 uppercase tracking-wide mb-2">AI Determination</p>
                    <span class="inline-flex items-center px-4 py-2 rounded-md text-lg font-bold {colors['bg']} {colors['text']}">
                        {self._escape(colors['label'])}
                    </span>
                </div>
                <div class="flex space-x-8">
                    <div class="text-center">
                        <p class="text-sm text-gray-500">Genuine Alert</p>
                        <p class="text-2xl font-bold {genuine_color}">{self.decision.genuine_alert_confidence}%</p>
                    </div>
                    <div class="text-center">
                        <p class="text-sm text-gray-500">False Positive</p>
                        <p class="text-2xl font-bold {fp_color}">{self.decision.false_positive_confidence}%</p>
                    </div>
                </div>
            </div>
            <div class="mt-4 pt-4 border-t border-gray-200 flex flex-wrap gap-4">
                <div>
                    <span class="text-sm text-gray-500">Recommended Action:</span>
                    <span class="ml-2 px-3 py-1 rounded-full text-sm font-medium {action_color}">
                        {self._escape(self.decision.recommended_action)}
                    </span>
                </div>
                <div class="flex-1 text-right">
                    <span class="text-sm text-gray-500">Similar Precedent:</span>
                    <span class="ml-2 text-sm text-gray-700">{self._escape(self.decision.similar_precedent[:80])}...</span>
                </div>
            </div>
        </section>"""

    def _render_alert_section(self) -> str:
        """Render the original alert details section.

        Returns:
            HTML string for alert section
        """
        # Determine side color
        side_color = "text-green-600" if self.alert_summary.side == "BUY" else "text-red-600"

        # Related event section (conditional)
        related_event_html = ""
        if self.alert_summary.related_event_type:
            related_event_html = f"""
                <div class="mt-4 pt-4 border-t border-gray-200">
                    <h4 class="text-sm font-medium text-gray-700 mb-3">Related Event</h4>
                    <div class="bg-yellow-50 border border-yellow-200 rounded-md p-3">
                        <p class="text-sm"><span class="font-medium">Event:</span> {self._escape(self.alert_summary.related_event_type or '')}</p>
                        <p class="text-sm"><span class="font-medium">Date:</span> {self._escape(self.alert_summary.related_event_date or '')}</p>
                        <p class="text-sm mt-1">{self._escape(self.alert_summary.related_event_description or '')}</p>
                    </div>
                </div>"""

        return f"""
        <!-- Original Alert Section -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                </svg>
                Original SMARTS Alert
            </h2>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Alert Metadata -->
                <div>
                    <h4 class="text-sm font-medium text-gray-700 mb-3">Alert Information</h4>
                    <div class="space-y-2 text-sm">
                        <p><span class="text-gray-500">Alert Type:</span> <span class="font-medium">{self._escape(self.alert_summary.alert_type)}</span></p>
                        <p><span class="text-gray-500">Rule Violated:</span> <span class="font-mono bg-red-50 text-red-700 px-2 py-0.5 rounded">{self._escape(self.alert_summary.rule_violated)}</span></p>
                        <p><span class="text-gray-500">Generated:</span> <span class="font-medium">{self._escape(self.alert_summary.generated_timestamp)}</span></p>
                    </div>
                </div>

                <!-- Trader Info -->
                <div>
                    <h4 class="text-sm font-medium text-gray-700 mb-3">Trader Information</h4>
                    <div class="space-y-2 text-sm">
                        <p><span class="text-gray-500">Trader ID:</span> <span class="font-mono">{self._escape(self.alert_summary.trader_id)}</span></p>
                        <p><span class="text-gray-500">Name:</span> <span class="font-medium">{self._escape(self.alert_summary.trader_name)}</span></p>
                        <p><span class="text-gray-500">Department:</span> <span class="font-medium">{self._escape(self.alert_summary.trader_department)}</span></p>
                    </div>
                </div>
            </div>

            <!-- Trade Details -->
            <div class="mt-6 pt-4 border-t border-gray-200">
                <h4 class="text-sm font-medium text-gray-700 mb-3">Suspicious Trade Details</h4>
                <div class="bg-gray-50 rounded-lg p-4">
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                        <div>
                            <p class="text-xs text-gray-500 uppercase">Symbol</p>
                            <p class="text-lg font-bold text-gray-900">{self._escape(self.alert_summary.symbol)}</p>
                        </div>
                        <div>
                            <p class="text-xs text-gray-500 uppercase">Side</p>
                            <p class="text-lg font-bold {side_color}">{self._escape(self.alert_summary.side)}</p>
                        </div>
                        <div>
                            <p class="text-xs text-gray-500 uppercase">Quantity</p>
                            <p class="text-lg font-bold text-gray-900">{self._format_number(self.alert_summary.quantity)}</p>
                        </div>
                        <div>
                            <p class="text-xs text-gray-500 uppercase">Price</p>
                            <p class="text-lg font-bold text-gray-900">{self._format_currency(self.alert_summary.price)}</p>
                        </div>
                    </div>
                    <div class="mt-4 pt-4 border-t border-gray-200 grid grid-cols-2 gap-4 text-center">
                        <div>
                            <p class="text-xs text-gray-500 uppercase">Total Value</p>
                            <p class="text-xl font-bold text-blue-600">{self._format_currency(self.alert_summary.total_value)}</p>
                        </div>
                        <div>
                            <p class="text-xs text-gray-500 uppercase">Trade Date</p>
                            <p class="text-lg font-medium text-gray-700">{self._escape(self.alert_summary.trade_date)}</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Anomaly Indicators -->
            <div class="mt-6 pt-4 border-t border-gray-200">
                <h4 class="text-sm font-medium text-gray-700 mb-3">SMARTS Anomaly Indicators</h4>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div class="bg-red-50 rounded-lg p-3 text-center">
                        <p class="text-xs text-gray-500 uppercase">Anomaly Score</p>
                        <p class="text-2xl font-bold text-red-600">{self.alert_summary.anomaly_score}</p>
                    </div>
                    <div class="bg-orange-50 rounded-lg p-3 text-center">
                        <p class="text-xs text-gray-500 uppercase">Confidence</p>
                        <p class="text-lg font-bold text-orange-600">{self._escape(self.alert_summary.confidence_level)}</p>
                    </div>
                    <div class="bg-purple-50 rounded-lg p-3 text-center">
                        <p class="text-xs text-gray-500 uppercase">Est. Profit</p>
                        <p class="text-lg font-bold text-purple-600">{self._format_currency(self.alert_summary.estimated_profit)}</p>
                    </div>
                    <div class="bg-blue-50 rounded-lg p-3">
                        <p class="text-xs text-gray-500 uppercase">Temporal Proximity</p>
                        <p class="text-sm font-medium text-blue-700">{self._escape(self.alert_summary.temporal_proximity)}</p>
                    </div>
                </div>
            </div>

            {related_event_html}
        </section>"""

    def _render_analysis_section(self) -> str:
        """Render the AI analysis findings section.

        Returns:
            HTML string for analysis section
        """
        # Key findings
        findings_html = "\n".join([
            f'<li class="flex items-start"><span class="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-800 rounded-full flex items-center justify-center text-xs font-bold mr-3">{i}</span><span>{self._escape(finding)}</span></li>'
            for i, finding in enumerate(self.decision.key_findings, 1)
        ])

        # Favorable indicators
        favorable_html = "\n".join([
            f'<li class="flex items-start"><svg class="w-4 h-4 text-red-500 mr-2 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path></svg><span class="text-gray-700">{self._escape(indicator)}</span></li>'
            for indicator in self.decision.favorable_indicators
        ])

        # Risk mitigating factors
        mitigating_html = "\n".join([
            f'<li class="flex items-start"><svg class="w-4 h-4 text-green-500 mr-2 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg><span class="text-gray-700">{self._escape(factor)}</span></li>'
            for factor in self.decision.risk_mitigating_factors
        ])

        return f"""
        <!-- AI Analysis Section -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path>
                </svg>
                AI Analysis Insights
            </h2>

            <!-- Key Findings -->
            <div class="mb-6">
                <h3 class="text-sm font-medium text-gray-700 mb-3">Key Findings</h3>
                <ol class="space-y-3 text-sm">
                    {findings_html}
                </ol>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Favorable Indicators -->
                <div class="bg-red-50 rounded-lg p-4">
                    <h3 class="text-sm font-medium text-red-800 mb-3 flex items-center">
                        <svg class="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path></svg>
                        Favorable Indicators (Suggesting Genuine)
                    </h3>
                    <ul class="space-y-2 text-sm">
                        {favorable_html}
                    </ul>
                </div>

                <!-- Risk Mitigating Factors -->
                <div class="bg-green-50 rounded-lg p-4">
                    <h3 class="text-sm font-medium text-green-800 mb-3 flex items-center">
                        <svg class="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>
                        Risk Mitigating Factors (Suggesting False Positive)
                    </h3>
                    <ul class="space-y-2 text-sm">
                        {mitigating_html}
                    </ul>
                </div>
            </div>
        </section>"""

    def _render_baseline_analysis_section(self) -> str:
        """Render the trader baseline analysis section.

        Returns:
            HTML string for baseline analysis section
        """
        baseline = self.decision.trader_baseline_analysis

        return f"""
        <!-- Trader Baseline Analysis -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
                </svg>
                Trader Baseline Analysis
            </h2>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-1">Typical Volume</p>
                    <p class="text-sm text-gray-800">{self._escape(baseline.typical_volume)}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-1">Typical Sectors</p>
                    <p class="text-sm text-gray-800">{self._escape(baseline.typical_sectors)}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-1">Trading Frequency</p>
                    <p class="text-sm text-gray-800">{self._escape(baseline.typical_frequency)}</p>
                </div>
            </div>

            <div class="bg-amber-50 border border-amber-200 rounded-lg p-4">
                <p class="text-xs text-amber-700 uppercase font-medium mb-1">Deviation Assessment</p>
                <p class="text-sm text-amber-900">{self._escape(baseline.deviation_assessment)}</p>
            </div>
        </section>"""

    def _render_market_context_section(self) -> str:
        """Render the market context section.

        Returns:
            HTML string for market context section
        """
        context = self.decision.market_context

        return f"""
        <!-- Market Context -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-teal-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"></path>
                </svg>
                Market Context
            </h2>

            <div class="space-y-4">
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-2">News Timeline</p>
                    <p class="text-sm text-gray-800">{self._escape(context.news_timeline)}</p>
                </div>

                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-2">Volatility Assessment</p>
                    <p class="text-sm text-gray-800">{self._escape(context.volatility_assessment)}</p>
                </div>

                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-2">Peer Activity Summary</p>
                    <p class="text-sm text-gray-800">{self._escape(context.peer_activity_summary)}</p>
                </div>
            </div>
        </section>"""

    def _render_reasoning_section(self) -> str:
        """Render the detailed reasoning narrative section.

        Returns:
            HTML string for reasoning section
        """
        # Split narrative into paragraphs for better formatting
        paragraphs = self.decision.reasoning_narrative.split("\n\n")
        paragraphs_html = "\n".join([
            f'<p class="text-gray-700 leading-relaxed mb-4">{self._escape(p)}</p>'
            for p in paragraphs if p.strip()
        ])

        return f"""
        <!-- Detailed Reasoning -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                </svg>
                Detailed Reasoning
            </h2>

            <div class="prose prose-sm max-w-none">
                {paragraphs_html}
            </div>
        </section>"""

    def _render_data_gaps_section(self) -> str:
        """Render the data gaps section (if any).

        Returns:
            HTML string for data gaps section, or empty string if no gaps
        """
        if not self.decision.data_gaps:
            return ""

        gaps_html = "\n".join([
            f'<li class="flex items-start"><svg class="w-4 h-4 text-gray-400 mr-2 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"></path></svg><span class="text-gray-600">{self._escape(gap)}</span></li>'
            for gap in self.decision.data_gaps
        ])

        return f"""
        <!-- Data Gaps -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                </svg>
                Data Gaps &amp; Recommended Additional Investigation
            </h2>

            <p class="text-sm text-gray-600 mb-3">The following data would improve the analysis:</p>
            <ul class="space-y-2 text-sm">
                {gaps_html}
            </ul>
        </section>"""

    def _render_footer(self) -> str:
        """Render the report footer.

        Returns:
            HTML string for footer
        """
        return """
        <!-- Footer -->
        <footer class="text-center py-6 border-t border-gray-200 mt-8">
            <p class="text-sm text-gray-500">
                Generated by <span class="font-medium">SMARTS Alert False Positive Analyzer</span>
            </p>
            <p class="text-xs text-gray-400 mt-1">
                AI-Powered Compliance Analysis | For Internal Use Only
            </p>
        </footer>"""
