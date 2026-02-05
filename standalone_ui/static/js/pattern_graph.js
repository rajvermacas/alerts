import { createLogger } from './logger.js';
import { showToast } from './toast.js';

const logger = createLogger('pattern_graph');

function requireObject(value, path) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error(`pattern_graph: ${path} (object) is required`);
    }
    return value;
}

function requireArray(value, path) {
    if (!Array.isArray(value)) {
        throw new Error(`pattern_graph: ${path} (array) is required`);
    }
    return value;
}

function requireNonEmptyString(value, path) {
    if (typeof value !== 'string' || value.trim().length === 0) {
        throw new Error(`pattern_graph: ${path} (non-empty string) is required`);
    }
    return value;
}

function requireNumber(value, path) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        throw new Error(`pattern_graph: ${path} (number) is required`);
    }
    return value;
}

function requireBoolean(value, path) {
    if (typeof value !== 'boolean') {
        throw new Error(`pattern_graph: ${path} (boolean) is required`);
    }
    return value;
}

function requireEnum(value, path, allowed) {
    const str = requireNonEmptyString(value, path);
    if (!allowed.includes(str)) {
        throw new Error(`pattern_graph: ${path} must be one of: ${allowed.join(', ')}`);
    }
    return str;
}

function requireCytoscape() {
    if (typeof window.cytoscape !== 'function') {
        throw new Error('pattern_graph: cytoscape not available (CDN failed to load)');
    }
    return window.cytoscape;
}

function requireContainer(containerId) {
    const id = requireNonEmptyString(containerId, 'containerId');
    const el = document.getElementById(id);
    if (!el) {
        throw new Error(`pattern_graph: missing container #${id}`);
    }
    return el;
}

function computeRenderProfile(nodeCount) {
    const count = requireNumber(nodeCount, 'nodeCount');
    if (!Number.isInteger(count) || count <= 0) {
        throw new Error('pattern_graph: nodeCount must be a positive integer');
    }

    if (count <= 8) {
        return {
            sizePx: { small: 52, medium: 72, large: 92 },
            nodeFontPx: 12,
            edgeFontPx: 11,
            edgeWidthMin: 3,
            edgeWidthMax: 7,
            nodeLabelMaxWidthPx: 140,
            fitPaddingPx: 16,
            minZoom: 0.05,
            maxZoom: 4.0,
        };
    }

    if (count <= 20) {
        return {
            sizePx: { small: 42, medium: 60, large: 78 },
            nodeFontPx: 11,
            edgeFontPx: 10,
            edgeWidthMin: 2.5,
            edgeWidthMax: 6,
            nodeLabelMaxWidthPx: 120,
            fitPaddingPx: 20,
            minZoom: 0.05,
            maxZoom: 4.0,
        };
    }

    return {
        sizePx: { small: 30, medium: 45, large: 60 },
        nodeFontPx: 10,
        edgeFontPx: 9,
        edgeWidthMin: 2,
        edgeWidthMax: 5,
        nodeLabelMaxWidthPx: 90,
        fitPaddingPx: 28,
        minZoom: 0.05,
        maxZoom: 4.0,
    };
}

function getNodeSize(sizeToken, profile) {
    const token = requireEnum(sizeToken, 'node.size', ['small', 'medium', 'large']);
    const size = profile.sizePx[token];
    if (typeof size !== 'number' || Number.isNaN(size)) {
        throw new Error(`pattern_graph: missing sizePx mapping for '${token}'`);
    }
    return size;
}

function computeEdgeWidth(weight, maxWeight, profile) {
    const w = requireNumber(weight, 'edge.weight');
    if (w <= 0) {
        throw new Error('pattern_graph: edge.weight must be > 0');
    }

    const max = requireNumber(maxWeight, 'maxWeight');
    if (max <= 0) {
        throw new Error('pattern_graph: maxWeight must be > 0');
    }

    const minWidth = requireNumber(profile.edgeWidthMin, 'profile.edgeWidthMin');
    const maxWidth = requireNumber(profile.edgeWidthMax, 'profile.edgeWidthMax');
    if (maxWidth < minWidth) {
        throw new Error('pattern_graph: profile.edgeWidthMax must be >= profile.edgeWidthMin');
    }

    const ratio = Math.min(1, w / max);
    return minWidth + ratio * (maxWidth - minWidth);
}

