"""HTML report generator for Wash Trade alerts.

This module generates professional HTML reports with Tailwind CSS
for wash trade analysis. Interactive relationship network visualization
is powered by Cytoscape.js via the wash_trade_graph module.
"""

import html
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from alerts.models.wash_trade import WashTradeDecision
from alerts.reports.wash_trade_graph import render_relationship_network_graph

logger = logging.getLogger(__name__)


class WashTradeAlertSummary:
    """Summary of wash trade alert data extracted from XML."""

    def __init__(
        self,
        alert_id: str,
        alert_type: str,
        rule_violated: str,
        generated_timestamp: str,
        severity: str,
        anomaly_score: int,
        confidence_level: str,
        trades: List[Dict],
        wash_indicators: Dict,
        market_context: Dict,
        regulatory_flags: List[str],
        investigation_notes: List[str],
    ):
        """Initialize wash trade alert summary."""
        self.alert_id = alert_id
        self.alert_type = alert_type
        self.rule_violated = rule_violated
        self.generated_timestamp = generated_timestamp
        self.severity = severity
        self.anomaly_score = anomaly_score
        self.confidence_level = confidence_level
        self.trades = trades
        self.wash_indicators = wash_indicators
        self.market_context = market_context
        self.regulatory_flags = regulatory_flags
        self.investigation_notes = investigation_notes


