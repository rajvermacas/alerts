"""Tests for SMARTS Alert Analyzer configuration."""

import os
import pytest
from pathlib import Path

from alerts.config import (
    AppConfig,
    ConfigurationError,
    DataConfig,
    LLMConfig,
    LoggingConfig,
    get_config,
    setup_logging,
)


class TestLLMConfig:
    """Tests for LLMConfig."""

    def test_openai_config(self):
        """Test OpenAI configuration."""
        config = LLMConfig(
            provider="openai",
            model="gpt-4o",
            api_key="test-key"
        )

        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert not config.is_azure()

    def test_azure_config(self):
        """Test Azure OpenAI configuration."""
        config = LLMConfig(
            provider="azure",
            model="gpt-4o",
            api_key="test-key",
            azure_endpoint="https://test.openai.azure.com/",
            azure_api_version="2024-02-15-preview"
        )

        assert config.provider == "azure"
        assert config.is_azure()

    def test_missing_api_key_raises(self):
        """Test that missing API key raises error."""
        with pytest.raises(ConfigurationError):
            LLMConfig(provider="openai", api_key=None)

    def test_azure_missing_endpoint_raises(self):
        """Test that Azure without endpoint raises error."""
        with pytest.raises(ConfigurationError):
            LLMConfig(
                provider="azure",
                api_key="test-key",
                azure_endpoint=None,
                azure_api_version="2024-02-15"
            )

    def test_azure_missing_version_raises(self):
        """Test that Azure without API version raises error."""
        with pytest.raises(ConfigurationError):
            LLMConfig(
                provider="azure",
                api_key="test-key",
                azure_endpoint="https://test.openai.azure.com/",
                azure_api_version=None
            )

    def test_openrouter_config(self):
        """Test OpenRouter configuration."""
        config = LLMConfig(
            provider="openrouter",
            model="openai/gpt-4o",
            api_key="test-openrouter-key"
        )

        assert config.provider == "openrouter"
        assert config.model == "openai/gpt-4o"
        assert not config.is_azure()

    def test_openrouter_config_with_site_tracking(self):
        """Test OpenRouter configuration with site tracking headers."""
        config = LLMConfig(
            provider="openrouter",
            model="anthropic/claude-instant-v1",
            api_key="test-openrouter-key",
            openrouter_site_url="https://example.com",
            openrouter_site_name="My App"
        )

        assert config.provider == "openrouter"
        assert config.openrouter_site_url == "https://example.com"
        assert config.openrouter_site_name == "My App"

    def test_openrouter_missing_api_key_raises(self):
        """Test that OpenRouter without API key raises error."""
        with pytest.raises(ConfigurationError):
            LLMConfig(
                provider="openrouter",
                model="openai/gpt-4o",
                api_key=None
            )


class TestDataConfig:
    """Tests for DataConfig."""

    def test_default_paths(self, tmp_path: Path):
        """Test default path configuration."""
        config = DataConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output"
        )

        assert config.data_dir.exists()
        assert config.output_dir.exists()

    def test_path_properties(self, tmp_path: Path):
        """Test path property methods."""
        config = DataConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output"
        )

        assert config.trader_history_path == tmp_path / "data" / "trader_history.csv"
        assert config.trader_profiles_path == tmp_path / "data" / "trader_profiles.csv"
        assert config.market_news_path == tmp_path / "data" / "market_news.txt"
        assert config.market_data_path == tmp_path / "data" / "market_data.csv"
        assert config.peer_trades_path == tmp_path / "data" / "peer_trades.csv"
        assert config.few_shot_examples_path == tmp_path / "data" / "few_shot_examples.json"
        assert config.alerts_dir == tmp_path / "data" / "alerts"


class TestLoggingConfig:
    """Tests for LoggingConfig."""

    def test_valid_levels(self):
        """Test valid log levels."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            config = LoggingConfig(level=level)
            assert config.level == level.upper()

    def test_case_insensitive(self):
        """Test log level is case insensitive."""
        config = LoggingConfig(level="info")
        assert config.level == "INFO"

    def test_invalid_level_raises(self):
        """Test invalid log level raises error."""
        with pytest.raises(ConfigurationError):
            LoggingConfig(level="INVALID")


class TestAppConfig:
    """Tests for AppConfig."""

    def test_from_env_openai(self, monkeypatch):
        """Test loading OpenAI config from environment."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        config = AppConfig.from_env()

        assert config.llm.provider == "openai"
        assert config.llm.api_key == "test-openai-key"
        assert config.llm.model == "gpt-4o-mini"
        assert config.logging.level == "DEBUG"

    def test_from_env_azure(self, monkeypatch):
        """Test loading Azure config from environment."""
        monkeypatch.setenv("LLM_PROVIDER", "azure")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-azure-key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com/")
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "my-deployment")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

        config = AppConfig.from_env()

        assert config.llm.provider == "azure"
        assert config.llm.api_key == "test-azure-key"
        assert config.llm.is_azure()

    def test_from_env_openrouter(self, monkeypatch):
        """Test loading OpenRouter config from environment."""
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
        monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-instant-v1")
        monkeypatch.setenv("OPENROUTER_SITE_URL", "https://example.com")
        monkeypatch.setenv("OPENROUTER_SITE_NAME", "My Alert App")

        config = AppConfig.from_env()

        assert config.llm.provider == "openrouter"
        assert config.llm.api_key == "test-openrouter-key"
        assert config.llm.model == "anthropic/claude-instant-v1"
        assert config.llm.openrouter_site_url == "https://example.com"
        assert config.llm.openrouter_site_name == "My Alert App"

    def test_from_env_openrouter_without_site_tracking(self, monkeypatch):
        """Test OpenRouter config without optional site tracking."""
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
        monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o")

        config = AppConfig.from_env()

        assert config.llm.provider == "openrouter"
        assert config.llm.openrouter_site_url is None
        assert config.llm.openrouter_site_name is None

    def test_from_env_invalid_provider(self, monkeypatch):
        """Test invalid provider raises error."""
        monkeypatch.setenv("LLM_PROVIDER", "invalid")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        with pytest.raises(ConfigurationError):
            AppConfig.from_env()


class TestGetConfig:
    """Tests for get_config function."""

    def test_get_config(self, monkeypatch):
        """Test get_config returns AppConfig."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        config = get_config()

        assert isinstance(config, AppConfig)


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging(self):
        """Test logging setup."""
        config = LoggingConfig(level="INFO")
        setup_logging(config)

        # If we get here without error, logging was configured
        import logging
        logger = logging.getLogger("test")
        assert logger.level == 0  # Inherits from root
