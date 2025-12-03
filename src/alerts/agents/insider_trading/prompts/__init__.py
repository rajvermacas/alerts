"""Insider trading prompts package."""

from alerts.agents.insider_trading.prompts.system_prompt import (
    get_system_prompt,
    get_final_decision_prompt,
    load_few_shot_examples,
)

__all__ = [
    "get_system_prompt",
    "get_final_decision_prompt",
    "load_few_shot_examples",
]
