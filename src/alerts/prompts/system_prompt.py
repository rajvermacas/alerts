"""System prompts for the SMARTS Alert Analyzer agent.

This module re-exports prompts from the insider trading agent for
backward compatibility. New code should import from specific agent packages.

Prompt structure:
- alerts.agents.insider_trading.prompts: Insider trading prompts
- alerts.agents.wash_trade.prompts: Wash trade prompts (coming soon)
"""

# Re-export from new location for backward compatibility
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
