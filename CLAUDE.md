# SMARTS Alert Analyzer - Developer Reference

**Mission**: Intelligent compliance filter using multi-agent LLM architecture to analyze SMARTS surveillance alerts (insider trading, wash trading) and reduce false positives.

**Core Philosophy**: Fully agentic reasoning without hardcoded scoring. Behavior tuning via few-shot examples in JSON files (zero code changes).

---

## Quick Navigation

| Section | Purpose |
|---------|---------|
| [Commands](#commands) | Setup, run, test, deploy |
| [Architecture](#architecture) | System design, data flow |
| [Directory Index](#directory-index) | File locations by purpose |
| [Integration Points](#integration-points) | A2A servers, frontend, tools |
| [Development Patterns](#development-patterns) | Add features, tune behavior |
| [Key Constraints](#key-constraints) | Fail-fast, no hardcoded scoring |

---

## Commands

### Setup
```bash
# Install
pip install -e .                    # Production
pip install -e ".[dev]"             # Development + testing

# Configure (NEVER commit .env)
cp .env.example .env
# Edit: LLM_PROVIDER (openai/azure/openrouter/gemini), API keys
```

### Run Analysis

**CLI (single alert)**:
```bash
python -m alerts.main                                      # Default IT alert
python -m alerts.main --alert test_data/alerts/wash_trade/wash_genuine.xml
python -m alerts.main --verbose
```

**Multi-Agent (A2A servers + web UI)**:
```bash
# Quick start - all servers in background
bash scripts/start_all_servers.sh
# Open: http://localhost:8080
# Logs: logs/{insider_trading,wash_trade,orchestrator,frontend}.log

# Manual (4 terminals)
python -m alerts.a2a.insider_trading_server --port 10001
python -m alerts.a2a.wash_trade_server --port 10002
python -m alerts.a2a.orchestrator_server --port 10000
python -m frontend.app --port 8080
```

### Testing
```bash
pytest                              # All tests
pytest --cov=alerts                 # With coverage
pytest tests/test_tools.py -v      # Specific file
pytest -k "wash_trade" -v          # Keyword match
```

---

## Architecture

### Multi-Agent Flow
```
User/Browser
    ↓ (XML alert)
Orchestrator (Port 10000) ← detects alert type
    ↓
    ├→ Insider Trading Agent (10001) → 5 tools (3 common + 2 IT-specific)
    └→ Wash Trade Agent (10002) → 7 tools (3 common + 4 WT-specific)
    ↓
Decision (JSON + HTML)
```

**Alert Detection**:
- IT: Keywords `insider|pre-announcement|mnpi`, rule codes `SMARTS-IT-*|SMARTS-PAT-*`
- WT: Keywords `wash|self-trade|circular`, rule codes `SMARTS-WT-*|WT-*|WASH_TRADE`

### Tool Architecture (Two-Tier LLM)

Each tool = Data Source → **LLM Interpretation** → Insights (not raw data)

**Common Tools** (all agents):
1. `alert_reader` - Parse XML → alert summary
2. `trader_profile` - CSV → MNPI access assessment
3. `market_data` - CSV → market conditions analysis

**IT-Specific Tools**:
4. `trader_history` - CSV → baseline deviation
5. `market_news` - TXT → public info timeline

**WT-Specific Tools**:
4. `account_relationships` - CSV → ownership network
5. `related_accounts_history` - CSV → coordinated activity
6. `trade_timing` - CSV → sub-second patterns
7. `counterparty_analysis` - CSV → beneficial ownership overlap

### LangGraph Workflow
```
START → agent → tools? → [tools → agent]* → respond → END
```
- `agent`: Main reasoning (calls tools)
- `tools`: ToolNode executor (parallel execution)
- `respond`: Structured output (Pydantic model)
- Recursion limit: 50

### Event Streaming (SSE)

Real-time progress over 5-10 minute analyses:

```
Browser EventSource (/api/stream/{task_id})
    ↓ SSE
Frontend (/message/stream proxy via httpx)
    ↓ A2A JSON-RPC SSE
Orchestrator → Agent → LangGraph (astream_events)
    ↓ Events
tool_started → tool_progress → tool_completed → analysis_complete
```

**Event Types**: `analysis_started`, `routing`, `evaluation_started`, `tool_started`, `tool_progress`, `tool_completed`, `analysis_complete`, `error`

**Key Files**:
- `a2a/event_mapper.py` - LangGraph → A2A event conversion
- `frontend/static/js/streaming.js` - EventSource client
- `frontend/static/js/dag-visualization.js` - Live execution DAG

---

## Directory Index

### Backend Core
```
src/alerts/
├── main.py                     # CLI entry point
├── config.py                   # Env-based config (fail-fast validation)
├── llm_factory.py              # LLM provider factory (4 providers)
├── agent.py                    # [SHIM → agents.insider_trading]
└── models.py                   # [SHIM → models/]
```

### Models (Output Schemas)
```
src/alerts/models/
├── base.py                     # BaseAlertDecision
├── insider_trading.py          # InsiderTradingDecision (11 fields)
└── wash_trade.py               # WashTradeDecision + RelationshipNetwork (14 fields)
```

### Agents
```
src/alerts/agents/
├── insider_trading/
│   ├── agent.py                # InsiderTradingAnalyzerAgent
│   ├── prompts/system_prompt.py # System prompt + few-shot loader
│   └── tools/                  # 2 IT-specific tools
│       ├── trader_history.py
│       └── market_news.py
└── wash_trade/
    ├── agent.py                # WashTradeAnalyzerAgent
    ├── prompts/system_prompt.py
    └── tools/                  # 4 WT-specific tools
        ├── account_relationships.py
        ├── related_accounts_history.py
        ├── trade_timing.py
        └── counterparty_analysis.py
```

### Tools (Common)
```
src/alerts/tools/
├── common/                     # 3 shared tools (USE THESE)
│   ├── base.py                 # BaseTool with LLM + streaming
│   ├── alert_reader.py
│   ├── trader_profile.py
│   └── market_data.py
├── alert_reader.py             # [LEGACY SHIM]
├── trader_profile.py           # [LEGACY SHIM]
└── market_data.py              # [LEGACY SHIM]
```

### Reports
```
src/alerts/reports/
├── html_generator.py           # IT HTML report (Tailwind CSS)
├── wash_trade_report.py        # WT HTML report + network graph
└── wash_trade_graph.py         # SVG network visualization
```

### A2A (Agent-to-Agent Protocol)
```
src/alerts/a2a/
├── orchestrator.py             # Alert routing logic
├── orchestrator_executor.py    # Orchestrator A2A executor + streaming proxy
├── orchestrator_server.py      # Port 10000
├── insider_trading_executor.py # IT A2A executor (execute/execute_stream)
├── insider_trading_server.py   # Port 10001
├── wash_trade_executor.py      # WT A2A executor
├── wash_trade_server.py        # Port 10002
├── event_mapper.py             # LangGraph → A2A event mapping + buffer
└── test_client.py              # CLI test client
```

### Frontend (Web UI)
```
src/frontend/
├── app.py                      # FastAPI routes + A2A client + SSE proxy
├── task_manager.py             # In-memory task tracking
├── templates/
│   ├── base.html               # Tailwind CSS base
│   └── upload.html             # Upload + timeline UI
└── static/js/
    ├── upload.js               # Drag-drop file upload
    ├── streaming.js            # EventSource SSE client
    ├── progress-timeline.js    # Timeline visualization
    ├── results.js              # Results + Cytoscape network graph
    └── dag-visualization.js    # Real-time execution DAG

API Endpoints:
- POST /api/analyze              # Upload alert
- GET /api/stream/{task_id}      # SSE progress stream
- GET /api/status/{task_id}      # Polling fallback
- GET /api/download/{task_id}/json|html
```

### Test Data
```
test_data/
├── alerts/
│   ├── alert_genuine.xml        # IT test cases
│   ├── alert_false_positive.xml
│   ├── alert_ambiguous.xml
│   └── wash_trade/              # WT test cases
│       ├── wash_genuine.xml
│       ├── wash_ambiguous.xml
│       └── wash_layered.xml
├── few_shot_examples.json       # IT precedents (tune IT behavior HERE)
├── wash_trade_few_shot_examples.json # WT precedents (tune WT behavior HERE)
├── *.csv                        # Market/trader data (7 files)
├── market_news.txt
└── wash_trade/*.csv             # WT-specific data (2 files)
```

### Output & Scripts
```
resources/
├── reports/                     # decision_{id}.json/html, audit_log.jsonl
└── debug/                       # a2a_response_*.json

scripts/
├── start_all_servers.sh         # Start all A2A + frontend (background)
└── test_frontend_api.sh         # API test script

logs/                            # Runtime logs (from start_all_servers.sh)
```

---

## Integration Points

### LLM Providers (via config)
Set `LLM_PROVIDER` in `.env`:
- `openai` - Requires: `OPENAI_API_KEY`, `OPENAI_MODEL`
- `azure` - Requires: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`
- `openrouter` - Requires: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`
- `gemini` - Requires: `GOOGLE_API_KEY`, `GEMINI_MODEL`

**Factory**: `llm_factory.py:create_llm()`

### A2A Server URLs
**Default**:
- Orchestrator: `http://localhost:10000`
- IT Agent: `http://localhost:10001`
- WT Agent: `http://localhost:10002`
- Frontend: `http://localhost:8080`

**Override**:
```bash
# Via CLI args
alerts-orchestrator-server --port 10000 \
    --insider-trading-url http://remote:10001 \
    --wash-trade-url http://remote:10002

alerts-frontend --port 8080 --orchestrator-url http://remote:10000
```

### Data Sources (POC - local files)
All tools read from `test_data/`:
- Alert XMLs: `alerts/*.xml`, `alerts/wash_trade/*.xml`
- CSVs: `trader_history.csv`, `trader_profiles.csv`, `market_data.csv`, `wash_trade/*.csv`
- Text: `market_news.txt`
- Few-shot: `few_shot_examples.json`, `wash_trade_few_shot_examples.json`

---

## Development Patterns

### Tune Agent Behavior (No Code Changes)

**Priority 1**: Edit few-shot examples
- IT: `test_data/few_shot_examples.json`
- WT: `test_data/wash_trade_few_shot_examples.json`

Add new precedent cases with detailed reasoning. Agent uses "case law" comparison.

**Priority 2**: Update system prompts
- IT: `agents/insider_trading/prompts/system_prompt.py`
- WT: `agents/wash_trade/prompts/system_prompt.py`

**Priority 3**: Modify agent graph (last resort)
- IT: `agents/insider_trading/agent.py:_build_graph()`
- WT: `agents/wash_trade/agent.py:_build_graph()`

### Add New Tool

**Common tool** (shared by all agents):
1. Create: `tools/common/your_tool.py` inheriting `BaseTool`
2. Set: `expected_format` class attribute (csv, xml, txt)
3. Implement: `_build_interpretation_prompt()` only
4. Export: `tools/common/__init__.py`
5. Add to agents: Both `InsiderTradingAnalyzerAgent` and `WashTradeAnalyzerAgent._create_tool_instances()`
6. Test: `tests/test_tools.py`

**Agent-specific tool**:
1. Create: `agents/{it|wt}/tools/your_tool.py`
2. Same implementation pattern
3. Export: `agents/{it|wt}/tools/__init__.py`
4. Add to agent: `{IT|WT}AnalyzerAgent._create_tool_instances()`
5. Test: `tests/test_tools.py`

**Tool Contract** (Proactive Information Flow):
```python
class YourTool(BaseTool):
    # Declare expected data format
    expected_format: str = "csv"  # or "xml", "txt"

    def __init__(self, llm: Any, data_dir: Path) -> None:
        super().__init__(
            llm=llm,
            name="your_tool_name",
            description="Description for agent prompt"
        )

    def _build_interpretation_prompt(self, raw_data: str, **kwargs) -> str:
        # Craft LLM prompt - this is the ONLY method you need to implement
        return f"Analyze this data: {raw_data}"

    # BaseTool.execute() handles: validate → LLM interpret → emit events → return insights
    # Data is INJECTED via execute(data=..., format=...) by Big Data Layer
```

### Add New Agent Type

1. Create: `agents/your_type/agent.py` (copy IT/WT structure)
2. Define model: `models/your_type.py` extending `BaseAlertDecision`
3. Create tools: `agents/your_type/tools/*.py`
4. System prompt: `agents/your_type/prompts/system_prompt.py`
5. A2A executor: `a2a/your_type_executor.py`
6. A2A server: `a2a/your_type_server.py`
7. Update orchestrator: `a2a/orchestrator.py:determine_alert_type()`
8. Add routing: `a2a/orchestrator.py:route_to_agent()`
9. Tests: `tests/test_a2a_orchestrator.py`

### Output Schema Changes

**IT Decision**: Edit `models/insider_trading.py:InsiderTradingDecision`
**WT Decision**: Edit `models/wash_trade.py:WashTradeDecision`

After schema change:
1. Update HTML report generator (`reports/html_generator.py` or `reports/wash_trade_report.py`)
2. Update frontend results rendering (`frontend/static/js/results.js`)
3. Update tests (`tests/test_models.py` or `tests/test_wash_trade_models.py`)

### Extend SSE Events

1. Add event type: `a2a/event_mapper.py:map_*_event()`
2. Update frontend: `frontend/static/js/progress-timeline.js:_handleEvent()`
3. Update DAG: `frontend/static/js/dag-visualization.js` (if execution flow changes)

---

## Key Constraints

### Fail-Fast Philosophy
**No graceful degradation**. Errors crash loudly for immediate debugging.
- Tool failure → entire analysis fails
- Missing env var → startup fails
- Invalid data → exception raised

**Rationale**: POC phase prioritizes visibility over resilience.

### No Hardcoded Scoring
**Pure LLM reasoning**. Zero weight-based formulas.
- To adjust behavior → edit few-shot examples
- No `if confidence > 0.7` logic
- No threshold constants

### Tool Returns Insights, Not Data
**Two-tier LLM**:
- Tier 1: Tool-level LLM interprets raw data
- Tier 2: Agent LLM reasons over insights

❌ Bad: `"trader_history.csv has 247 rows"`
✅ Good: `"Trader typically 5K shares/day in tech. Flagged 50K healthcare trade is 10x volume, new sector"`

### POC Data Sources
All data from local files in `test_data/`. Production requires:
- Update Big Data Layer to fetch from DB/API instead of files
- Tools receive data via `execute(data=..., format=...)` - no changes needed
- Keep `_build_interpretation_prompt()` unchanged

### NEVER Modify
- `.env` file (contains secrets, gitignored)
- Legacy shim files (`agent.py`, `models.py`, `tools/*.py` except `common/`)

---

## Output Formats

### Decision Files
- **JSON**: `resources/reports/decision_{alert_id}.json` (full schema)
- **HTML**: `resources/reports/decision_{alert_id}.html` (Tailwind CSS, professional)
- **Audit**: `resources/reports/audit_log.jsonl` (append-only JSONL)

### IT Decision Schema (11 fields)
`determination`, `genuine_alert_confidence`, `false_positive_confidence`, `key_findings`, `favorable_indicators`, `risk_mitigating_factors`, `trader_baseline_analysis`, `market_context`, `reasoning_narrative`, `similar_precedent`, `recommended_action`

### WT Decision Schema (14 fields)
IT fields + `relationship_network`, `timing_patterns`, `trade_flows`, `counterparty_patterns`, `historical_pattern_summary`, `regulatory_framework`

---

## Testing Strategy

**Unit tests**: Tools, models, config, HTML generation
**Integration tests**: A2A executors, servers, streaming
**Fixtures**: `tests/conftest.py`
**Mock LLMs**: Deterministic test responses
**Coverage**: `pytest --cov=alerts`

---

## Anti-Patterns

❌ Return raw data from tools
❌ Add hardcoded scoring/thresholds
❌ Silently catch errors
❌ Create files in project root
❌ Modify `.env`
❌ Use legacy tool paths (`tools/*.py` vs `tools/common/*.py`)
❌ Edit shim files (`agent.py`, `models.py`)

---

## Reference

**LangGraph**: `resources/research/langgraph/`
**Architecture**: `.dev-resources/architecture/*.md`
**A2A Protocol**: Google's Agent-to-Agent standard (JSON-RPC over HTTP)
**APAC Regulations**: MAS SFA, SFC SFO, ASIC, FSA FIEA