function validatePatternGraphSpec(patternGraphSpec) {
    const spec = requireObject(patternGraphSpec, 'patternGraphSpec');
    const nodes = requireArray(spec.nodes, 'patternGraphSpec.nodes');
    const edges = requireArray(spec.edges, 'patternGraphSpec.edges');

    if (nodes.length === 0) {
        throw new Error('pattern_graph: patternGraphSpec.nodes must be non-empty');
    }
    if (edges.length === 0) {
        throw new Error('pattern_graph: patternGraphSpec.edges must be non-empty');
    }

    nodes.forEach((n, idx) => {
        const node = requireObject(n, `patternGraphSpec.nodes[${idx}]`);
        requireNonEmptyString(node.id, `patternGraphSpec.nodes[${idx}].id`);
        requireNonEmptyString(node.label, `patternGraphSpec.nodes[${idx}].label`);
        requireNonEmptyString(node.type, `patternGraphSpec.nodes[${idx}].type`);
        requireEnum(node.size, `patternGraphSpec.nodes[${idx}].size`, ['small', 'medium', 'large']);
        requireBoolean(node.isAnomaly, `patternGraphSpec.nodes[${idx}].isAnomaly`);
        requireBoolean(node.isBaseline, `patternGraphSpec.nodes[${idx}].isBaseline`);
        requireNumber(node.volume, `patternGraphSpec.nodes[${idx}].volume`);
        if (node.volume < 0) {
            throw new Error(`pattern_graph: patternGraphSpec.nodes[${idx}].volume must be >= 0`);
        }
    });

    edges.forEach((e, idx) => {
        const edge = requireObject(e, `patternGraphSpec.edges[${idx}]`);
        requireNonEmptyString(edge.id, `patternGraphSpec.edges[${idx}].id`);
        requireNonEmptyString(edge.source, `patternGraphSpec.edges[${idx}].source`);
        requireNonEmptyString(edge.target, `patternGraphSpec.edges[${idx}].target`);
        requireNonEmptyString(edge.label, `patternGraphSpec.edges[${idx}].label`);
        requireNumber(edge.weight, `patternGraphSpec.edges[${idx}].weight`);
        if (edge.weight <= 0) {
            throw new Error(`pattern_graph: patternGraphSpec.edges[${idx}].weight must be > 0`);
        }
        requireBoolean(edge.isAnomaly, `patternGraphSpec.edges[${idx}].isAnomaly`);
    });

    return { spec, nodes, edges };
}

function toCytoscapeElements(spec, profile) {
    const maxWeight = Math.max(...spec.edges.map((e) => e.weight));
    if (typeof maxWeight !== 'number' || Number.isNaN(maxWeight) || maxWeight <= 0) {
        throw new Error('pattern_graph: computed maxWeight must be > 0');
    }

    const nodes = spec.nodes.map((n) => ({
        data: {
            id: n.id,
            label: n.label,
            type: n.type,
            size: getNodeSize(n.size, profile),
            isAnomaly: n.isAnomaly,
            isBaseline: n.isBaseline,
            volume: n.volume,
        },
    }));
    const edges = spec.edges.map((e) => ({
        data: {
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.label,
            weight: e.weight,
            isAnomaly: e.isAnomaly,
            width: computeEdgeWidth(e.weight, maxWeight, profile),
        },
    }));
    return { nodes, edges };
}

function buildCytoscapeStyle(profile) {
    return [
        {
            selector: 'node',
            style: {
                'background-color': '#6B7280',
                'label': 'data(label)',
                'text-valign': 'bottom',
                'text-halign': 'center',
                'font-size': `${profile.nodeFontPx}px`,
                'text-margin-y': '5px',
                'width': 'data(size)',
                'height': 'data(size)',
                'text-wrap': 'wrap',
                'text-max-width': `${profile.nodeLabelMaxWidthPx}px`,
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
                'width': 'data(width)',
                'line-color': '#9CA3AF',
                'target-arrow-color': '#9CA3AF',
                'target-arrow-shape': 'triangle',
                'curve-style': 'bezier',
                'label': 'data(label)',
                'font-size': `${profile.edgeFontPx}px`,
                'text-rotation': 'autorotate',
                'text-margin-y': '-10px',
            },
        },
        {
            selector: 'edge[?isAnomaly]',
            style: {
                'line-color': '#DC2626',
                'target-arrow-color': '#DC2626',
                'line-style': 'dashed',
            },
        },
    ];
}

function hasTraderNode(patternGraphSpec) {
    return patternGraphSpec.nodes.some((n) => n.type === 'trader');
}

function getTraderRootSelector(patternGraphSpec) {
    const traderNodes = patternGraphSpec.nodes.filter((n) => n.type === 'trader');
    if (traderNodes.length === 0) {
        return null;
    }
    if (traderNodes.length !== 1) {
        throw new Error(`pattern_graph: expected exactly 1 trader node, found ${traderNodes.length}`);
    }
    return `#${requireNonEmptyString(traderNodes[0].id, 'patternGraphSpec.nodes[trader].id')}`;
}

function buildCytoscapeLayout(patternGraphSpec, profile) {
    const traderCentered = hasTraderNode(patternGraphSpec) && patternGraphSpec.nodes.length <= 20;
    if (traderCentered) {
        const root = getTraderRootSelector(patternGraphSpec);
        if (!root) {
            throw new Error('pattern_graph: traderCentered requires a trader root');
        }
        return {
            name: 'breadthfirst',
            roots: root,
            directed: true,
            orientation: 'horizontal',
            circle: false,
            fit: false,
            padding: profile.fitPaddingPx,
            spacingFactor: 1.35,
        };
    }

    return {
        name: 'cose',
        idealEdgeLength: 90,
        nodeOverlap: 20,
        nodeRepulsion: 600000,
        edgeElasticity: 100,
        gravity: 60,
        numIter: 900,
        fit: false,
        padding: profile.fitPaddingPx,
        randomize: false,
    };
}

