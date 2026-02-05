import { createLogger } from './logger.js';

const logger = createLogger('cards_renderer');

function requireElementById(id) {
    const el = document.getElementById(id);
    if (!el) {
        throw new Error(`cards_renderer: missing required element #${id}`);
    }
    return el;
}

function requireNonEmptyString(value, path) {
    if (typeof value !== 'string' || value.trim().length === 0) {
        throw new Error(`cards_renderer: ${path} (non-empty string) is required`);
    }
    return value;
}

function requireNumber(value, path) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        throw new Error(`cards_renderer: ${path} (number) is required`);
    }
    return value;
}

function requireArray(value, path) {
    if (!Array.isArray(value)) {
        throw new Error(`cards_renderer: ${path} (array) is required`);
    }
    return value;
}

function requireObject(value, path) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error(`cards_renderer: ${path} (object) is required`);
    }
    return value;
}

function requireEnum(value, path, allowed) {
    const str = requireNonEmptyString(value, path);
    if (!allowed.includes(str)) {
        throw new Error(`cards_renderer: ${path} must be one of: ${allowed.join(', ')}`);
    }
    return str;
}

function isPrimitive(value) {
    return value === null || ['string', 'number', 'boolean'].includes(typeof value);
}

function renderPrimitive(value) {
    const p = document.createElement('p');
    p.className = 'text-gray-700 text-sm whitespace-pre-wrap';
    if (value === null) {
        p.textContent = 'null';
        return p;
    }
    p.textContent = String(value);
    return p;
}

function renderBulletList(items) {
    const ul = document.createElement('ul');
    ul.className = 'list-disc ml-5 space-y-1 text-sm text-gray-700';
    items.forEach((item) => {
        const li = document.createElement('li');
        li.textContent = String(item);
        ul.appendChild(li);
    });
    return ul;
}

function renderJsonBlock(value) {
    const pre = document.createElement('pre');
    pre.className = 'bg-gray-900 text-gray-200 p-4 rounded-lg text-xs overflow-x-auto';
    pre.textContent = JSON.stringify(value, null, 2);
    return pre;
}

function renderTable(rows) {
    if (rows.length === 0) {
        throw new Error('cards_renderer: array-of-objects table must be non-empty');
    }

    const keys = Object.keys(rows[0]);
    if (keys.length === 0) {
        throw new Error('cards_renderer: array-of-objects rows must have at least 1 column');
    }

    rows.forEach((row, i) => {
        const rowKeys = Object.keys(row);
        const same = rowKeys.length === keys.length && rowKeys.every((k) => keys.includes(k));
        if (!same) {
            throw new Error(`cards_renderer: table rows must have consistent keys (row ${i})`);
        }
    });

    const wrapper = document.createElement('div');
    wrapper.className = 'overflow-x-auto';

    const table = document.createElement('table');
    table.className = 'min-w-full text-sm';

    const thead = document.createElement('thead');
    thead.className = 'bg-gray-50';
    const hr = document.createElement('tr');
    keys.forEach((k) => {
        const th = document.createElement('th');
        th.className = 'px-4 py-2 text-left font-medium text-gray-700';
        th.textContent = k;
        hr.appendChild(th);
    });
    thead.appendChild(hr);

    const tbody = document.createElement('tbody');
    tbody.className = 'divide-y divide-gray-200';
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

    table.appendChild(thead);
    table.appendChild(tbody);
    wrapper.appendChild(table);
    return wrapper;
}

function isTypedCard(value) {
    return value && typeof value === 'object' && !Array.isArray(value) && typeof value._type === 'string';
}

function renderConfidenceScoresCard(value) {
    const obj = requireObject(value, 'confidence_scores card');
    const items = requireArray(obj.items, 'confidence_scores.items');

    const barColors = {
        red: 'bg-red-500',
        green: 'bg-gray-700',
        blue: 'bg-red-500',
        yellow: 'bg-gray-500',
        indigo: 'bg-gray-600',
        purple: 'bg-gray-600',
        gray: 'bg-gray-500',
        black: 'bg-black',
    };

    const container = document.createElement('div');
    container.className = 'space-y-4';

    items.forEach((it, idx) => {
        const item = requireObject(it, `confidence_scores.items[${idx}]`);
        const label = requireNonEmptyString(item.label, `confidence_scores.items[${idx}].label`);
        const valueNum = requireNumber(item.value, `confidence_scores.items[${idx}].value`);
        if (valueNum < 0 || valueNum > 100) {
            throw new Error(`cards_renderer: confidence_scores.items[${idx}].value must be 0..100`);
        }
        const color = requireEnum(item.barColor, `confidence_scores.items[${idx}].barColor`, Object.keys(barColors));
        const barClass = barColors[color];
        if (!barClass) {
            throw new Error(`cards_renderer: unsupported barColor '${color}'`);
        }

        const row = document.createElement('div');
        row.innerHTML = `
            <div class="flex justify-between mb-1">
                <span class="text-sm font-medium text-gray-700">${label}</span>
                <span class="text-sm font-bold text-gray-900">${valueNum}%</span>
            </div>
            <div class="w-full bg-gray-200 rounded-full h-3">
                <div class="${barClass} h-3 rounded-full transition-all duration-500" style="width: ${valueNum}%"></div>
            </div>
        `;
        container.appendChild(row);
    });

    return container;
}

