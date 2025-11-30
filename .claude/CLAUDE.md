# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SMARTS Alert False Positive Analyzer - An intelligent compliance filter that analyzes SMARTS surveillance alerts for potential insider trading. Uses a fully agentic LLM-based approach with LangGraph, where each tool calls an LLM internally to interpret data rather than returning raw data.

**Core Philosophy**: Fully agentic reasoning without hardcoded scoring weights. Adaptability through few-shot examples stored in external JSON files (not code changes).

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Install development dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your API keys (NEVER commit .env)
```

### Running the Application
```bash
# Analyze the default alert (genuine insider trading case)
python -m alerts.main

# Analyze a specific alert file
python -m alerts.main --alert test_data/alerts/alert_genuine.xml
python -m alerts.main --alert test_data/alerts/alert_false_positive.xml
python -m alerts.main --alert test_data/alerts/alert_ambiguous.xml

# Run with verbose logging
python -m alerts.main --verbose

# Run with minimal output
python -m alerts.main --quiet

# Using installed script entry point
alerts
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=alerts

# Run specific test file
pytest tests/test_tools.py -v

# Run with verbose output and short traceback
pytest -v --tb=short
```

## Architecture

### High-Level Design Pattern

**Single LangGraph Agent** with 6 specialized tools. Each tool:
1. Reads from a data source (CSV/XML/TXT files in POC)
2. **Calls LLM internally** to interpret raw data
3. Returns **insights** (not raw data) to the main agent

This creates a **two-tier LLM architecture**:
- **Tier 1**: Tool-level LLMs extract insights from raw data
- **Tier 2**: Main agent LLM makes final determination using tool insights + few-shot examples

### Core Components

```
src/alerts/
├── main.py              # CLI entry point, LLM initialization
├── config.py            # Environment-based configuration (OpenAI/Azure)
├── agent.py             # LangGraph agent orchestration
├── models.py            # Pydantic models for structured output
├── tools/
│   ├── base.py          # BaseTool class with LLM interpretation
│   ├── alert_reader.py
│   ├── trader_history.py
│   ├── trader_profile.py
│   ├── market_news.py
│   ├── market_data.py
│   └── peer_trades.py
└── prompts/
    └── system_prompt.py # Agent system prompt + few-shot loader
```

### LangGraph Workflow

```
START → agent → tools? → [tools → agent]* → respond → END
        ↑                                      ↓
        └──────── loops until no tool calls ───┘
```

**Nodes**:
- `agent`: Main reasoning node (decides which tools to call)
- `tools`: ToolNode executing requested tools
- `respond`: Final structured output generation using `AlertDecision` Pydantic model

**Key Implementation Details**:
- `MessagesState` for conversation history
- `recursion_limit=50` to allow multiple tool calls
- Tools bound to LLM via `llm.bind_tools()`
- Final response uses `llm.with_structured_output(AlertDecision)`

### Tool Implementation Pattern

All tools inherit from `BaseTool` and implement:

```python
class SomeTool(BaseTool):
    def _load_data(self, **kwargs) -> str:
        # Read from data source (CSV, XML, etc.)
        pass

    def _build_interpretation_prompt(self, raw_data: str, **kwargs) -> str:
        # Build LLM prompt for interpretation
        pass

    def __call__(self, **kwargs) -> str:
        # BaseTool handles: load → interpret with LLM → return insights
        pass
```

**Critical**: Tools return LLM-interpreted insights, NOT raw data. Example:
```
Bad:  "trader_history.csv has 247 rows..."
Good: "This trader typically trades 5K shares/day in tech sector.
       The flagged 50K share healthcare trade is 10x normal volume
       and a sector they've never touched."
