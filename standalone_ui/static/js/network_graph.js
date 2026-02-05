import { createLogger } from './logger.js';
import { showToast } from './toast.js';

const logger = createLogger('network_graph');

function requireCytoscape() {
    if (typeof window.cytoscape !== 'function') {
        throw new Error('network_graph: cytoscape not available (CDN failed to load)');
    }
    return window.cytoscape;
}

function requireContainer(containerId) {
    const el = document.getElementById(containerId);
    if (!el) {
        throw new Error(`network_graph: missing container #${containerId}`);
    }
    return el;
}

function toCytoscapeElements(spec) {
    const nodes = spec.nodes.map((n) => ({
        data: { id: n.id, label: n.id, owner: n.owner, type: n.type, flagged: n.flagged },
    }));
    const edges = spec.edges.map((e) => ({
        data: { id: e.id, source: e.source, target: e.target, type: e.type, label: e.label, suspicious: e.suspicious },
    }));
    return { nodes, edges };
}

export function initRelationshipNetwork(containerId, relationshipNetworkSpec) {
    const container = requireContainer(containerId);
    const cytoscape = requireCytoscape();
    const elements = toCytoscapeElements(relationshipNetworkSpec);

    logger.info('init', { nodes: elements.nodes.length, edges: elements.edges.length });

    const cy = cytoscape({
        container,
        elements,
        style: [
            {
                selector: 'node',
                style: {
                    'background-color': '#4B5563',
                    'label': 'data(label)',
                    'text-valign': 'bottom',
                    'text-halign': 'center',
                    'font-size': '10px',
                    'text-margin-y': '5px',
                    'width': '40px',
                    'height': '40px',
                },
            },
            {
                selector: 'node[?flagged]',
                style: {
                    'background-color': '#DC2626',
                    'border-width': '3px',
                    'border-color': '#991B1B',
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
                    'font-size': '8px',
                    'text-rotation': 'autorotate',
                    'text-margin-y': '-10px',
                },
            },
            {
                selector: 'edge[?suspicious]',
                style: {
                    'line-color': '#DC2626',
                    'target-arrow-color': '#DC2626',
                    'width': 3,
                },
            },
            {
                selector: 'edge[type="ownership"]',
                style: {
                    'line-style': 'dashed',
                    'line-color': '#6B7280',
                    'target-arrow-color': '#6B7280',
                },
            },
        ],
        layout: {
            name: 'cose',
            idealEdgeLength: 100,
            nodeOverlap: 20,
            refresh: 20,
            fit: true,
            padding: 30,
            randomize: false,
            componentSpacing: 100,
            nodeRepulsion: 400000,
            edgeElasticity: 100,
            gravity: 80,
            numIter: 800,
        },
    });

    cy.fit();

    cy.on('tap', 'node', (evt) => {
        const data = evt.target.data();
        showToast(`Account: ${data.id}\nOwner: ${data.owner}\nType: ${data.type}`, 'info');
    });

    return cy;
}

