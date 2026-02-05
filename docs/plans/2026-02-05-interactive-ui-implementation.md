# Interactive UI Enhancements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add subtle hover feedback to all interactive elements and staggered cascade animations for a fluid, professional user experience in the standalone_ui.

**Architecture:** Pure CSS approach with minimal JavaScript. Add reusable interactive classes to `styles.css`, then apply them in JS renderers. Staggered animations use CSS `animation-delay` applied dynamically.

**Tech Stack:** CSS transitions/animations, vanilla JavaScript (ES modules)

---

## Task 1: Add Interactive Hover Classes to CSS

**Files:**
- Modify: `standalone_ui/static/css/styles.css:362` (append to end)

**Step 1: Add interactive card hover styles**

Append to `standalone_ui/static/css/styles.css`:

```css
/* ============================================
   Interactive Hover States
   ============================================ */

/* Cards: subtle lift + shadow on hover */
.interactive-card {
    transition: transform 0.15s ease-out, box-shadow 0.15s ease-out, border-color 0.15s ease-out;
    border: 1px solid transparent;
}

.interactive-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    border-color: #E5E7EB;
}
```

**Step 2: Add interactive button hover styles**

Continue appending to `standalone_ui/static/css/styles.css`:

```css
/* Buttons: darken + scale feedback */
.interactive-btn {
    transition: transform 0.15s ease-out, background-color 0.15s ease-out, color 0.15s ease-out;
}

.interactive-btn:hover {
    transform: scale(1.05);
}

.interactive-btn:active {
    transform: scale(0.95);
}
```

**Step 3: Add interactive badge hover styles**

Continue appending:

```css
/* Badges: darken + slight scale */
.interactive-badge {
    transition: transform 0.15s ease-out, background-color 0.15s ease-out;
    cursor: default;
}

.interactive-badge:hover {
    transform: scale(1.03);
}

/* Tool badge specific hover */
.interactive-badge-tool:hover {
    background-color: #E5E7EB;
}

/* Agent badge specific hover */
.interactive-badge-agent:hover {
    background-color: #E0E7FF;
}
```

**Step 4: Add interactive table row hover styles**

Continue appending:

```css
/* Table rows: background highlight */
.interactive-row {
    transition: background-color 0.15s ease-out;
}

.interactive-row:hover {
    background-color: #F3F4F6;
}
```

**Step 5: Add connection status pill hover styles**

Continue appending:

```css
/* Connection status pill: border glow */
.connection-status {
    transition: border-color 0.15s ease-out, box-shadow 0.15s ease-out;
}

.connection-status:hover {
    border-color: #9CA3AF;
    box-shadow: 0 0 0 2px rgba(156, 163, 175, 0.2);
}
```

**Step 6: Add expandable details hover styles**

Continue appending:

```css
/* Expandable details: summary hover */
.interactive-details summary {
    transition: background-color 0.15s ease-out;
    border-radius: 6px;
    padding: 4px 8px;
    margin: -4px -8px;
}

.interactive-details summary:hover {
    background-color: #F3F4F6;
}
```

**Step 7: Verify CSS is valid**

Run: `cat standalone_ui/static/css/styles.css | tail -60`
Expected: Shows all new interactive classes without syntax errors

**Step 8: Commit**

```bash
git add standalone_ui/static/css/styles.css
git commit -m "feat(ui): add interactive hover state CSS classes

Add reusable classes for subtle hover feedback:
- interactive-card: lift + shadow
- interactive-btn: scale + active press
- interactive-badge: scale + darken
- interactive-row: background highlight
- connection-status: border glow
- interactive-details: summary hover"
```

---

## Task 2: Add Timeline Item Mini-Card Hover Styles

**Files:**
- Modify: `standalone_ui/static/css/styles.css` (append after Task 1)

**Step 1: Add timeline item interactive styles**

Append to `standalone_ui/static/css/styles.css`:

```css
/* ============================================
   Timeline Item Mini-Card Hover
   ============================================ */

.timeline-item {
    transition: transform 0.15s ease-out, background-color 0.15s ease-out,
                box-shadow 0.15s ease-out, border-left-width 0.15s ease-out;
    border-radius: 0 8px 8px 0;
    margin-right: 8px;
    padding-right: 8px;
}

.timeline-item:hover {
    transform: translateY(-2px);
    background-color: white;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    border-left-width: 3px;
}

.timeline-item:last-child:hover {
    border-left-color: #E5E7EB;
}
```

**Step 2: Verify CSS is valid**

Run: `cat standalone_ui/static/css/styles.css | tail -20`
Expected: Shows timeline item hover styles

**Step 3: Commit**

```bash
git add standalone_ui/static/css/styles.css
git commit -m "feat(ui): add timeline item mini-card hover effect

Timeline items now lift and gain shadow on hover,
with border thickening for visual feedback."
```

---

## Task 3: Add Staggered Animation CSS Classes

**Files:**
- Modify: `standalone_ui/static/css/styles.css` (append after Task 2)

**Step 1: Add stagger animation keyframes**

Append to `standalone_ui/static/css/styles.css`:

```css
/* ============================================
   Staggered Cascade Animations
   ============================================ */

@keyframes stagger-fade-slide-in {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.stagger-fade-in {
    opacity: 0;
    animation: stagger-fade-slide-in 0.3s ease-out forwards;
}

/* Delay utilities: 80ms increments */
.stagger-delay-1 { animation-delay: 80ms; }
.stagger-delay-2 { animation-delay: 160ms; }
.stagger-delay-3 { animation-delay: 240ms; }
.stagger-delay-4 { animation-delay: 320ms; }
.stagger-delay-5 { animation-delay: 400ms; }
.stagger-delay-6 { animation-delay: 480ms; }
.stagger-delay-7 { animation-delay: 560ms; }
.stagger-delay-8 { animation-delay: 640ms; }
```

**Step 2: Add graph delayed fade-in**

Continue appending:

```css
/* Graph containers fade in after card */
.graph-fade-in {
    opacity: 0;
    animation: stagger-fade-slide-in 0.3s ease-out forwards;
    animation-delay: 150ms;
}
```

**Step 3: Add page load stagger classes**

Continue appending:

```css
/* Page load sequence */
.page-stagger-1 {
    opacity: 0;
    animation: stagger-fade-slide-in 0.25s ease-out forwards;
    animation-delay: 0ms;
}

.page-stagger-2 {
    opacity: 0;
    animation: stagger-fade-slide-in 0.25s ease-out forwards;
    animation-delay: 100ms;
}

.page-stagger-3 {
    opacity: 0;
    animation: stagger-fade-slide-in 0.25s ease-out forwards;
    animation-delay: 200ms;
}
```

**Step 4: Verify CSS is valid**

Run: `cat standalone_ui/static/css/styles.css | tail -40`
Expected: Shows all stagger animation classes

**Step 5: Commit**

```bash
git add standalone_ui/static/css/styles.css
git commit -m "feat(ui): add staggered cascade animation CSS classes

Add animation utilities for visual rhythm:
- stagger-fade-in base class with slide-up effect
- stagger-delay-1 through stagger-delay-8 (80ms increments)
- graph-fade-in for delayed graph reveal
- page-stagger-1/2/3 for page load sequence"
```

---

## Task 4: Apply Interactive Classes to Cards Renderer

**Files:**
- Modify: `standalone_ui/static/js/cards_renderer.js:231-241` (renderCardsIntoResults)
- Modify: `standalone_ui/static/js/cards_renderer.js:267-286` (renderAnalysisCard)
- Modify: `standalone_ui/static/js/cards_renderer.js:100-134` (renderTable)

**Step 1: Update renderCardsIntoResults to add interactive-card class with stagger**

In `standalone_ui/static/js/cards_renderer.js`, find line 231-232:

```javascript
        const card = document.createElement('div');
        card.className = 'bg-white rounded-lg shadow-md p-6';
```

Replace with:

```javascript
        const card = document.createElement('div');
        const staggerIndex = Object.keys(obj).indexOf(title);
        const delayClass = staggerIndex < 8 ? `stagger-delay-${staggerIndex + 1}` : 'stagger-delay-8';
        card.className = `bg-white rounded-lg shadow-md p-6 interactive-card stagger-fade-in ${delayClass}`;
```

**Step 2: Update renderAnalysisCard to add interactive-card class with stagger**

In `standalone_ui/static/js/cards_renderer.js`, find line 267-269:

```javascript
function renderAnalysisCard(key, cardData) {
    const card = document.createElement('div');
    card.className = 'bg-white rounded-lg shadow-md p-6';
```

Change the function signature and body to accept an index:

```javascript
function renderAnalysisCard(key, cardData, staggerIndex) {
    const card = document.createElement('div');
    const delayClass = staggerIndex < 8 ? `stagger-delay-${staggerIndex + 1}` : 'stagger-delay-8';
    card.className = `bg-white rounded-lg shadow-md p-6 interactive-card stagger-fade-in ${delayClass}`;
```

**Step 3: Update renderAnalysisCards to pass stagger index**

In `standalone_ui/static/js/cards_renderer.js`, find line 296-305:

```javascript
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
```

Replace with:

```javascript
    order.forEach((key, index) => {
        if (!analysisCards[key]) {
            throw new Error(`cards_renderer: analysisCards.${key} is required`);
        }
        const cardData = analysisCards[key];
        if (!cardData.title || !cardData.summary) {
            throw new Error(`cards_renderer: analysisCards.${key} must have title and summary`);
        }
        results.appendChild(renderAnalysisCard(key, cardData, index));
    });
```

**Step 4: Update createVisibleGraphContainer to add graph-fade-in class**

In `standalone_ui/static/js/cards_renderer.js`, find line 252-253:

```javascript
    const graphContainer = document.createElement('div');
    graphContainer.id = graphId;
    graphContainer.className = 'mt-4 h-96 border border-gray-200 rounded-lg bg-gray-50';
```

Replace with:

```javascript
    const graphContainer = document.createElement('div');
    graphContainer.id = graphId;
    graphContainer.className = 'mt-4 h-96 border border-gray-200 rounded-lg bg-gray-50 graph-fade-in';
```

**Step 5: Update renderTable to add interactive-row class**

In `standalone_ui/static/js/cards_renderer.js`, find line 119-128:

```javascript
    rows.forEach((row) => {
        const tr = document.createElement('tr');
        keys.forEach((k) => {
            const td = document.createElement('td');
            td.className = 'px-4 py-2 text-gray-800';
            td.textContent = row[k] === null ? 'null' : String(row[k]);
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
```

Replace with:

```javascript
    rows.forEach((row) => {
        const tr = document.createElement('tr');
        tr.className = 'interactive-row';
        keys.forEach((k) => {
            const td = document.createElement('td');
            td.className = 'px-4 py-2 text-gray-800';
            td.textContent = row[k] === null ? 'null' : String(row[k]);
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
```

**Step 6: Verify the file is syntactically correct**

Run: `node --check standalone_ui/static/js/cards_renderer.js`
Expected: No output (syntax valid)

**Step 7: Commit**

```bash
git add standalone_ui/static/js/cards_renderer.js
git commit -m "feat(ui): apply interactive + stagger classes to cards renderer

- Cards get interactive-card class for hover lift
- Cards get stagger-fade-in with delay for cascade reveal
- Graph containers get graph-fade-in for delayed appearance
- Table rows get interactive-row for hover highlight"
```

---

## Task 5: Apply Interactive Classes to Timeline Renderer

**Files:**
- Modify: `standalone_ui/static/js/timeline_renderer.js:169-174` (badge classes)
- Modify: `standalone_ui/static/js/timeline_renderer.js:85-117` (details element)

**Step 1: Update tool badge to add interactive-badge class**

In `standalone_ui/static/js/timeline_renderer.js`, find line 169-173:

```javascript
        if (eventInfo.toolName) {
            const toolBadge = document.createElement('span');
            toolBadge.className = 'text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono';
            toolBadge.textContent = eventInfo.toolName;
            meta.appendChild(toolBadge);
        }
```

Replace with:

```javascript
        if (eventInfo.toolName) {
            const toolBadge = document.createElement('span');
            toolBadge.className = 'text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono interactive-badge interactive-badge-tool';
            toolBadge.textContent = eventInfo.toolName;
            meta.appendChild(toolBadge);
        }
```

**Step 2: Update agent badge to add interactive-badge class**

In `standalone_ui/static/js/timeline_renderer.js`, find line 176-180:

```javascript
        if (eventInfo.agentName) {
            const agentBadge = document.createElement('span');
            agentBadge.className = 'text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded';
            agentBadge.textContent = eventInfo.agentName;
            meta.appendChild(agentBadge);
        }
```

Replace with:

```javascript
        if (eventInfo.agentName) {
            const agentBadge = document.createElement('span');
            agentBadge.className = 'text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded interactive-badge interactive-badge-agent';
            agentBadge.textContent = eventInfo.agentName;
            meta.appendChild(agentBadge);
        }
```

**Step 3: Update createOutputSummaryElement to add interactive-details class**

In `standalone_ui/static/js/timeline_renderer.js`, find line 85-86:

```javascript
    const details = document.createElement('details');
    details.className = 'mt-2 bg-gray-50 rounded-md px-3 py-2 border border-gray-200';
```

Replace with:

```javascript
    const details = document.createElement('details');
    details.className = 'mt-2 bg-gray-50 rounded-md px-3 py-2 border border-gray-200 interactive-details';
```

**Step 4: Verify the file is syntactically correct**

Run: `node --check standalone_ui/static/js/timeline_renderer.js`
Expected: No output (syntax valid)

**Step 5: Commit**

```bash
git add standalone_ui/static/js/timeline_renderer.js
git commit -m "feat(ui): apply interactive classes to timeline renderer

- Tool badges get interactive-badge-tool for hover darken
- Agent badges get interactive-badge-agent for hover darken
- Details elements get interactive-details for summary hover"
```

---

## Task 6: Apply Interactive Classes to HTML Buttons

**Files:**
- Modify: `standalone_ui/index.html:76-89` (DAG control buttons)
- Modify: `standalone_ui/index.html:144-147` (reload button)

**Step 1: Update DAG reset button to add interactive-btn class**

In `standalone_ui/index.html`, find line 76-82:

```html
                            <button id="dag-reset-btn"
                                    class="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded hover:bg-gray-100"
                                    title="Reset layout">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                                </svg>
                            </button>
```

Replace with:

```html
                            <button id="dag-reset-btn"
                                    class="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded hover:bg-gray-100 interactive-btn"
                                    title="Reset layout">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                                </svg>
                            </button>
```

**Step 2: Update DAG maximize button to add interactive-btn class**

In `standalone_ui/index.html`, find line 83-89:

```html
                            <button id="dag-maximize-btn"
                                    class="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded hover:bg-gray-100"
                                    title="Maximize graph">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/>
                                </svg>
                            </button>
```

Replace with:

```html
                            <button id="dag-maximize-btn"
                                    class="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded hover:bg-gray-100 interactive-btn"
                                    title="Maximize graph">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/>
                                </svg>
                            </button>
```

**Step 3: Update reload button to add interactive-btn class**

In `standalone_ui/index.html`, find line 144-147:

```html
                        <button id="try-again-btn"
                                class="bg-gray-800 text-white py-2 px-6 rounded-lg font-semibold hover:bg-black transition-colors">
                            Reload
                        </button>
```

Replace with:

```html
                        <button id="try-again-btn"
                                class="bg-gray-800 text-white py-2 px-6 rounded-lg font-semibold hover:bg-black transition-colors interactive-btn">
                            Reload
                        </button>
```

**Step 4: Commit**