```

### Few-Shot Examples Strategy

Location: `test_data/few_shot_examples.json`

The agent uses a **"case law" approach** - few-shot examples serve as precedents. To tune behavior:
1. Edit `few_shot_examples.json` (NO code changes needed)
2. Add new example scenarios with detailed reasoning
3. Agent compares current case to precedents

Loaded via `prompts/system_prompt.py:load_few_shot_examples()` and injected into system prompt.

### Configuration Management

**Environment-based** configuration supporting both OpenAI and Azure OpenAI:

```python
# config.py uses dataclasses with fail-fast validation
AppConfig
├── LLMConfig       # Provider, model, API keys, temperature
├── DataConfig      # Paths to data_dir, output_dir, alerts
└── LoggingConfig   # Log level, format, optional file
```

Load with: `get_config()` (reads from `.env` file via `python-dotenv`)

**Provider switching**: Set `LLM_PROVIDER=openai` or `LLM_PROVIDER=azure` in `.env`

### Output Schema

**Primary Model**: `AlertDecision` (Pydantic)

Key fields:
- `determination`: "ESCALATE" | "CLOSE" | "NEEDS_HUMAN_REVIEW"
- `genuine_alert_confidence`: 0-100
- `false_positive_confidence`: 0-100
- `key_findings`: List[str]
- `favorable_indicators`: Reasons suggesting genuine insider trading
- `risk_mitigating_factors`: Reasons suggesting false positive
- `trader_baseline_analysis`: TraderBaselineAnalysis nested model
- `market_context`: MarketContext nested model
- `reasoning_narrative`: 2-4 paragraph explanation
- `similar_precedent`: Which few-shot example this resembles

**Output Files**:
- `resources/reports/decision_{alert_id}.json` - Full decision
- `resources/reports/audit_log.jsonl` - Append-only audit trail

## Important Constraints

### Error Handling Philosophy
**Fail-fast**: No graceful degradation. Errors crash loudly for debugging. If a tool fails, the entire analysis fails.

Rationale: In POC phase, we want immediate feedback on issues rather than silent failures.

### Data Access in POC
All data sources are **local files** in `test_data/`:
- `alerts/*.xml` - SMARTS alert files
- `trader_history.csv` - Historical trades
- `trader_profiles.csv` - Trader roles/access levels
- `market_news.txt` - News timeline (free-form text)
- `market_data.csv` - Price/volume data
- `peer_trades.csv` - Peer trading activity
- `few_shot_examples.json` - Few-shot precedents

### LLM Provider Support
Code is **provider-agnostic**. Switch between OpenAI and Azure via configuration:
- OpenAI: `OPENAI_API_KEY` + `OPENAI_MODEL`
- Azure: `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT`

Implementation: `main.py:create_llm()` uses LangChain's `ChatOpenAI` or `AzureChatOpenAI`

### No Hardcoded Scoring
The system uses **pure LLM reasoning** - no weight-based scoring formulas. To adjust behavior:
1. Modify few-shot examples in `test_data/few_shot_examples.json`
2. Update system prompt in `prompts/system_prompt.py`

**Do NOT add** scoring weights, thresholds, or rule-based logic.

## Development Patterns

### Adding a New Tool
1. Create tool class in `src/alerts/tools/your_tool.py`
2. Inherit from `BaseTool`
3. Implement `_load_data()` and `_build_interpretation_prompt()`
4. Add to `agent.py:_create_tool_instances()`
5. Update tests in `tests/test_tools.py`

### Modifying Agent Behavior
1. **First choice**: Edit `test_data/few_shot_examples.json` (no code changes)
2. **If insufficient**: Update system prompt in `prompts/system_prompt.py`
3. **Last resort**: Modify agent graph in `agent.py:_build_graph()`

### Testing Strategy
- Unit tests for tools, models, config
- Mock LLM responses for deterministic tests
- Use `conftest.py` for shared fixtures
- Test data generation scripts go in `scripts/` folder

### Logging
Extensive logging at INFO level by default:
- Tool calls and processing times
- Agent reasoning steps
- Decision generation
- Output file writes

Third-party loggers (httpx, openai) suppressed to WARNING level.

## Key Files Reference

| File | Purpose | When to Modify |
|------|---------|----------------|
| `test_data/few_shot_examples.json` | Behavior tuning | Adjust agent decision patterns |
| `prompts/system_prompt.py` | Agent instructions | Change reasoning approach |
| `agent.py` | Graph definition | Add nodes, change workflow |
| `models.py` | Output schema | Change decision structure |
| `tools/base.py` | Tool infrastructure | Common tool functionality |
| `config.py` | Environment config | Add config parameters |
| `main.py` | Entry point | CLI arguments, output formatting |

## Anti-Patterns to Avoid

1. **Don't return raw data from tools** - Always use LLM to interpret first
2. **Don't add hardcoded scoring** - Use few-shot examples instead
3. **Don't silently catch errors** - Let them crash (fail-fast)
4. **Don't create new data sources** without updating architecture docs
5. **Don't modify `.env`** - It contains secrets and is gitignored
6. **Don't create files in project root** - Use `scripts/`, `test_data/`, or `resources/` subdirectories

## Reference Documentation

- LangGraph docs: `resources/research/langgraph/` (comprehensive reference materials)
- Architecture design: `.dev-resources/architecture/smarts-alert-analyzer.md`
- Architecture prompts: `.dev-resources/prompts/architecture.txt`
