# SMARTS Alert Analyzer - Developer Reference

**Mission**: Intelligent compliance filter using deterministic multi-agent architecture to analyze SMARTS surveillance alerts (insider trading, wash trading) and reduce false positives.

**Core Philosophy**: Proactive information flow - Big Data Layer aggregates all required data upfront, agents execute tools in fixed order without LLM routing.

---

## Quick Commands

### Setup
```bash
pip install -e .                    # Production
pip install -e ".[dev]"             # Development + testing
cp .env.example .env                # Edit: LLM_PROVIDER, API keys
```

### Run Analysis
```bash
# CLI (single alert)
python -m alerts.main --alert test_data/alerts/wash_trade/wash_genuine.xml

# Multi-Agent (A2A servers + web UI)
bash scripts/start_all_servers.sh
# Open: http://localhost:8080
# Logs: logs/{insider_trading,wash_trade,orchestrator,frontend}.log
```

### Testing
```bash
pytest --cov=alerts
```

---

## Architecture

### Multi-Agent Flow (Deterministic)
```
Big Data Layer → Orchestrator (Port 10000) → Agent (Port 10001/10002) → Output
      ↓              ↓                            ↓
  Aggregates     Routes by         Executes tools in FIXED order
  all data       alert type        (no LLM routing)
```

**Alert Types**:
- **IT**: `insider|pre-announcement|mnpi`, `SMARTS-IT-*|SMARTS-PAT-*`
- **WT**: `wash|self-trade|circular`, `SMARTS-WT-*|WT-*|WASH_TRADE`

**Agents**:
- Insider Trading: Port 10001 → 5 tools
- Wash Trade: Port 10002 → 7 tools

### Request Model (API Contract)
```python
class AnalysisRequest:
    alert_id: str
    agent_type: "insider_trading" | "wash_trade"
    tool_data: Dict[str, ToolInput]  # Pre-aggregated by Big Data Layer
```

**ToolInput**:
- `format`: "xml" | "csv" | "txt"
- `data`: Raw content string

**Fail-Fast**: Missing required tool data → immediate error (no fallbacks)

### Deterministic Execution
```
Agent Loop:
1. Validate all required tools present in request
2. Execute tools in FIXED order (TOOL_ORDER tuple)
3. LLM interprets each tool's data → insights
4. Synthesize final decision from all insights
```

**No LLM routing** - tool order hardcoded per agent type.

### Tool Execution Order
**IT Agent** (`TOOL_ORDER`):
1. alert_reader
2. market_news
3. market_data
4. trader_profile
5. trader_history

**WT Agent** (`TOOL_ORDER`):
1. alert_reader
2. account_relationships
3. related_accounts_history
4. trade_timing
5. market_data
6. trader_profile
7. counterparty_analysis

### Event Streaming (SSE)
```
Browser EventSource → Frontend Proxy → Orchestrator → Agent → Tool Events
```

**Event Types**: `analysis_started`, `routing`, `tool_started`, `tool_progress`, `tool_completed`, `analysis_complete`, `error`

---

## Directory Index

### Core Backend
```
src/alerts/
├── main.py                     # CLI entry point
├── config.py                   # Env-based config (fail-fast)
├── llm_factory.py              # LLM provider factory
├── agent.py                    # [SHIM → agents.insider_trading]
└── models.py                   # [SHIM → models/]
```

### Models
```
src/alerts/models/
├── request.py                  # AnalysisRequest, ToolInput (API contract)
├── base.py                     # BaseAlertDecision
├── insider_trading.py          # InsiderTradingDecision (11 fields)
└── wash_trade.py               # WashTradeDecision (14 fields)
```

### Agents (Deterministic)
```
src/alerts/agents/
├── insider_trading/
│   ├── deterministic_agent.py  # Fixed tool loop (no LangGraph)
│   ├── prompts/system_prompt.py# System prompt + few-shot loader
│   └── tools/*.py              # TraderHistoryTool, MarketNewsTool
└── wash_trade/
    ├── deterministic_agent.py  # Fixed tool loop
    ├── prompts/system_prompt.py
    └── tools/*.py              # 4 WT-specific tools
```