```bash
git add standalone_ui/index.html
git commit -m "feat(ui): add interactive-btn class to HTML buttons

DAG reset, maximize, and reload buttons now have
scale feedback on hover and press."
```

---

## Task 7: Add Page Load Stagger Animation

**Files:**
- Modify: `standalone_ui/index.html:34` (header)
- Modify: `standalone_ui/index.html:50` (main card)
- Modify: `standalone_ui/index.html:154` (footer)

**Step 1: Add page-stagger-1 to header**

In `standalone_ui/index.html`, find line 34:

```html
    <header class="bg-white shadow-sm border-b border-gray-200">
```

Replace with:

```html
    <header class="bg-white shadow-sm border-b border-gray-200 page-stagger-1">
```

**Step 2: Add page-stagger-2 to main card**

In `standalone_ui/index.html`, find line 50:

```html
            <div class="bg-white rounded-lg shadow-md overflow-hidden">
```

Replace with:

```html
            <div class="bg-white rounded-lg shadow-md overflow-hidden page-stagger-2">
```

**Step 3: Add page-stagger-3 to footer**

In `standalone_ui/index.html`, find line 154:

```html
    <footer class="bg-white border-t border-gray-200 mt-auto">
```

Replace with:

```html
    <footer class="bg-white border-t border-gray-200 mt-auto page-stagger-3">
```

**Step 4: Commit**

```bash
git add standalone_ui/index.html
git commit -m "feat(ui): add page load stagger animation

Header, main card, and footer fade in sequentially
on page load for visual rhythm."
```

---

## Task 8: Add Interactive Class to Relationship Network Card

**Files:**
- Modify: `standalone_ui/static/js/demo_player.js:92-93` (renderRelationshipNetworkIfPresent)

**Step 1: Update relationship network card to use interactive-card class**

In `standalone_ui/static/js/demo_player.js`, find line 92-93:

```javascript
    const section = document.createElement('div');
    section.className = 'bg-white rounded-lg shadow-md p-6';
```

Replace with:

```javascript
    const section = document.createElement('div');
    section.className = 'bg-white rounded-lg shadow-md p-6 interactive-card stagger-fade-in stagger-delay-5';
```

**Step 2: Verify the file is syntactically correct**

Run: `node --check standalone_ui/static/js/demo_player.js`
Expected: No output (syntax valid)

**Step 3: Commit**

```bash
git add standalone_ui/static/js/demo_player.js
git commit -m "feat(ui): add interactive + stagger to relationship network card

Network visualization card now has hover lift and
cascades in with the other result cards."
```

---

## Task 9: Manual Testing

**Step 1: Start a local server**

Run: `cd standalone_ui && python3 -m http.server 8000`

**Step 2: Open browser and test interactions**

Open: `http://localhost:8000`

Test checklist:
- [ ] Page loads with staggered header → main → footer animation
- [ ] Click "Start" in execution flow to run demo
- [ ] Timeline items lift and shadow on hover
- [ ] Tool badges darken on hover
- [ ] Agent badges darken on hover
- [ ] Details summary highlights on hover
- [ ] DAG reset/maximize buttons scale on hover
- [ ] DAG buttons press down on click
- [ ] When demo completes, result cards cascade in with stagger
- [ ] Result cards lift and shadow on hover
- [ ] Table rows highlight on hover
- [ ] Graph containers fade in after card appears
- [ ] Connection status pill gets border glow on hover

**Step 3: Stop the server**

Press: Ctrl+C

---

## Task 10: Final Commit

**Step 1: Verify all changes are committed**

Run: `git status`
Expected: nothing to commit, working tree clean

**Step 2: View commit history**

Run: `git log --oneline -10`
Expected: Shows all commits from this implementation

---

## Summary

After completing all tasks, the standalone UI will have:

1. **Hover feedback** on all interactive elements (cards, buttons, badges, table rows, pills)
2. **Timeline mini-card treatment** with lift and shadow on hover
3. **Staggered cascade animations** for page load and results reveal
4. **Graph delayed fade-in** after parent card appears

All changes are pure CSS + minimal JS class application. No new dependencies.
