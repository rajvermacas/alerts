# Analysis Cards UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 4 analysis cards (News, PnL, Client Risk, Trader History) to standalone UI with expandable pattern graph.

**Architecture:** Extend existing cards_renderer.js with new `renderAnalysisCards()` function. Create pattern_graph.js for Cytoscape visualization. Update demo.json with analysisCards data. Wire up in demo_player.js.

**Tech Stack:** Vanilla JS, Cytoscape.js (already loaded), Tailwind CSS

---

## Task 1: Update demo.json with analysisCards data

**Files:**
- Modify: `standalone_ui/data/demo.json:261` (add after closing `}` of cards)

**Step 1: Add analysisCards object**

Add this after line 261 (after the `cards` closing brace, before final `}`):

```json
  "analysisCards": {
    "newsAnalysis": {
      "title": "News Analysis",
      "summary": "No material public news explains the observed volume spike in the relevant window."
    },
    "pnlAnalysis": {
      "title": "Profit And Loss Analysis",
      "summary": "PNL impact is positive and concentrated; the trade sequence suggests potential intent to generate artificial liquidity."
    },
    "clientRiskAnalysis": {
      "title": "Client Risk Analysis",
      "summary": "Client risk score elevated due to prior alerts and concentrated activity across related accounts."
    },
    "traderHistoryAnalysis": {
      "title": "Trader History Analysis",
      "summary": "Trader typically 5K shares/day tech. Flagged 50K healthcare = 10x volume, new sector.",
      "patternGraph": {
        "title": "Trading Pattern Analysis",
        "description": "Trader activity across sectors showing volume anomaly",
        "nodes": [
          { "id": "trader", "label": "Trader", "type": "trader", "size": "medium" },
          { "id": "tech", "label": "Tech Sector", "type": "sector", "size": "small", "volume": 5000, "isBaseline": true },
          { "id": "healthcare", "label": "Healthcare", "type": "sector", "size": "large", "volume": 50000, "isAnomaly": true },
          { "id": "baseline", "label": "Baseline\n5K/day", "type": "metric", "size": "small" },
          { "id": "flagged", "label": "Flagged\n50K", "type": "metric", "size": "large", "isAnomaly": true }
        ],
        "edges": [
          { "id": "e1", "source": "trader", "target": "tech", "label": "Typical", "weight": 1 },
          { "id": "e2", "source": "trader", "target": "healthcare", "label": "Flagged Trade", "weight": 10, "isAnomaly": true },
          { "id": "e3", "source": "tech", "target": "baseline", "label": "90-day avg" },
          { "id": "e4", "source": "healthcare", "target": "flagged", "label": "10x spike", "isAnomaly": true }
        ]
      }
    }
  }
```

**Step 2: Validate JSON syntax**

Run: `python -m json.tool standalone_ui/data/demo.json > /dev/null && echo "Valid JSON"`
Expected: `Valid JSON`

**Step 3: Commit**

```bash
git add standalone_ui/data/demo.json
git commit -m "feat(ui): add analysisCards data to demo.json"
```

---

## Task 2: Create pattern_graph.js

**Files:**
- Create: `standalone_ui/static/js/pattern_graph.js`

**Step 1: Create pattern_graph.js with Cytoscape initialization**

```javascript
import { createLogger } from './logger.js';
import { showToast } from './toast.js';

const logger = createLogger('pattern_graph');

function requireCytoscape() {
    if (typeof window.cytoscape !== 'function') {
        throw new Error('pattern_graph: cytoscape not available');
    }
    return window.cytoscape;
}

function requireContainer(containerId) {
    const el = document.getElementById(containerId);
    if (!el) {
        throw new Error(`pattern_graph: missing container #${containerId}`);
    }
    return el;
}

function getNodeSize(node) {
    const sizes = { small: 30, medium: 45, large: 60 };
    return sizes[node.size] || 40;
}

