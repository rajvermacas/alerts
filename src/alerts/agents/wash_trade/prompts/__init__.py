"""Wash trade prompts package."""

from alerts.agents.wash_trade.prompts.system_prompt import (
    get_wash_trade_system_prompt,
    get_wash_trade_final_decision_prompt,
    load_wash_trade_few_shot_examples,
)

__all__ = [
    "get_wash_trade_system_prompt",
    "get_wash_trade_final_decision_prompt",
    "load_wash_trade_few_shot_examples",
]
