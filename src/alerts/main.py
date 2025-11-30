"""Main entry point for the SMARTS Alert Analyzer.

This module provides the CLI entry point for analyzing alerts.
"""

import argparse
import logging
import sys
from pathlib import Path

from langchain_openai import AzureChatOpenAI, ChatOpenAI

from alerts.agent import AlertAnalyzerAgent
from alerts.config import ConfigurationError, get_config, setup_logging

logger = logging.getLogger(__name__)


def create_llm(config):
    """Create LLM instance based on configuration.

    Args:
        config: AppConfig instance

    Returns:
        LangChain LLM instance (AzureChatOpenAI, ChatOpenAI, or ChatOpenAI with OpenRouter)
    """
    logger.info(f"Creating LLM with provider: {config.llm.provider}")

    if config.llm.is_azure():
        logger.info(f"Using Azure OpenAI: {config.llm.azure_endpoint}")
        return AzureChatOpenAI(
            azure_deployment=config.llm.model,
            azure_endpoint=config.llm.azure_endpoint,
            api_version=config.llm.azure_api_version,
            api_key=config.llm.api_key,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
    elif config.llm.provider == "openrouter":
        logger.info(f"Using OpenRouter: {config.llm.model}")

        # Build optional headers for site tracking
        default_headers = {}
        if config.llm.openrouter_site_url:
            default_headers["HTTP-Referer"] = config.llm.openrouter_site_url
            logger.debug(f"OpenRouter HTTP-Referer header set: {config.llm.openrouter_site_url}")
        if config.llm.openrouter_site_name:
            default_headers["X-Title"] = config.llm.openrouter_site_name
            logger.debug(f"OpenRouter X-Title header set: {config.llm.openrouter_site_name}")

        return ChatOpenAI(
            model=config.llm.model,
            api_key=config.llm.api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers=default_headers if default_headers else None,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
    else:
        logger.info(f"Using OpenAI: {config.llm.model}")
        return ChatOpenAI(
            model=config.llm.model,
            api_key=config.llm.api_key,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="SMARTS Alert False Positive Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze the default alert
  python -m alerts.main

  # Analyze a specific alert file
  python -m alerts.main --alert test_data/alerts/alert_genuine.xml

  # Run with verbose logging
  python -m alerts.main --verbose

  # Analyze the false positive test case
  python -m alerts.main --alert test_data/alerts/alert_false_positive.xml
        """
    )

    parser.add_argument(
        "--alert",
        type=str,
        default=None,
        help="Path to alert XML file to analyze (overrides ALERT_FILE_PATH env var)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging"
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Minimal output (WARNING level logging)"
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    args = parse_args()

    # Load configuration
    try:
        config = get_config()
    except ConfigurationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("Please check your .env file and environment variables.", file=sys.stderr)
        return 1

    # Override log level based on args
    if args.verbose:
        config.logging.level = "DEBUG"
    elif args.quiet:
        config.logging.level = "WARNING"

    # Setup logging
    setup_logging(config.logging)

    logger.info("=" * 60)
    logger.info("SMARTS Alert False Positive Analyzer")
    logger.info("=" * 60)

    # Determine alert file path
    if args.alert:
        alert_path = Path(args.alert)
    elif config.data.alert_file_path:
        alert_path = config.data.alert_file_path
    else:
        # Default to genuine alert
        alert_path = config.data.alerts_dir / "alert_genuine.xml"

    logger.info(f"Alert file: {alert_path}")

    if not alert_path.exists():
        logger.error(f"Alert file not found: {alert_path}")
        return 1

    try:
        # Create LLM
        logger.info("Initializing LLM")
        llm = create_llm(config)

        # Create agent
        logger.info("Creating analysis agent")
        agent = AlertAnalyzerAgent(
            llm=llm,
            data_dir=config.data.data_dir,
            output_dir=config.data.output_dir,
        )

        # Run analysis
        logger.info("Starting alert analysis")
        decision = agent.analyze(alert_path)

        # Output results
        logger.info("=" * 60)
        logger.info("ANALYSIS COMPLETE")
        logger.info("=" * 60)

        print("\n" + "=" * 60)
        print("ALERT ANALYSIS RESULT")
        print("=" * 60)
        print(f"\nAlert ID: {decision.alert_id}")
        print(f"Determination: {decision.determination}")
        print(f"Genuine Confidence: {decision.genuine_alert_confidence}%")
        print(f"False Positive Confidence: {decision.false_positive_confidence}%")
        print(f"\nRecommended Action: {decision.recommended_action}")
        print(f"Similar Precedent: {decision.similar_precedent}")

        print("\n--- Key Findings ---")
        for i, finding in enumerate(decision.key_findings, 1):
            print(f"{i}. {finding}")

        print("\n--- Favorable Indicators (suggesting genuine) ---")
        for indicator in decision.favorable_indicators:
            print(f"  - {indicator}")

        print("\n--- Risk Mitigating Factors (suggesting false positive) ---")
        for factor in decision.risk_mitigating_factors:
            print(f"  - {factor}")

        print("\n--- Reasoning ---")
        print(decision.reasoning_narrative)

        if decision.data_gaps:
            print("\n--- Data Gaps ---")
            for gap in decision.data_gaps:
                print(f"  - {gap}")

        # Print output file location
        output_file = config.data.output_dir / f"decision_{decision.alert_id}.json"
        print(f"\nFull report written to: {output_file}")

        # Print tool stats
        stats = agent.get_tool_stats()
        logger.info("Tool usage statistics:")
        for tool_stat in stats["tools"]:
            logger.info(
                f"  {tool_stat['name']}: {tool_stat['call_count']} calls, "
                f"{tool_stat['total_time_seconds']}s total"
            )

        return 0

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        return 1

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