function toCytoscapeElements(spec) {
    const nodes = spec.nodes.map((n) => ({
        data: {
            id: n.id,
            label: n.label,
            type: n.type,
            size: getNodeSize(n),
            isAnomaly: n.isAnomaly || false,
            isBaseline: n.isBaseline || false,
            volume: n.volume || 0,
        },
    }));
    const edges = spec.edges.map((e) => ({
        data: {
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.label || '',
            weight: e.weight || 1,
            isAnomaly: e.isAnomaly || false,
        },
    }));
    return { nodes, edges };
}

export function initPatternGraph(containerId, patternGraphSpec) {
    const container = requireContainer(containerId);
    const cytoscape = requireCytoscape();
    const elements = toCytoscapeElements(patternGraphSpec);

    logger.info('init pattern graph', { nodes: elements.nodes.length, edges: elements.edges.length });

    const cy = cytoscape({
        container,
        elements,
        style: [
            {
                selector: 'node',
                style: {
                    'background-color': '#6B7280',
                    'label': 'data(label)',
                    'text-valign': 'bottom',
                    'text-halign': 'center',
                    'font-size': '10px',
                    'text-margin-y': '5px',
                    'width': 'data(size)',
                    'height': 'data(size)',
                    'text-wrap': 'wrap',
                    'text-max-width': '80px',
                },
            },
            {
                selector: 'node[type="trader"]',
                style: {
                    'background-color': '#2563EB',
                    'border-width': '3px',
                    'border-color': '#1D4ED8',
                },
            },
            {
                selector: 'node[?isAnomaly]',
                style: {
                    'background-color': '#DC2626',
                    'border-width': '3px',
                    'border-color': '#991B1B',
                },
            },
            {
                selector: 'node[?isBaseline]',
                style: {
                    'background-color': '#9CA3AF',
                    'border-width': '2px',
                    'border-color': '#6B7280',
                },
            },
            {
                selector: 'edge',
                style: {
                    'width': 2,
                    'line-color': '#9CA3AF',
                    'target-arrow-color': '#9CA3AF',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'label': 'data(label)',
                    'font-size': '9px',
                    'text-rotation': 'autorotate',
                    'text-margin-y': '-10px',
                },
            },
            {
                selector: 'edge[?isAnomaly]',
                style: {
                    'line-color': '#DC2626',
                    'target-arrow-color': '#DC2626',
                    'width': 3,
                    'line-style': 'dashed',
                },
            },
        ],
        layout: {
            name: 'concentric',
            concentric: (node) => (node.data('type') === 'trader' ? 10 : 5),
            levelWidth: () => 2,
            minNodeSpacing: 50,
            padding: 30,
        },
    });

    cy.fit();

    cy.on('tap', 'node', (evt) => {
        const data = evt.target.data();
        const info = data.volume
            ? `${data.label}\nVolume: ${data.volume.toLocaleString()}`
            : data.label;
        showToast(info, 'info');
    });

    logger.info('pattern graph initialized');
    return cy;
}
```

**Step 2: Commit**

```bash
git add standalone_ui/static/js/pattern_graph.js
git commit -m "feat(ui): add pattern_graph.js for trader history visualization"
```

---

## Task 3: Update cards_renderer.js with renderAnalysisCards

**Files:**
- Modify: `standalone_ui/static/js/cards_renderer.js`

**Step 1: Add renderAnalysisCards function after line 244**

Add before the final empty line:

```javascript
function createExpandableGraphContainer(cardKey, patternGraph) {
    const graphId = `pattern-graph-${cardKey}`;
    const wrapper = document.createElement('div');
    wrapper.className = 'mt-4';

    const button = document.createElement('button');
    button.className = 'flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors';
    button.innerHTML = `
        <svg class="w-4 h-4 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
        </svg>
        <span>View Pattern Graph</span>
    `;

    const graphContainer = document.createElement('div');
    graphContainer.id = graphId;
    graphContainer.className = 'hidden mt-4 h-64 border border-gray-200 rounded-lg bg-gray-50';
    graphContainer.dataset.patternGraph = JSON.stringify(patternGraph);

    let expanded = false;
    button.addEventListener('click', () => {
        expanded = !expanded;
        graphContainer.classList.toggle('hidden', !expanded);
        button.querySelector('svg').style.transform = expanded ? 'rotate(90deg)' : '';
        button.querySelector('span').textContent = expanded ? 'Hide Pattern Graph' : 'View Pattern Graph';

        if (expanded && !graphContainer.dataset.initialized) {
            graphContainer.dataset.initialized = 'true';
            window.dispatchEvent(new CustomEvent('initPatternGraph', {
                detail: { containerId: graphId, spec: patternGraph }
            }));
        }
    });

    wrapper.appendChild(button);
    wrapper.appendChild(graphContainer);
    return wrapper;
}

