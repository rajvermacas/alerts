"""Tests for SMARTS Alert Analyzer main module."""

import pytest
from unittest.mock import MagicMock, patch

from alerts.config import AppConfig, LLMConfig
from alerts.main import create_llm


class TestCreateLLM:
    """Tests for create_llm function."""

    def test_create_openai_llm(self):
        """Test creating OpenAI LLM instance."""
        config = MagicMock(spec=AppConfig)
        config.llm = LLMConfig(
            provider="openai",
            model="gpt-4o",
            api_key="test-openai-key",
            temperature=0.0,
            max_tokens=4000
        )

        llm = create_llm(config)

        assert llm is not None
        assert llm.model_name == "gpt-4o"

    def test_create_azure_llm(self):
        """Test creating Azure OpenAI LLM instance."""
        config = MagicMock(spec=AppConfig)
        config.llm = LLMConfig(
            provider="azure",
            model="gpt-4o",
            api_key="test-azure-key",
            azure_endpoint="https://test.openai.azure.com/",
            azure_api_version="2024-02-15-preview",
            temperature=0.0,
            max_tokens=4000
        )

        llm = create_llm(config)

        assert llm is not None
        # Azure uses deployment name instead of model name
        assert llm.deployment_name == "gpt-4o"

    def test_create_openrouter_llm(self):
        """Test creating OpenRouter LLM instance."""
        config = MagicMock(spec=AppConfig)
        config.llm = LLMConfig(
            provider="openrouter",
            model="openai/gpt-4o",
            api_key="test-openrouter-key",
            temperature=0.0,
            max_tokens=4000,
            openrouter_site_url=None,
            openrouter_site_name=None
        )

        llm = create_llm(config)

        assert llm is not None
        assert llm.model_name == "openai/gpt-4o"
        # Verify base URL is set for OpenRouter
        assert llm.openai_api_base == "https://openrouter.ai/api/v1"

    def test_create_openrouter_llm_with_site_tracking(self):
        """Test creating OpenRouter LLM with site tracking headers."""
        config = MagicMock(spec=AppConfig)
        config.llm = LLMConfig(
            provider="openrouter",
            model="anthropic/claude-instant-v1",
            api_key="test-openrouter-key",
            temperature=0.0,
            max_tokens=4000,
            openrouter_site_url="https://example.com",
            openrouter_site_name="My Alert App"
        )

        llm = create_llm(config)

        assert llm is not None
        assert llm.model_name == "anthropic/claude-instant-v1"
        assert llm.openai_api_base == "https://openrouter.ai/api/v1"
        # Verify headers are set
        assert llm.default_headers is not None
        assert llm.default_headers.get("HTTP-Referer") == "https://example.com"
        assert llm.default_headers.get("X-Title") == "My Alert App"

    def test_create_openrouter_llm_without_site_tracking(self):
        """Test creating OpenRouter LLM without optional site tracking."""
        config = MagicMock(spec=AppConfig)
        config.llm = LLMConfig(
            provider="openrouter",
            model="openai/gpt-4o",
            api_key="test-openrouter-key",
            temperature=0.0,
            max_tokens=4000
        )

        llm = create_llm(config)

        assert llm is not None
        # Headers should be None if not provided
        assert llm.default_headers is None

    def test_create_llm_preserves_temperature(self):
        """Test that temperature is preserved in created LLM."""
        config = MagicMock(spec=AppConfig)
        config.llm = LLMConfig(
            provider="openai",
            model="gpt-4o",
            api_key="test-key",
            temperature=0.7,
            max_tokens=2000
        )

        llm = create_llm(config)

        assert llm.temperature == 0.7
        assert llm.max_tokens == 2000

    def test_create_llm_with_different_models(self):
        """Test creating LLM with different model names."""
        test_cases = [
            ("openai", "gpt-4o-mini", "test-openai-key"),
            ("openrouter", "openai/gpt-4-turbo", "test-openrouter-key"),
            ("openrouter", "meta-llama/llama-3-8b", "test-openrouter-key"),
            ("openrouter", "anthropic/claude-opus", "test-openrouter-key"),
        ]

        for provider, model, api_key in test_cases:
            config = MagicMock(spec=AppConfig)
            if provider == "azure":
                config.llm = LLMConfig(
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    azure_endpoint="https://test.openai.azure.com/",
                    azure_api_version="2024-02-15-preview"
                )
            else:
                config.llm = LLMConfig(
                    provider=provider,
                    model=model,
                    api_key=api_key
                )

            llm = create_llm(config)
            assert llm is not None

            if provider == "azure":
                assert llm.deployment_name == model
            elif provider == "openrouter":
                assert llm.model_name == model
                assert llm.openai_api_base == "https://openrouter.ai/api/v1"
            else:
                assert llm.model_name == model