function renderCardValue(value) {
    if (isTypedCard(value)) {
        const type = requireNonEmptyString(value._type, 'card._type');
        if (type === 'confidence_scores') {
            return renderConfidenceScoresCard(value);
        }
        throw new Error(`cards_renderer: unsupported card _type '${type}'`);
    }

    if (isPrimitive(value)) {
        return renderPrimitive(value);
    }

    if (Array.isArray(value)) {
        const allPrimitives = value.every((v) => isPrimitive(v));
        if (allPrimitives) {
            return renderBulletList(value);
        }

        const allObjects = value.every((v) => v && typeof v === 'object' && !Array.isArray(v));
        if (allObjects) {
            return renderTable(value);
        }

        return renderJsonBlock(value);
    }

    if (value && typeof value === 'object') {
        return renderJsonBlock(value);
    }

    throw new Error('cards_renderer: unsupported card value type');
}

export function renderCardsIntoResults(cards) {
    const results = requireElementById('results-section');
    const obj = cards;
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
        throw new Error('cards_renderer: cards (object map) is required');
    }

    Object.entries(obj).forEach(([title, value]) => {
        requireNonEmptyString(title, 'card title');

        const card = document.createElement('div');
        const staggerIndex = Object.keys(obj).indexOf(title);
        const delayClass = staggerIndex < 8 ? `stagger-delay-${staggerIndex + 1}` : 'stagger-delay-8';
        card.className = `bg-white rounded-lg shadow-md p-6 interactive-card stagger-fade-in ${delayClass}`;

        const h3 = document.createElement('h3');
        h3.className = 'text-lg font-semibold text-gray-900 mb-4';
        h3.textContent = title;
        card.appendChild(h3);

        card.appendChild(renderCardValue(value));
        results.appendChild(card);
    });

    logger.info('rendered cards', { count: Object.keys(obj).length });
}

function createVisibleGraphContainer(cardKey, patternGraph) {
    const graphId = `pattern-graph-${cardKey}`;
    const wrapper = document.createElement('div');
    wrapper.className = 'mt-4';

    const graphContainer = document.createElement('div');
    graphContainer.id = graphId;
    graphContainer.className = 'mt-4 h-96 border border-gray-200 rounded-lg bg-gray-50 graph-fade-in';
    graphContainer.dataset.patternGraph = JSON.stringify(patternGraph);

    wrapper.appendChild(graphContainer);

    setTimeout(() => {
        window.dispatchEvent(new CustomEvent('initPatternGraph', {
            detail: { containerId: graphId, spec: patternGraph }
        }));
    }, 0);

    return wrapper;
}

function renderAnalysisCard(key, cardData, staggerIndex) {
    const card = document.createElement('div');
    const delayClass = staggerIndex < 8 ? `stagger-delay-${staggerIndex + 1}` : 'stagger-delay-8';
    card.className = `bg-white rounded-lg shadow-md p-6 interactive-card stagger-fade-in ${delayClass}`;

    const h3 = document.createElement('h3');
    h3.className = 'text-lg font-semibold text-gray-900 mb-3';
    h3.textContent = cardData.title;
    card.appendChild(h3);

    const summary = document.createElement('p');
    summary.className = 'text-gray-700 text-sm';
    summary.textContent = cardData.summary;
    card.appendChild(summary);

    if (cardData.patternGraph) {
        card.appendChild(createVisibleGraphContainer(key, cardData.patternGraph));
    }

    return card;
}

export function renderAnalysisCards(analysisCards) {
    const results = requireElementById('results-section');
    if (!analysisCards || typeof analysisCards !== 'object' || Array.isArray(analysisCards)) {
        throw new Error('cards_renderer: analysisCards (object) is required');
    }

    const order = ['newsAnalysis', 'pnlAnalysis', 'clientRiskAnalysis', 'traderHistoryAnalysis'];

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

    logger.info('rendered analysis cards', { count: order.length });
}
