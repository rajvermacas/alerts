"""LLM factory for creating provider-specific LLM instances.

This module provides a centralized factory function for creating LangChain LLM
instances based on the application configuration. Supports OpenAI, Azure OpenAI,
OpenRouter, and Google Gemini providers.
"""

import logging
from typing import Any, Union

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from alerts.config import AppConfig

logger = logging.getLogger(__name__)


def create_llm(
    config: AppConfig,
) -> Union[ChatOpenAI, AzureChatOpenAI, ChatGoogleGenerativeAI]:
    """Create LLM instance based on configuration.

    Factory function that creates the appropriate LangChain LLM instance
    based on the provider specified in the configuration.

    Args:
        config: AppConfig instance containing LLM configuration

    Returns:
        LangChain LLM instance appropriate for the configured provider:
        - ChatOpenAI for OpenAI provider
        - AzureChatOpenAI for Azure provider
        - ChatOpenAI with custom base_url for OpenRouter provider
        - ChatGoogleGenerativeAI for Gemini provider

    Raises:
        ValueError: If an unknown provider is specified
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
    elif config.llm.is_gemini():
        logger.info(f"Using Google Gemini: {config.llm.model}")
        return ChatGoogleGenerativeAI(
            model=config.llm.model,
            google_api_key=config.llm.api_key,
            temperature=config.llm.temperature,
            max_output_tokens=config.llm.max_tokens,
        )
    elif config.llm.provider == "openrouter":
        logger.info(f"Using OpenRouter: {config.llm.model}")

        # Build optional headers for site tracking
        default_headers: dict[str, Any] = {}
        if config.llm.openrouter_site_url:
            default_headers["HTTP-Referer"] = config.llm.openrouter_site_url
            logger.debug(
                f"OpenRouter HTTP-Referer header set: {config.llm.openrouter_site_url}"
            )
        if config.llm.openrouter_site_name:
            default_headers["X-Title"] = config.llm.openrouter_site_name
            logger.debug(
                f"OpenRouter X-Title header set: {config.llm.openrouter_site_name}"
            )

        return ChatOpenAI(
            model=config.llm.model,
            api_key=config.llm.api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers=default_headers if default_headers else None,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
    elif config.llm.provider == "openai":
        logger.info(f"Using OpenAI: {config.llm.model}")
        return ChatOpenAI(
            model=config.llm.model,
            api_key=config.llm.api_key,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: {config.llm.provider}. "
            f"Supported providers: openai, azure, openrouter, gemini"
        )
