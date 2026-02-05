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

    logger.info('init pattern graph', {
        nodes: elements.nodes.length,
        edges: elements.edges.length
    });

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
