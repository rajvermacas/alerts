"""Configuration management for the SMARTS Alert Analyzer.

This module provides environment-based configuration supporting both
OpenAI and Azure OpenAI providers. Configuration is loaded from
environment variables with fail-fast behavior on missing required values.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing required values."""

    pass


@dataclass
class LLMConfig:
    """LLM provider configuration.

    Attributes:
        provider: LLM provider type ("openai" or "azure")
        model: Model name/deployment name
        temperature: Sampling temperature (0.0 for deterministic)
        max_tokens: Maximum tokens in response
        api_key: API key for the provider
        azure_endpoint: Azure OpenAI endpoint (required for Azure)
        azure_api_version: Azure API version (required for Azure)
    """

    provider: Literal["openai", "azure"] = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.0
    max_tokens: int = 4000
    api_key: Optional[str] = None
    azure_endpoint: Optional[str] = None
    azure_api_version: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        logger.debug(f"LLMConfig initialized: provider={self.provider}, model={self.model}")

        if not self.api_key:
            raise ConfigurationError(
                f"API key required for provider '{self.provider}'. "
                f"Set OPENAI_API_KEY or AZURE_OPENAI_API_KEY environment variable."
            )

        if self.provider == "azure":
            if not self.azure_endpoint:
                raise ConfigurationError(
                    "Azure endpoint required. Set AZURE_OPENAI_ENDPOINT environment variable."
                )
            if not self.azure_api_version:
                raise ConfigurationError(
                    "Azure API version required. Set AZURE_OPENAI_API_VERSION environment variable."
                )
            logger.info(f"Azure OpenAI configured: endpoint={self.azure_endpoint}")
        else:
            logger.info(f"OpenAI configured: model={self.model}")

    def is_azure(self) -> bool:
        """Check if using Azure OpenAI provider.

        Returns:
            True if provider is Azure, False otherwise
        """
        return self.provider == "azure"


@dataclass
class DataConfig:
    """Data paths configuration.

    Attributes:
        data_dir: Directory containing test data files
        output_dir: Directory for output reports
        alert_file_path: Path to the alert XML file to analyze
    """

    data_dir: Path = field(default_factory=lambda: Path("test_data"))
    output_dir: Path = field(default_factory=lambda: Path("resources/reports"))
    alert_file_path: Optional[Path] = None

    def __post_init__(self) -> None:
        """Validate paths after initialization."""
        logger.debug(f"DataConfig initialized: data_dir={self.data_dir}, output_dir={self.output_dir}")

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Data directory: {self.data_dir.absolute()}")
        logger.info(f"Output directory: {self.output_dir.absolute()}")

    @property
    def trader_history_path(self) -> Path:
        """Path to trader history CSV file."""
        return self.data_dir / "trader_history.csv"

    @property
    def trader_profiles_path(self) -> Path:
        """Path to trader profiles CSV file."""
        return self.data_dir / "trader_profiles.csv"

    @property
    def market_news_path(self) -> Path:
        """Path to market news text file."""
        return self.data_dir / "market_news.txt"

    @property
    def market_data_path(self) -> Path:
        """Path to market data CSV file."""
        return self.data_dir / "market_data.csv"

    @property
    def peer_trades_path(self) -> Path:
        """Path to peer trades CSV file."""
        return self.data_dir / "peer_trades.csv"

    @property
    def few_shot_examples_path(self) -> Path:
        """Path to few-shot examples JSON file."""
        return self.data_dir / "few_shot_examples.json"

    @property
    def alerts_dir(self) -> Path:
        """Path to alerts directory."""
        return self.data_dir / "alerts"


@dataclass
class LoggingConfig:
    """Logging configuration.

    Attributes:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Log message format
        log_file: Optional log file path
    """

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_file: Optional[Path] = None

    def __post_init__(self) -> None:
        """Validate logging configuration."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.level.upper() not in valid_levels:
            raise ConfigurationError(
                f"Invalid log level '{self.level}'. Must be one of: {valid_levels}"
            )
        self.level = self.level.upper()
        logger.debug(f"LoggingConfig initialized: level={self.level}")


@dataclass
class AppConfig:
    """Complete application configuration.

    Attributes:
        llm: LLM provider configuration
        data: Data paths configuration
        logging: Logging configuration
    """

    llm: LLMConfig
    data: DataConfig
    logging: LoggingConfig

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load configuration from environment variables.

        Returns:
            AppConfig instance populated from environment

        Raises:
            ConfigurationError: If required configuration is missing
        """
        logger.info("Loading configuration from environment variables")

        # Determine provider
        provider = os.getenv("LLM_PROVIDER", "openai").lower()
        if provider not in ("openai", "azure"):
            raise ConfigurationError(
                f"Invalid LLM_PROVIDER '{provider}'. Must be 'openai' or 'azure'."
            )

        # Get API key based on provider
        if provider == "azure":
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            model = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            model = os.getenv("OPENAI_MODEL", "gpt-4o")

        # Build LLM config
        llm_config = LLMConfig(
            provider=provider,
            model=model,
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4000")),
            api_key=api_key,
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azure_api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        )

        # Build data config
        alert_file = os.getenv("ALERT_FILE_PATH")
        data_config = DataConfig(
            data_dir=Path(os.getenv("DATA_DIR", "test_data")),
            output_dir=Path(os.getenv("OUTPUT_DIR", "resources/reports")),
            alert_file_path=Path(alert_file) if alert_file else None,
        )

        # Build logging config
        logging_config = LoggingConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
        )

        config = cls(
            llm=llm_config,
            data=data_config,
            logging=logging_config,
        )

        logger.info("Configuration loaded successfully")
        return config


def setup_logging(config: LoggingConfig) -> None:
    """Configure logging for the application.

    Args:
        config: Logging configuration
    """
    handlers = [logging.StreamHandler()]

    if config.log_file:
        handlers.append(logging.FileHandler(config.log_file))

    logging.basicConfig(
        level=getattr(logging, config.level),
        format=config.format,
        handlers=handlers,
        force=True,
    )

    # Suppress verbose third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

    logger.info(f"Logging configured: level={config.level}")


def get_config() -> AppConfig:
    """Get application configuration.

    This is the main entry point for configuration access.
    Loads configuration from environment variables.

    Returns:
        AppConfig instance

    Raises:
        ConfigurationError: If configuration is invalid
    """
    return AppConfig.from_env()