### Tools (Common)
```
src/alerts/tools/common/
├── base.py                     # BaseTool (LLM interpretation)
├── alert_reader.py             # Parse XML
├── trader_profile.py           # MNPI access
└── market_data.py              # Price/volume analysis
```

### Reports
```
src/alerts/reports/
├── html_generator.py           # IT HTML report (Tailwind CSS)
├── wash_trade_report.py        # WT HTML + network graph
└── wash_trade_graph.py         # SVG network viz
```

### A2A Servers
```
src/alerts/a2a/
├── orchestrator.py             # Alert routing logic
├── orchestrator_executor.py    # Orchestrator A2A executor + SSE proxy
├── orchestrator_server.py      # Port 10000
├── insider_trading_executor.py # IT executor (execute/execute_stream)
├── insider_trading_server.py   # Port 10001
├── wash_trade_executor.py      # WT executor
├── wash_trade_server.py        # Port 10002
└── event_mapper.py             # Agent → A2A event mapping
```

### Frontend (Web UI)
```
src/frontend/
├── app.py                      # FastAPI routes + A2A client
├── task_manager.py             # In-memory task tracking
├── templates/*.html            # Tailwind CSS UI
└── static/js/
    ├── streaming.js            # EventSource SSE client
    ├── progress-timeline.js    # Timeline visualization
    ├── results.js              # Cytoscape network graphs
    └── dag-visualization.js    # Real-time execution DAG
```

**API Endpoints**:
- `POST /api/analyze` - Upload alert
- `GET /api/stream/{task_id}` - SSE progress
- `GET /api/status/{task_id}` - Polling fallback
- `GET /api/download/{task_id}/json|html`

### Test Data
```
test_data/
├── alerts/*.xml                # IT test cases
├── alerts/wash_trade/*.xml     # WT test cases
├── few_shot_examples.json      # IT precedents
├── wash_trade_few_shot_examples.json  # WT precedents
├── *.csv                       # Market/trader data
└── wash_trade/*.csv            # WT-specific data
```

---

## Integration Points

### LLM Providers
Set `LLM_PROVIDER` in `.env`:
- `openai` → `OPENAI_API_KEY`, `OPENAI_MODEL`
- `azure` → `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`
- `openrouter` → `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`
- `gemini` → `GOOGLE_API_KEY`, `GEMINI_MODEL`

**Factory**: `llm_factory.py:create_llm()`

### A2A Server URLs
**Default**:
- Orchestrator: `http://localhost:10000`
- IT Agent: `http://localhost:10001`
- WT Agent: `http://localhost:10002`
- Frontend: `http://localhost:8080`

**Override via CLI args**:
```bash
alerts-orchestrator-server --port 10000 \
    --insider-trading-url http://remote:10001 \
    --wash-trade-url http://remote:10002
```

### Big Data Layer Contract
**OpenAPI Spec**: `models/request.py` (source of truth)

**Required Tools per Agent**:
- IT: `alert_reader`, `market_news`, `market_data`, `trader_profile`, `trader_history`
- WT: `alert_reader`, `market_data`, `trader_profile`, `account_relationships`, `related_accounts_history`, `trade_timing`, `counterparty_analysis`

**Validation**: `AnalysisRequest.model_validator` fails on missing tools

---

## Development Patterns

### Tune Agent Behavior (No Code)
**Priority 1**: Edit few-shot examples
- IT: `test_data/few_shot_examples.json`
- WT: `test_data/wash_trade_few_shot_examples.json`

**Priority 2**: Update system prompts
- IT: `agents/insider_trading/prompts/system_prompt.py`
- WT: `agents/wash_trade/prompts/system_prompt.py`

### Add New Tool
**Common tool** (all agents):
1. Create: `tools/common/your_tool.py` extending `BaseTool`
2. Implement: `_load_data()`, `_build_interpretation_prompt()`
3. Export: `tools/common/__init__.py`
4. Add to both agents' `deterministic_agent.py:TOOL_ORDER`
5. Update `models/request.py:*_REQUIRED_TOOLS` and `TOOL_FORMAT_REQUIREMENTS`

