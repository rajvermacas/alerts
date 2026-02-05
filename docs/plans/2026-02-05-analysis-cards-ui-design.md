# Analysis Cards UI Design

**Date:** 2026-02-05
**Status:** Approved
**Scope:** Add 4 analysis cards to standalone UI with expandable Trader History pattern graph

---

## Overview

Modify the standalone UI to display 4 analysis cards (News Analysis, PnL Analysis, Client Risk Analysis, Trader History Analysis) after Key Findings. The Trader History card includes an expandable pattern graph showing trader activity across sectors with volume anomaly visualization.

## Component Render Order

```
Results Section:
1. Confidence Scores (existing)
2. AI Analysis Insights (existing)
3. Key Findings (existing)
4. News Analysis (NEW)
5. Profit And Loss Analysis (NEW)
6. Client Risk Analysis (NEW)
7. Trader History Analysis (NEW - with expandable graph)
8. Relationship Network (existing - circular trade loop)
```

## Data Structure

### New `analysisCards` in demo.json

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
    "patternGraph": { ... }
  }
}
```

### Pattern Graph Structure

```json
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
    { "source": "trader", "target": "tech", "label": "Typical", "weight": 1 },
    { "source": "trader", "target": "healthcare", "label": "Flagged Trade", "weight": 10, "isAnomaly": true },
    { "source": "tech", "target": "baseline", "label": "90-day avg" },
    { "source": "healthcare", "target": "flagged", "label": "10x spike", "isAnomaly": true }
  ]
}
```

## Visual Styling

### Pattern Graph
- **Trader node:** Blue, centered (concentric layout)
- **Baseline nodes:** Gray color, smaller size
- **Anomaly nodes:** Red color, larger size
- **Edge weights:** Thicker lines for higher weight
- **Anomaly edges:** Red, dashed style

### Expandable Button
- Default: "View Pattern Graph" (graph hidden)
- Clicked: "Hide Pattern Graph" (graph visible with animation)

## File Changes

### 1. `standalone_ui/data/demo.json`
- Add `analysisCards` object with 4 cards
- Add `patternGraph` inside `traderHistoryAnalysis`

### 2. `standalone_ui/static/js/cards_renderer.js`
- Add `renderAnalysisCards(analysisCards)` export
- Add `renderAnalysisCard(key, cardData)` internal function
- Add `createExpandableGraphContainer(cardData)` for button + hidden graph

### 3. `standalone_ui/static/js/pattern_graph.js` (NEW)
- `initPatternGraph(containerId, patternGraph)` - Cytoscape init
- Concentric layout with trader at center
- Node styling based on type/anomaly flags
- Edge styling based on weight/anomaly flags

### 4. `standalone_ui/static/js/demo_player.js`
- Import `renderAnalysisCards` from cards_renderer
- Import `initPatternGraph` from pattern_graph
- Call `renderAnalysisCards(spec.analysisCards)` after existing cards
- Keep `renderRelationshipNetworkIfPresent()` at end

## Implementation Order

1. Update `demo.json` with new data structure
2. Create `pattern_graph.js` for Cytoscape visualization
3. Update `cards_renderer.js` with analysis card rendering
4. Update `demo_player.js` to wire up the render sequence
5. Test in browser
