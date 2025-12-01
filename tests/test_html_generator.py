"""Tests for HTML report generator.

This module contains unit tests for the HTMLReportGenerator class,
ensuring proper HTML generation for alert analysis reports.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from alerts.models import (
    AlertDecision,
    AlertSummary,
    MarketContext,
    TraderBaselineAnalysis,
)
from alerts.reports.html_generator import HTMLReportGenerator


@pytest.fixture
def sample_alert_summary() -> AlertSummary:
    """Create a sample AlertSummary for testing."""
    return AlertSummary(
        alert_id="TEST-001",
        alert_type="Pre-Announcement Trading",
        rule_violated="MAR-03-001",
        generated_timestamp="2024-03-16T10:30:00Z",
        trader_id="T001",
        trader_name="John Smith",
        trader_department="Operations",
        symbol="ACME",
        trade_date="2024-03-15",
        side="BUY",
        quantity=50000,
        price=101.50,
        total_value=5075000.00,
        anomaly_score=87,
        confidence_level="HIGH",
        temporal_proximity="36 hours before M&A announcement",
        estimated_profit=675000.00,
        related_event_type="M&A Announcement",
        related_event_date="2024-03-16",
        related_event_description="ACME Corp acquired by TechGiant for $150/share",
    )


@pytest.fixture
def sample_decision() -> AlertDecision:
    """Create a sample AlertDecision for testing."""
    return AlertDecision(
        alert_id="TEST-001",
        determination="ESCALATE",
        genuine_alert_confidence=95,
        false_positive_confidence=5,
        key_findings=[
            "Severe baseline deviation: 50k shares is 36x average volume",
            "Trading explicitly prohibited for back-office Operations role",
            "Trade 36 hours before M&A announcement with zero prior news",
        ],
        favorable_indicators=[
            "Extreme volume outlier (36x normal)",
            "Perfect pre-announcement timing",
        ],
        risk_mitigating_factors=[
            "Low formal MNPI access",
            "Mild pre-event market uptrend",
        ],
        trader_baseline_analysis=TraderBaselineAnalysis(
            typical_volume="~1,380 shares per trade average",
            typical_sectors="Exclusively TECH (100% historical)",
            typical_frequency="Weekly (1 trade/week)",
            deviation_assessment="Extreme anomaly: 36x volume spike",
        ),
        market_context=MarketContext(
            news_timeline="No significant news 2024-03-01 to 03-15",
            volatility_assessment="Steady uptrend with mild spike on 03-15",
            peer_activity_summary="Unanimous SELLING by peers",
        ),
        reasoning_narrative="This alert presents a textbook case of potential insider trading.\n\nMultiple red flags converge including severe baseline deviation and suspicious timing.",
        similar_precedent="Most closely resembles ex_001 (genuine_clear)",
        recommended_action="ESCALATE",
        data_gaps=["Trader communications/logs", "Options flow data"],
        timestamp=datetime(2024, 3, 20, 14, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_close_decision() -> AlertDecision:
    """Create a sample CLOSE AlertDecision for testing."""
    return AlertDecision(
        alert_id="TEST-002",
        determination="CLOSE",
        genuine_alert_confidence=15,
        false_positive_confidence=85,
        key_findings=[
            "Trade within normal baseline parameters",
            "Public news available prior to trade",
        ],
        favorable_indicators=["Timing coincidence"],
        risk_mitigating_factors=[
            "Consistent with trader's historical pattern",
            "Public catalyst available",
        ],
        trader_baseline_analysis=TraderBaselineAnalysis(
            typical_volume="15,000 shares per trade average",
            typical_sectors="Tech sector primarily",
            typical_frequency="Daily active trader",
            deviation_assessment="Within normal parameters",
        ),
        market_context=MarketContext(
            news_timeline="Analyst upgrade published on 03-14",
            volatility_assessment="Normal market conditions",
            peer_activity_summary="Mixed activity, both buying and selling",
        ),
        reasoning_narrative="This alert appears to be a false positive based on the comprehensive evidence review. The trader's activity is consistent with their historical patterns and public information was available.",
        similar_precedent="Resembles ex_002 (false_positive_clear)",
        recommended_action="CLOSE",
        data_gaps=[],
        timestamp=datetime(2024, 3, 20, 14, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_review_decision() -> AlertDecision:
    """Create a sample NEEDS_HUMAN_REVIEW AlertDecision for testing."""
    return AlertDecision(
        alert_id="TEST-003",
        determination="NEEDS_HUMAN_REVIEW",
        genuine_alert_confidence=50,
        false_positive_confidence=50,
        key_findings=[
            "Conflicting signals require human judgment",
            "Some deviation from baseline but not extreme",
        ],
        favorable_indicators=["Slightly elevated volume"],
        risk_mitigating_factors=["Partial news coverage available"],
        trader_baseline_analysis=TraderBaselineAnalysis(
            typical_volume="10,000 shares average",
            typical_sectors="Mixed",
            typical_frequency="Weekly",
            deviation_assessment="Moderate deviation",
        ),
        market_context=MarketContext(
            news_timeline="Partial news coverage",
            volatility_assessment="Elevated volatility",
            peer_activity_summary="Mixed signals",
        ),
        reasoning_narrative="This case presents ambiguous signals that require human review. The evidence is conflicting and does not clearly support either escalation or closure. Additional investigation is recommended.",
        similar_precedent="Similar to ex_003 (ambiguous)",
        recommended_action="MONITOR",
        data_gaps=["Additional context needed"],
        timestamp=datetime(2024, 3, 20, 14, 0, 0, tzinfo=timezone.utc),
    )


class TestHTMLReportGenerator:
    """Test suite for HTMLReportGenerator class."""

    def test_init(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test HTMLReportGenerator initialization."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)

        assert generator.alert_summary == sample_alert_summary
        assert generator.decision == sample_decision

    def test_generate_produces_valid_html(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generate() produces valid HTML document."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        # Check HTML structure
        assert html.startswith("<!DOCTYPE html>")
        assert "<html lang=\"en\">" in html
        assert "</html>" in html
        assert "<head>" in html
        assert "</head>" in html
        assert "<body" in html
        assert "</body>" in html

    def test_generate_includes_tailwind_cdn(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes Tailwind CSS CDN."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        assert "cdn.tailwindcss.com" in html

    def test_generate_includes_alert_id(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes alert ID."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        assert "TEST-001" in html
        assert sample_decision.alert_id in html

    def test_generate_includes_determination_badge_escalate(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that ESCALATE determination has correct badge styling."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        # Should have red badge for ESCALATE
        assert "bg-red-600" in html
        assert "ESCALATE" in html

    def test_generate_includes_determination_badge_close(
        self, sample_alert_summary: AlertSummary, sample_close_decision: AlertDecision
    ):
        """Test that CLOSE determination has correct badge styling."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_close_decision)
        html = generator.generate()

        # Should have green badge for CLOSE
        assert "bg-green-600" in html
        assert "CLOSE" in html

    def test_generate_includes_determination_badge_review(
        self, sample_alert_summary: AlertSummary, sample_review_decision: AlertDecision
    ):
        """Test that NEEDS_HUMAN_REVIEW determination has correct badge styling."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_review_decision)
        html = generator.generate()

        # Should have yellow badge for NEEDS_HUMAN_REVIEW
        assert "bg-yellow-500" in html
        assert "NEEDS HUMAN REVIEW" in html

    def test_generate_includes_confidence_scores(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes confidence scores."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        assert "95%" in html  # genuine_alert_confidence
        assert "5%" in html  # false_positive_confidence

    def test_generate_includes_trader_info(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes trader information."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        assert "John Smith" in html
        assert "T001" in html
        assert "Operations" in html

    def test_generate_includes_trade_details(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes trade details."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        assert "ACME" in html
        assert "BUY" in html
        assert "50,000" in html  # formatted quantity
        assert "$101.50" in html  # formatted price

    def test_generate_includes_anomaly_indicators(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes anomaly indicators."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        assert "87" in html  # anomaly score
        assert "HIGH" in html  # confidence level
        assert "$675,000.00" in html  # estimated profit

    def test_generate_includes_key_findings(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes key findings."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        for finding in sample_decision.key_findings:
            # Account for HTML escaping (& becomes &amp;)
            escaped_finding = finding.replace("&", "&amp;")
            assert escaped_finding in html

    def test_generate_includes_favorable_indicators(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes favorable indicators."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        for indicator in sample_decision.favorable_indicators:
            assert indicator in html

    def test_generate_includes_risk_mitigating_factors(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes risk mitigating factors."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        for factor in sample_decision.risk_mitigating_factors:
            assert factor in html

    def test_generate_includes_baseline_analysis(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes trader baseline analysis."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        baseline = sample_decision.trader_baseline_analysis
        assert baseline.typical_volume in html
        assert baseline.typical_sectors in html
        assert baseline.typical_frequency in html
        assert baseline.deviation_assessment in html

    def test_generate_includes_market_context(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes market context."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        context = sample_decision.market_context
        assert context.news_timeline in html
        assert context.volatility_assessment in html
        assert context.peer_activity_summary in html

    def test_generate_includes_reasoning_narrative(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes reasoning narrative."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        # Check for parts of the narrative (may be split into paragraphs)
        assert "textbook case" in html

    def test_generate_includes_data_gaps(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes data gaps section."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        for gap in sample_decision.data_gaps:
            assert gap in html

    def test_generate_excludes_data_gaps_when_empty(
        self, sample_alert_summary: AlertSummary, sample_close_decision: AlertDecision
    ):
        """Test that data gaps section is excluded when empty."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_close_decision)
        html = generator.generate()

        # Should not have the data gaps heading when no gaps
        # The section should be completely absent
        assert "Data Gaps" not in html or sample_close_decision.data_gaps

    def test_generate_includes_related_event(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes related event when present."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        assert "M&amp;A Announcement" in html or "M&A Announcement" in html
        assert "TechGiant" in html

    def test_generate_excludes_related_event_when_missing(
        self, sample_decision: AlertDecision
    ):
        """Test that related event section is excluded when not present."""
        # Create alert summary without related event
        summary = AlertSummary(
            alert_id="TEST-004",
            alert_type="Pattern Detection",
            rule_violated="MAR-01-001",
            generated_timestamp="2024-03-16T10:30:00Z",
            trader_id="T002",
            trader_name="Jane Doe",
            trader_department="Sales",
            symbol="XYZ",
            trade_date="2024-03-15",
            side="SELL",
            quantity=1000,
            price=50.00,
            total_value=50000.00,
            anomaly_score=45,
            confidence_level="MEDIUM",
            temporal_proximity="N/A",
            estimated_profit=5000.00,
            related_event_type=None,
            related_event_date=None,
            related_event_description=None,
        )

        generator = HTMLReportGenerator(summary, sample_decision)
        html = generator.generate()

        # Related event section should not appear
        assert "Related Event" not in html

    def test_generate_escapes_html_special_chars(
        self, sample_decision: AlertDecision
    ):
        """Test that HTML special characters are properly escaped."""
        # Create summary with special characters
        summary = AlertSummary(
            alert_id="TEST-XSS",
            alert_type="Test & Alert",
            rule_violated="MAR-03-001",
            generated_timestamp="2024-03-16T10:30:00Z",
            trader_id="T001",
            trader_name="John <test> Smith",
            trader_department="Operations",
            symbol="ACME",
            trade_date="2024-03-15",
            side="BUY",
            quantity=50000,
            price=101.50,
            total_value=5075000.00,
            anomaly_score=87,
            confidence_level="HIGH",
            temporal_proximity="36 hours",
            estimated_profit=675000.00,
        )

        generator = HTMLReportGenerator(summary, sample_decision)
        html = generator.generate()

        # Special characters should be escaped
        # & should become &amp;
        assert "Test &amp; Alert" in html
        # < and > in names should be escaped
        assert "John &lt;test&gt; Smith" in html
        # No raw < or > should appear in trader name context
        assert "John <test> Smith" not in html

    def test_format_currency(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test currency formatting."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)

        assert generator._format_currency(1000.00) == "$1,000.00"
        assert generator._format_currency(5075000.00) == "$5,075,000.00"
        assert generator._format_currency(0.99) == "$0.99"

    def test_format_number(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test number formatting with thousand separators."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)

        assert generator._format_number(1000) == "1,000"
        assert generator._format_number(50000) == "50,000"
        assert generator._format_number(1234567) == "1,234,567"

    def test_confidence_color_high(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test confidence color for high values."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)

        assert generator._get_confidence_color(95) == "text-red-600"
        assert generator._get_confidence_color(70) == "text-red-600"

    def test_confidence_color_medium(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test confidence color for medium values."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)

        assert generator._get_confidence_color(50) == "text-yellow-600"
        assert generator._get_confidence_color(40) == "text-yellow-600"

    def test_confidence_color_low(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test confidence color for low values."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)

        assert generator._get_confidence_color(30) == "text-green-600"
        assert generator._get_confidence_color(0) == "text-green-600"


class TestHTMLReportGeneratorXMLParsing:
    """Test suite for XML parsing functionality."""

    def test_from_xml_file_parses_valid_xml(
        self, test_data_dir: Path, sample_decision: AlertDecision
    ):
        """Test that from_xml_file correctly parses valid XML."""
        xml_path = test_data_dir / "alerts" / "alert_genuine.xml"

        generator = HTMLReportGenerator.from_xml_file(xml_path, sample_decision)

        assert generator.alert_summary.alert_id == "ITA-2024-001847"
        assert generator.alert_summary.trader_name == "John Smith"
        assert generator.alert_summary.symbol == "ACME"
        assert generator.alert_summary.quantity == 50000

    def test_from_xml_file_raises_on_missing_file(
        self, sample_decision: AlertDecision
    ):
        """Test that from_xml_file raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            HTMLReportGenerator.from_xml_file(
                Path("/nonexistent/path.xml"), sample_decision
            )

    def test_parse_alert_xml_extracts_all_fields(self, test_data_dir: Path):
        """Test that _parse_alert_xml extracts all expected fields."""
        xml_path = test_data_dir / "alerts" / "alert_genuine.xml"

        summary = HTMLReportGenerator._parse_alert_xml(xml_path)

        assert summary.alert_id == "ITA-2024-001847"
        assert summary.alert_type == "Pre-Announcement Trading"
        assert summary.rule_violated == "MAR-03-001"
        assert summary.trader_id == "T001"
        assert summary.trader_name == "John Smith"
        assert summary.trader_department == "Operations"
        assert summary.symbol == "ACME"
        assert summary.side == "BUY"
        assert summary.quantity == 50000
        assert summary.price == 101.50
        assert summary.total_value == 5075000.0
        assert summary.anomaly_score == 87
        assert summary.confidence_level == "HIGH"
        assert summary.estimated_profit == 675000.0
        assert summary.related_event_type == "M&A Announcement"


class TestHTMLReportGeneratorIntegration:
    """Integration tests for full HTML generation workflow."""

    def test_full_generation_workflow(
        self, test_data_dir: Path, tmp_path: Path
    ):
        """Test complete workflow from XML to HTML output."""
        xml_path = test_data_dir / "alerts" / "alert_genuine.xml"

        # Create a realistic decision
        decision = AlertDecision(
            alert_id="ITA-2024-001847",
            determination="ESCALATE",
            genuine_alert_confidence=95,
            false_positive_confidence=5,
            key_findings=["Severe baseline deviation"],
            favorable_indicators=["Perfect timing"],
            risk_mitigating_factors=["Low access level"],
            trader_baseline_analysis=TraderBaselineAnalysis(
                typical_volume="1,380 shares",
                typical_sectors="TECH",
                typical_frequency="Weekly",
                deviation_assessment="Extreme anomaly",
            ),
            market_context=MarketContext(
                news_timeline="No news",
                volatility_assessment="Stable",
                peer_activity_summary="Selling",
            ),
            reasoning_narrative="This is a test narrative with sufficient length to pass validation requirements. The analysis indicates potential insider trading based on multiple factors.",
            similar_precedent="ex_001",
            recommended_action="ESCALATE",
            data_gaps=["Communication logs"],
        )

        # Generate HTML
        generator = HTMLReportGenerator.from_xml_file(xml_path, decision)
        html = generator.generate()

        # Write to file
        output_path = tmp_path / "test_report.html"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Verify file was created and has content
        assert output_path.exists()
        assert output_path.stat().st_size > 0

        # Read back and verify
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "ITA-2024-001847" in content
        assert "ESCALATE" in content
        assert "John Smith" in content

    def test_html_has_proper_responsive_classes(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that generated HTML includes responsive Tailwind classes."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        # Check for responsive classes
        assert "max-w-" in html  # Max width container
        assert "md:" in html  # Medium breakpoint responsive classes
        assert "px-" in html  # Padding
        assert "py-" in html  # Padding

    def test_html_sections_are_present(
        self, sample_alert_summary: AlertSummary, sample_decision: AlertDecision
    ):
        """Test that all major sections are present in HTML."""
        generator = HTMLReportGenerator(sample_alert_summary, sample_decision)
        html = generator.generate()

        # All major sections should be present
        assert "SMARTS Alert Analysis Report" in html
        assert "Original SMARTS Alert" in html
        assert "AI Analysis Insights" in html
        assert "Trader Baseline Analysis" in html
        assert "Market Context" in html
        assert "Detailed Reasoning" in html