**Agent-specific tool**:
1. Create: `agents/{it|wt}/tools/your_tool.py`
2. Add to `agents/{it|wt}/deterministic_agent.py:TOOL_ORDER`
3. Update `models/request.py`

**Tool Contract**:
```python
class YourTool(BaseTool):
    def _load_data(self, **kwargs) -> str:
        # Accept data via kwargs (injected from AnalysisRequest)
        return kwargs.get("data", "")

    def _build_interpretation_prompt(self, raw_data: str, **kwargs) -> str:
        # Craft LLM prompt
        pass
```

### Add New Agent Type
1. Create: `agents/your_type/deterministic_agent.py` (copy IT/WT structure)
2. Define model: `models/your_type.py` extending `BaseAlertDecision`
3. Create tools: `agents/your_type/tools/*.py`
4. Define `TOOL_ORDER` tuple
5. A2A executor: `a2a/your_type_executor.py`
6. A2A server: `a2a/your_type_server.py`
7. Update orchestrator: `a2a/orchestrator.py:determine_alert_type()`
8. Update request model: `models/request.py` (add required tools)

### Output Schema Changes
Edit `models/{insider_trading|wash_trade}.py`, then update:
1. HTML report generator (`reports/`)
2. Frontend rendering (`frontend/static/js/results.js`)
3. Tests (`tests/test_*_models.py`)

---

## Key Constraints

### Fail-Fast Philosophy
**No graceful degradation**. Errors crash loudly.
- Missing tool data → entire analysis fails
- Invalid format → exception raised
- Missing env var → startup fails

### No Hardcoded Scoring
**Pure LLM reasoning**. Zero formulas.
- Tune via few-shot examples, not code
- No `if confidence > 0.7` logic

### Tool Returns Insights, Not Data
**Two-tier LLM**:
- Tier 1: Tool LLM interprets raw data
- Tier 2: Agent LLM reasons over insights

❌ Bad: `"trader_history.csv has 247 rows"`
✅ Good: `"Trader typically 5K shares/day. Flagged 50K trade is 10x baseline"`

### Deterministic Execution
**Fixed tool order** in `TOOL_ORDER` tuple - no LLM routing.

### Data Source Decoupling
Tools accept data via `**kwargs`, not file I/O:
```python
def _load_data(self, **kwargs) -> str:
    return kwargs.get("data", "")  # Injected from AnalysisRequest
```

---

## Output Formats

### Decision Files
- **JSON**: `resources/reports/decision_{alert_id}.json`
- **HTML**: `resources/reports/decision_{alert_id}.html`
- **Audit**: `resources/reports/audit_log.jsonl`

### IT Decision Schema (11 fields)
`determination`, `genuine_alert_confidence`, `false_positive_confidence`, `key_findings`, `favorable_indicators`, `risk_mitigating_factors`, `trader_baseline_analysis`, `market_context`, `reasoning_narrative`, `similar_precedent`, `recommended_action`

### WT Decision Schema (14 fields)
IT fields + `relationship_network`, `timing_patterns`, `trade_flows`, `counterparty_patterns`, `historical_pattern_summary`, `regulatory_framework`

---

## Testing Strategy

**Unit tests**: Tools, models, config
**Integration tests**: A2A executors, servers, streaming
**Fixtures**: `tests/conftest.py`
**Mock LLMs**: Deterministic responses
**Coverage**: `pytest --cov=alerts`

---

## Anti-Patterns

❌ Return raw data from tools
❌ Add hardcoded scoring/thresholds
❌ Silently catch errors
❌ Create files in project root
❌ Modify `.env`
❌ Add LLM-based tool routing (use fixed `TOOL_ORDER`)
❌ Load data from files in tools (accept via `**kwargs`)

---

## Reference

**Architecture**: `.dev-resources/architecture/proactive-info-flow.md`
**A2A Protocol**: Google's Agent-to-Agent (JSON-RPC over HTTP)
**APAC Regulations**: MAS SFA, SFC SFO, ASIC, FSA FIEA