class WashTradeHTMLReportGenerator:
    """Generates HTML reports for wash trade analysis with SVG network visualization.

    This generator creates professional, Tailwind CSS-styled reports
    that display wash trade alerts with relationship network diagrams.

    Attributes:
        alert_summary: Parsed wash trade alert data from XML
        decision: AI-generated wash trade analysis decision
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

    # Pattern type colors
    PATTERN_COLORS = {
        "DIRECT_WASH": "bg-red-100 text-red-800 border-red-300",
        "LAYERED_WASH": "bg-orange-100 text-orange-800 border-orange-300",
        "INTERMEDIARY_WASH": "bg-yellow-100 text-yellow-800 border-yellow-300",
        "NO_PATTERN": "bg-green-100 text-green-800 border-green-300",
    }

    def __init__(
        self,
        alert_summary: WashTradeAlertSummary,
        decision: WashTradeDecision,
    ) -> None:
        """Initialize the HTML report generator.

        Args:
            alert_summary: Parsed wash trade alert data from XML
            decision: AI-generated wash trade analysis decision
        """
        self.alert_summary = alert_summary
        self.decision = decision
        self.logger = logger

    @classmethod
    def from_xml_file(
        cls,
        alert_xml_path: Path,
        decision: WashTradeDecision,
    ) -> "WashTradeHTMLReportGenerator":
        """Create generator from XML file path.

        Args:
            alert_xml_path: Path to the wash trade alert XML file
            decision: AI-generated wash trade analysis decision

        Returns:
            WashTradeHTMLReportGenerator instance

        Raises:
            FileNotFoundError: If XML file doesn't exist
            ValueError: If XML parsing fails
        """
        alert_summary = cls._parse_wash_trade_xml(alert_xml_path)
        return cls(alert_summary, decision)

    @staticmethod
    def _parse_wash_trade_xml(xml_path: Path) -> WashTradeAlertSummary:
        """Parse wash trade alert XML file into WashTradeAlertSummary.

        Args:
            xml_path: Path to the XML file

        Returns:
            WashTradeAlertSummary with parsed data

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If XML is malformed
        """
        logger.info(f"Parsing wash trade alert XML: {xml_path}")

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

            # Parse trades
            trades = []
            for trade_elem in root.findall(".//FlaggedTrades/Trade"):
                trade = {}
                for child in trade_elem:
                    trade[child.tag] = child.text
                if trade.get("sequence"):
                    trade["sequence"] = trade_elem.get("sequence")
                trades.append(trade)

            # Parse wash indicators
            wash_indicators = {}
            indicators_elem = root.find(".//WashTradeIndicators")
            if indicators_elem is not None:
                for child in indicators_elem:
                    wash_indicators[child.tag] = child.text

            # Parse market context
            market_context = {}
            context_elem = root.find(".//MarketContext")
            if context_elem is not None:
                for child in context_elem:
                    market_context[child.tag] = child.text

            # Parse regulatory flags
            regulatory_flags = []
            for reg in root.findall(".//ApplicableRegulations/Regulation"):
                if reg.text:
                    regulatory_flags.append(reg.text)

            # Parse investigation notes
            investigation_notes = []
            for note in root.findall(".//InvestigationNotes/Note"):
                if note.text:
                    investigation_notes.append(note.text)

            return WashTradeAlertSummary(
                alert_id=get_text(".//AlertID", "UNKNOWN"),
                alert_type=get_text(".//AlertType", "WashTrade"),
                rule_violated=get_text(".//RuleViolated", "Unknown"),
                generated_timestamp=get_text(".//GeneratedTimestamp", "Unknown"),
                severity=get_text(".//Severity", "MEDIUM"),
                anomaly_score=get_int(".//AnomalyScore"),
                confidence_level=get_text(".//ConfidenceLevel", "Unknown"),
                trades=trades,
                wash_indicators=wash_indicators,
                market_context=market_context,
                regulatory_flags=regulatory_flags,
                investigation_notes=investigation_notes,
            )

        except ET.ParseError as e:
            raise ValueError(f"Failed to parse XML: {e}") from e

    def generate(self) -> str:
        """Generate complete HTML report.

        Returns:
            Complete HTML document as string
        """
        self.logger.info(f"Generating wash trade HTML report for alert: {self.decision.alert_id}")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wash Trade Analysis Report - {self._escape(self.decision.alert_id)}</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen">
    <div class="max-w-6xl mx-auto py-8 px-4">
        {self._render_header()}
        {self._render_determination_banner()}
        {self._render_relationship_network()}
        {self._render_alert_section()}
        {self._render_timing_analysis_section()}
        {self._render_counterparty_analysis_section()}
        {self._render_historical_patterns_section()}
        {self._render_regulatory_section()}
        {self._render_reasoning_section()}
        {self._render_footer()}
    </div>
</body>
</html>"""

    def _escape(self, text: str) -> str:
        """Escape HTML special characters."""
        return html.escape(str(text)) if text else ""

    def _format_currency(self, value: float) -> str:
        """Format value as currency."""
        return f"${value:,.2f}"

    def _format_number(self, value: int) -> str:
        """Format number with thousand separators."""
        return f"{value:,}"

    def _render_header(self) -> str:
        """Render the report header section."""
        timestamp = self.decision.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

        return f"""
        <!-- Header -->
        <header class="bg-white rounded-lg shadow-md p-6 mb-6">
            <div class="flex justify-between items-start">
                <div>
                    <h1 class="text-2xl font-bold text-gray-900">Wash Trade Analysis Report</h1>
                    <p class="text-gray-600 mt-1">AI-Powered Compliance Analysis | APAC Regulatory Framework</p>
                </div>
                <div class="text-right">
                    <p class="text-sm text-gray-500">Report Generated</p>
                    <p class="text-sm font-medium text-gray-700">{self._escape(timestamp)}</p>
                </div>
            </div>
            <div class="mt-4 pt-4 border-t border-gray-200 flex flex-wrap gap-4">
                <div>
                    <span class="text-sm text-gray-600">Alert ID:</span>
                    <span class="font-mono bg-gray-100 px-2 py-1 rounded ml-2">{self._escape(self.decision.alert_id)}</span>
                </div>
                <div>
                    <span class="text-sm text-gray-600">Severity:</span>
                    <span class="px-2 py-1 rounded text-sm font-medium ml-2 {self._get_severity_color(self.alert_summary.severity)}">
                        {self._escape(self.alert_summary.severity)}
                    </span>
                </div>
            </div>
        </header>"""

    def _get_severity_color(self, severity: str) -> str:
        """Get color class for severity level."""
        colors = {
            "CRITICAL": "bg-red-100 text-red-800",
            "HIGH": "bg-orange-100 text-orange-800",
            "MEDIUM": "bg-yellow-100 text-yellow-800",
            "LOW": "bg-green-100 text-green-800",
        }
        return colors.get(severity.upper(), "bg-gray-100 text-gray-800")

    def _render_determination_banner(self) -> str:
        """Render the determination banner with pattern classification."""
        colors = self.DETERMINATION_COLORS.get(
            self.decision.determination,
            self.DETERMINATION_COLORS["NEEDS_HUMAN_REVIEW"]
        )
        pattern_color = self.PATTERN_COLORS.get(
            self.decision.relationship_network.pattern_type,
            self.PATTERN_COLORS["NO_PATTERN"]
        )

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
                        <p class="text-sm text-gray-500">Genuine Wash Trade</p>
                        <p class="text-2xl font-bold text-red-600">{self.decision.genuine_alert_confidence}%</p>
                    </div>
                    <div class="text-center">
                        <p class="text-sm text-gray-500">False Positive</p>
                        <p class="text-2xl font-bold text-green-600">{self.decision.false_positive_confidence}%</p>
                    </div>
                </div>
            </div>
            <div class="mt-4 pt-4 border-t border-gray-200 flex flex-wrap gap-4">
                <div>
                    <span class="text-sm text-gray-500">Pattern Detected:</span>
                    <span class="ml-2 px-3 py-1 rounded-full text-sm font-medium border {pattern_color}">
                        {self._escape(self.decision.relationship_network.pattern_type.replace('_', ' '))}
                    </span>
                </div>
                <div>
                    <span class="text-sm text-gray-500">Volume Impact:</span>
                    <span class="ml-2 font-medium text-gray-700">{self.decision.volume_impact_percentage:.1f}%</span>
                </div>
                <div>
                    <span class="text-sm text-gray-500">Same Beneficial Owner:</span>
                    <span class="ml-2 font-medium {'text-red-600' if self.decision.beneficial_ownership_match else 'text-green-600'}">
                        {'Yes' if self.decision.beneficial_ownership_match else 'No'}
                    </span>
                </div>
            </div>
        </section>"""

    def _render_relationship_network(self) -> str:
        """Render the interactive Cytoscape.js relationship network.

        Delegates to the wash_trade_graph module for graph generation.
        """
        return render_relationship_network_graph(
            network=self.decision.relationship_network,
            escape_fn=self._escape
        )

    def _render_alert_section(self) -> str:
        """Render the original alert details with trades."""
        trades_html = ""
        for trade in self.alert_summary.trades:
            side_color = "text-green-600" if trade.get("Side") == "BUY" else "text-red-600"
            trades_html += f"""
                <div class="bg-gray-50 rounded-lg p-4 mb-3">
                    <div class="flex justify-between items-start mb-2">
                        <span class="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium">
                            Trade {trade.get('sequence', '?')}
                        </span>
                        <span class="text-sm text-gray-500">{self._escape(trade.get('TradeTime', ''))}</span>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                        <div>
                            <p class="text-gray-500 text-xs">Account</p>
                            <p class="font-medium">{self._escape(trade.get('AccountID', ''))}</p>
                            <p class="text-xs text-gray-400">{self._escape(trade.get('AccountName', ''))}</p>
                        </div>
                        <div>
                            <p class="text-gray-500 text-xs">Side / Symbol</p>
                            <p class="font-medium {side_color}">{self._escape(trade.get('Side', ''))}</p>
                            <p class="text-xs">{self._escape(trade.get('Symbol', ''))}</p>
                        </div>
                        <div>
                            <p class="text-gray-500 text-xs">Quantity / Price</p>
                            <p class="font-medium">{self._escape(trade.get('Quantity', ''))}</p>
                            <p class="text-xs">${self._escape(trade.get('Price', ''))}</p>
                        </div>
                        <div>
                            <p class="text-gray-500 text-xs">Counterparty</p>
                            <p class="font-medium">{self._escape(trade.get('CounterpartyAccount', 'MARKET'))}</p>
                        </div>
                    </div>
                </div>
            """

        # Wash indicators
        indicators = self.alert_summary.wash_indicators
        indicators_html = ""
        for key, value in indicators.items():
            indicators_html += f"""
                <div class="bg-gray-50 px-3 py-2 rounded">
                    <p class="text-xs text-gray-500">{self._escape(key)}</p>
                    <p class="font-medium text-sm">{self._escape(value or 'N/A')}</p>
                </div>
            """

        return f"""
        <!-- Original Alert Section -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                </svg>
                Flagged Trades
            </h2>

            {trades_html}

            <h3 class="text-md font-medium text-gray-800 mt-6 mb-3">Wash Trade Indicators</h3>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                {indicators_html}
            </div>
        </section>"""

    def _render_timing_analysis_section(self) -> str:
        """Render the timing analysis section."""
        timing = self.decision.timing_patterns

        pre_arranged_color = "text-red-600" if timing.is_pre_arranged else "text-green-600"

        return f"""
        <!-- Timing Analysis -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                Timing Analysis
            </h2>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Time Delta</p>
                    <p class="text-xl font-bold text-gray-900">{self._escape(timing.time_delta_description)}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Market Phase</p>
                    <p class="text-lg font-medium text-gray-700">{self._escape(timing.market_phase.replace('_', ' ').title())}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Liquidity</p>
                    <p class="text-lg font-medium text-gray-700">{self._escape(timing.liquidity_assessment.title())}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Pre-Arranged</p>
                    <p class="text-lg font-bold {pre_arranged_color}">
                        {'Yes' if timing.is_pre_arranged else 'No'} ({timing.pre_arrangement_confidence}%)
                    </p>
                </div>
            </div>

            <div class="bg-amber-50 border border-amber-200 rounded-lg p-4">
                <p class="text-sm text-amber-900">{self._escape(timing.timing_analysis)}</p>
            </div>
        </section>"""

    def _render_counterparty_analysis_section(self) -> str:
        """Render the counterparty analysis section."""
        cp = self.decision.counterparty_pattern

        # Trade flow visualization
        flow_html = ""
        for trade in cp.trade_flow:
            side_color = "bg-green-100 text-green-800" if trade.side == "BUY" else "bg-red-100 text-red-800"
            flow_html += f"""
                <div class="flex items-center">
                    <span class="w-8 h-8 rounded-full bg-blue-500 text-white flex items-center justify-center text-sm font-bold">
                        {trade.sequence_number}
                    </span>
                    <div class="ml-3">
                        <p class="font-medium">{self._escape(trade.account_id)}</p>
                        <p class="text-xs">
                            <span class="px-2 py-0.5 rounded {side_color}">{trade.side}</span>
                            {self._format_number(trade.quantity)} @ ${trade.price}
                        </p>
                    </div>
                </div>
            """

        return f"""
        <!-- Counterparty Analysis -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-teal-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"></path>
                </svg>
                Trade Flow Analysis
            </h2>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                    <h3 class="text-sm font-medium text-gray-700 mb-3">Trade Flow Sequence</h3>
                    <div class="space-y-4">
                        {flow_html}
                    </div>
                </div>

                <div>
                    <h3 class="text-sm font-medium text-gray-700 mb-3">Pattern Analysis</h3>
                    <div class="space-y-3">
                        <div class="flex justify-between items-center p-2 bg-gray-50 rounded">
                            <span class="text-sm text-gray-600">Circular Pattern</span>
                            <span class="font-medium {'text-red-600' if cp.is_circular else 'text-green-600'}">
                                {'Detected' if cp.is_circular else 'Not Detected'}
                            </span>
                        </div>
                        <div class="flex justify-between items-center p-2 bg-gray-50 rounded">
                            <span class="text-sm text-gray-600">Offsetting Trades</span>
                            <span class="font-medium {'text-red-600' if cp.is_offsetting else 'text-green-600'}">
                                {'Yes' if cp.is_offsetting else 'No'}
                            </span>
                        </div>
                        <div class="flex justify-between items-center p-2 bg-gray-50 rounded">
                            <span class="text-sm text-gray-600">Same Beneficial Owner</span>
                            <span class="font-medium {'text-red-600' if cp.same_beneficial_owner else 'text-green-600'}">
                                {'Yes' if cp.same_beneficial_owner else 'No'}
                            </span>
                        </div>
                        <div class="flex justify-between items-center p-2 bg-gray-50 rounded">
                            <span class="text-sm text-gray-600">Economic Purpose</span>
                            <span class="font-medium {'text-green-600' if cp.economic_purpose_identified else 'text-red-600'}">
                                {'Identified' if cp.economic_purpose_identified else 'Not Identified'}
                            </span>
                        </div>
                    </div>
                    {f'<div class="mt-3 p-3 bg-green-50 rounded"><p class="text-sm text-green-800">{self._escape(cp.economic_purpose_description)}</p></div>' if cp.economic_purpose_description else ''}
                </div>
            </div>
        </section>"""

    def _render_historical_patterns_section(self) -> str:
        """Render the historical patterns section."""
        hist = self.decision.historical_patterns

        trend_colors = {
            "increasing": "text-red-600",
            "stable": "text-yellow-600",
            "decreasing": "text-green-600",
            "new": "text-blue-600",
        }
        trend_color = trend_colors.get(hist.pattern_trend, "text-gray-600")

        return f"""
        <!-- Historical Patterns -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
                </svg>
                Historical Pattern Analysis
            </h2>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Similar Patterns</p>
                    <p class="text-2xl font-bold text-gray-900">{hist.pattern_count}</p>
                    <p class="text-xs text-gray-500">in last {hist.time_window_days} days</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Frequency</p>
                    <p class="text-lg font-medium text-gray-700">{self._escape(hist.average_frequency)}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Trend</p>
                    <p class="text-lg font-bold {trend_color}">{self._escape(hist.pattern_trend.title())}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Risk Level</p>
                    <p class="text-lg font-bold {'text-red-600' if hist.pattern_count >= 3 else 'text-yellow-600' if hist.pattern_count >= 1 else 'text-green-600'}">
                        {'High' if hist.pattern_count >= 3 else 'Medium' if hist.pattern_count >= 1 else 'Low'}
                    </p>
                </div>
            </div>

            <div class="bg-gray-50 rounded-lg p-4">
                <p class="text-sm text-gray-700">{self._escape(hist.historical_analysis)}</p>
            </div>
        </section>"""

    def _render_regulatory_section(self) -> str:
        """Render the regulatory flags section."""
        flags_html = ""
        for flag in self.decision.regulatory_flags:
            flags_html += f"""
                <div class="flex items-start p-3 bg-red-50 rounded-lg">
                    <svg class="w-5 h-5 text-red-500 mr-2 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                    </svg>
                    <span class="text-sm text-red-800">{self._escape(flag)}</span>
                </div>
            """

        if not flags_html:
            flags_html = '<p class="text-sm text-gray-500">No specific regulatory flags identified.</p>'

        return f"""
        <!-- Regulatory Flags -->
        <section class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                </svg>
                Regulatory Considerations (APAC Framework)
            </h2>

            <div class="space-y-3">
                {flags_html}
            </div>

            <div class="mt-4 p-4 bg-blue-50 rounded-lg">
                <p class="text-sm text-blue-800">
                    <span class="font-medium">Note:</span> This analysis applies APAC regulatory standards including
                    Singapore MAS SFA, Hong Kong SFC SFO, Australia ASIC Corporations Act, and Japan FSA FIEA.
                </p>
            </div>
        </section>"""

    def _render_reasoning_section(self) -> str:
        """Render the detailed reasoning narrative section."""
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

            <div class="mt-4 pt-4 border-t border-gray-200">
                <p class="text-sm text-gray-600">
                    <span class="font-medium">Similar Precedent:</span>
                    {self._escape(self.decision.similar_precedent)}
                </p>
            </div>
        </section>"""

    def _render_footer(self) -> str:
        """Render the report footer."""
        return """
        <!-- Footer -->
        <footer class="text-center py-6 border-t border-gray-200 mt-8">
            <p class="text-sm text-gray-500">
                Generated by <span class="font-medium">SMARTS Wash Trade Analyzer</span>
            </p>
            <p class="text-xs text-gray-400 mt-1">
                AI-Powered Compliance Analysis | APAC Regulatory Framework | For Internal Use Only
            </p>
        </footer>"""