function renderAnalysisCard(key, cardData) {
    const card = document.createElement('div');
    card.className = 'bg-white rounded-lg shadow-md p-6';

    const h3 = document.createElement('h3');
    h3.className = 'text-lg font-semibold text-gray-900 mb-3';
    h3.textContent = cardData.title;
    card.appendChild(h3);

    const summary = document.createElement('p');
    summary.className = 'text-gray-700 text-sm';
    summary.textContent = cardData.summary;
    card.appendChild(summary);

    if (cardData.patternGraph) {
        card.appendChild(createExpandableGraphContainer(key, cardData.patternGraph));
    }

    return card;
}

export function renderAnalysisCards(analysisCards) {
    const results = requireElementById('results-section');
    if (!analysisCards || typeof analysisCards !== 'object') {
        throw new Error('cards_renderer: analysisCards (object) is required');
    }

    const order = ['newsAnalysis', 'pnlAnalysis', 'clientRiskAnalysis', 'traderHistoryAnalysis'];

    order.forEach((key) => {
        if (!analysisCards[key]) {
            throw new Error(`cards_renderer: analysisCards.${key} is required`);
        }
        const cardData = analysisCards[key];
        if (!cardData.title || !cardData.summary) {
            throw new Error(`cards_renderer: analysisCards.${key} must have title and summary`);
        }
        results.appendChild(renderAnalysisCard(key, cardData));
    });

    logger.info('rendered analysis cards', { count: order.length });
}
```

**Step 2: Commit**

```bash
git add standalone_ui/static/js/cards_renderer.js
git commit -m "feat(ui): add renderAnalysisCards with expandable graph support"
```

---

## Task 4: Update demo_player.js to wire up rendering

**Files:**
- Modify: `standalone_ui/static/js/demo_player.js`

**Step 1: Add import for renderAnalysisCards (line 5)**

Change line 5 from:
```javascript
import { renderCardsIntoResults } from './cards_renderer.js';
```
To:
```javascript
import { renderCardsIntoResults, renderAnalysisCards } from './cards_renderer.js';
```

**Step 2: Add import for initPatternGraph (after line 6)**

Add after line 6:
```javascript
import { initPatternGraph } from './pattern_graph.js';
```

**Step 3: Add event listener for pattern graph initialization (after line 8)**

Add after the logger line:
```javascript
window.addEventListener('initPatternGraph', (evt) => {
    const { containerId, spec } = evt.detail;
    initPatternGraph(containerId, spec);
});
```

**Step 4: Add renderAnalysisCards call (after line 146)**

After `renderCardsIntoResults(spec.cards);` add:
```javascript
                if (spec.analysisCards) {
                    renderAnalysisCards(spec.analysisCards);
                }
```

**Step 5: Commit**

```bash
git add standalone_ui/static/js/demo_player.js
git commit -m "feat(ui): wire up analysis cards and pattern graph rendering"
```

---

## Task 5: Test in browser

**Step 1: Start a local server**

Run: `cd standalone_ui && python -m http.server 8000`

**Step 2: Open browser and verify**

Open: `http://localhost:8000`

Verify:
1. Click "Start" in execution flow
2. Wait for demo to complete
3. Results section shows in order:
   - Confidence Scores
   - AI Analysis Insights
   - Key Findings
   - News Analysis (NEW)
   - Profit And Loss Analysis (NEW)
   - Client Risk Analysis (NEW)
   - Trader History Analysis (NEW with "View Pattern Graph" button)
   - Relationship Network
4. Click "View Pattern Graph" button - graph expands
5. Click again - graph collapses

**Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(ui): address any issues found in testing"
```
