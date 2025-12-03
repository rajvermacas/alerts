"""Tests for LLM factory module."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from alerts.config import AppConfig, LLMConfig
from alerts.llm_factory import create_llm


class TestCreateLLM:
    """Tests for create_llm factory function."""

    def _create_mock_config(self, **llm_kwargs) -> MagicMock:
        """Create a mock AppConfig with specified LLM settings."""
        config = MagicMock(spec=AppConfig)
        config.llm = LLMConfig(**llm_kwargs)
        return config

    def test_create_openai_llm(self):
        """Test creating OpenAI LLM instance."""
        config = self._create_mock_config(
            provider="openai",
            model="gpt-4o",
            api_key="test-openai-key",
            temperature=0.0,
            max_tokens=4000
        )

        llm = create_llm(config)

        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == "gpt-4o"
        assert llm.temperature == 0.0
        assert llm.max_tokens == 4000

    def test_create_azure_llm(self):
        """Test creating Azure OpenAI LLM instance."""
        config = self._create_mock_config(
            provider="azure",
            model="gpt-4o-deployment",
            api_key="test-azure-key",
            azure_endpoint="https://test.openai.azure.com/",
            azure_api_version="2024-02-15-preview",
            temperature=0.0,
            max_tokens=4000
        )

        llm = create_llm(config)

        assert isinstance(llm, AzureChatOpenAI)
        assert llm.deployment_name == "gpt-4o-deployment"

    def test_create_openrouter_llm(self):
        """Test creating OpenRouter LLM instance (uses ChatOpenAI with custom base_url)."""
        config = self._create_mock_config(
            provider="openrouter",
            model="anthropic/claude-instant-v1",
            api_key="test-openrouter-key",
            temperature=0.5,
            max_tokens=2000
        )

        llm = create_llm(config)

        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == "anthropic/claude-instant-v1"
        assert llm.openai_api_base == "https://openrouter.ai/api/v1"

    def test_create_openrouter_llm_with_headers(self):
        """Test OpenRouter LLM with site tracking headers."""
        config = self._create_mock_config(
            provider="openrouter",
            model="openai/gpt-4o",
            api_key="test-openrouter-key",
            openrouter_site_url="https://example.com",
            openrouter_site_name="My App",
            temperature=0.0,
            max_tokens=4000
        )

        llm = create_llm(config)

        assert isinstance(llm, ChatOpenAI)
        # Headers are set in default_headers
        assert llm.default_headers is not None
        assert llm.default_headers.get("HTTP-Referer") == "https://example.com"
        assert llm.default_headers.get("X-Title") == "My App"

    def test_create_gemini_llm(self):
        """Test creating Google Gemini LLM instance."""
        config = self._create_mock_config(
            provider="gemini",
            model="gemini-2.0-flash",
            api_key="test-gemini-key",
            temperature=0.0,
            max_tokens=4000
        )

        llm = create_llm(config)

        assert isinstance(llm, ChatGoogleGenerativeAI)
        # ChatGoogleGenerativeAI prefixes model name with "models/"
        assert "gemini-2.0-flash" in llm.model
        assert llm.temperature == 0.0
        assert llm.max_output_tokens == 4000

    def test_create_gemini_llm_different_models(self):
        """Test creating Gemini LLM with different model names."""
        test_models = [
            "gemini-2.0-flash",
            "gemini-2.0-flash-exp",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ]

        for model in test_models:
            config = self._create_mock_config(
                provider="gemini",
                model=model,
                api_key="test-gemini-key",
                temperature=0.0,
                max_tokens=4000
            )

            llm = create_llm(config)

            assert isinstance(llm, ChatGoogleGenerativeAI)
            # ChatGoogleGenerativeAI prefixes model name with "models/"
            assert model in llm.model

    def test_create_gemini_llm_with_temperature(self):
        """Test Gemini LLM preserves temperature setting."""
        config = self._create_mock_config(
            provider="gemini",
            model="gemini-2.0-flash",
            api_key="test-gemini-key",
            temperature=0.7,
            max_tokens=2000
        )

        llm = create_llm(config)

        assert isinstance(llm, ChatGoogleGenerativeAI)
        assert llm.temperature == 0.7
        assert llm.max_output_tokens == 2000

    def test_unknown_provider_raises_error(self):
        """Test that unknown provider raises ValueError."""
        # Create a config with an invalid provider by bypassing validation
        config = MagicMock(spec=AppConfig)
        llm_config = MagicMock()
        llm_config.provider = "unknown_provider"
        llm_config.is_azure.return_value = False
        llm_config.is_gemini.return_value = False
        config.llm = llm_config

        with pytest.raises(ValueError) as exc_info:
            create_llm(config)

        assert "Unknown LLM provider" in str(exc_info.value)
        assert "unknown_provider" in str(exc_info.value)