function clamp(num, min, max) {
    if (min > max) {
        throw new Error('pattern_graph: clamp(min,max) requires min <= max');
    }
    return Math.max(min, Math.min(max, num));
}

function applyInitialViewport(cy, profile) {
    cy.resize();
    cy.fit(cy.elements(), profile.fitPaddingPx);

    const minZoom = requireNumber(profile.minZoom, 'profile.minZoom');
    const maxZoom = requireNumber(profile.maxZoom, 'profile.maxZoom');
    const current = cy.zoom();
    const clamped = clamp(current, minZoom, maxZoom);
    if (clamped !== current) {
        cy.zoom({
            level: clamped,
            renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
        });
    }
}

function bindCtrlWheelZoom(container, cy, profile) {
    const minZoom = requireNumber(profile.minZoom, 'profile.minZoom');
    const maxZoom = requireNumber(profile.maxZoom, 'profile.maxZoom');

    container.addEventListener('wheel', (evt) => {
        if (!(evt.ctrlKey || evt.metaKey)) {
            return;
        }

        evt.preventDefault();
        evt.stopPropagation();

        const rect = container.getBoundingClientRect();
        const cursor = {
            x: evt.clientX - rect.left,
            y: evt.clientY - rect.top,
        };

        const delta = clamp(evt.deltaY, -60, 60);
        const zoomMultiplier = 1 - delta * 0.0015;
        const next = clamp(cy.zoom() * zoomMultiplier, minZoom, maxZoom);

        cy.zoom({
            level: next,
            renderedPosition: cursor,
        });
    }, { passive: false });
}

function createCytoscapeGraph(container, elements, profile) {
    const cytoscape = requireCytoscape();
    return cytoscape({
        container,
        elements,
        style: buildCytoscapeStyle(profile),
        layout: { name: 'preset' },
        userZoomingEnabled: true,
        minZoom: profile.minZoom,
        maxZoom: profile.maxZoom,
    });
}

function bindInitialLayoutAndViewport(container, cy, spec, profile, initialRect) {
    const rect = requireObject(initialRect, 'initialRect');
    const containerReady = rect.width >= 50 && rect.height >= 50;
    let needsInitialViewport = !containerReady;

    const layout = cy.layout(buildCytoscapeLayout(spec, profile));
    cy.one('layoutstop', () => {
        if (needsInitialViewport) {
            logger.warn('pattern graph layout completed but container too small; waiting for resize', {
                containerWidthPx: Math.round(rect.width),
                containerHeightPx: Math.round(rect.height),
            });
            return;
        }
        window.requestAnimationFrame(() => applyInitialViewport(cy, profile));
    });
    layout.run();

    bindCtrlWheelZoom(container, cy, profile);

    if (typeof window.ResizeObserver !== 'function') {
        logger.warn('ResizeObserver not available; pattern graph will not auto-resize');
        return;
    }

    const ro = new window.ResizeObserver(() => {
        cy.resize();
        if (!needsInitialViewport) {
            return;
        }

        const nextRect = container.getBoundingClientRect();
        if (nextRect.width < 50 || nextRect.height < 50) {
            return;
        }

        needsInitialViewport = false;
        window.requestAnimationFrame(() => applyInitialViewport(cy, profile));
    });
    ro.observe(container);
    cy.on('destroy', () => ro.disconnect());
}

function bindNodeToast(cy) {
    cy.on('tap', 'node', (evt) => {
        const data = evt.target.data();
        const volume = requireNumber(data.volume, 'node.data(volume)');
        const info = volume > 0
            ? `${data.label}\nVolume: ${volume.toLocaleString()}`
            : data.label;
        showToast(info, 'info');
    });
}

export function initPatternGraph(containerId, patternGraphSpec) {
    const container = requireContainer(containerId);
    const { spec } = validatePatternGraphSpec(patternGraphSpec);
    const profile = computeRenderProfile(spec.nodes.length);
    const elements = toCytoscapeElements(spec, profile);
    const rect = container.getBoundingClientRect();

    logger.info('init pattern graph', {
        containerId,
        nodes: elements.nodes.length,
        edges: elements.edges.length,
        nodeFontPx: profile.nodeFontPx,
        edgeFontPx: profile.edgeFontPx,
        fitPaddingPx: profile.fitPaddingPx,
        containerWidthPx: Math.round(rect.width),
        containerHeightPx: Math.round(rect.height),
    });

    const cy = createCytoscapeGraph(container, elements, profile);
    bindInitialLayoutAndViewport(container, cy, spec, profile, rect);
    bindNodeToast(cy);

    logger.info('pattern graph initialized', {
        layout: hasTraderNode(spec) && spec.nodes.length <= 20 ? 'breadthfirst' : 'cose',
        minZoom: profile.minZoom,
        maxZoom: profile.maxZoom,
    });
    return cy;
}
