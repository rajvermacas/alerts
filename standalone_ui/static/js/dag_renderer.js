import { createLogger } from './logger.js';
import { ToolResultModal } from './modal.js';

const logger = createLogger('dag_renderer');

function requireElementById(id) {
    const el = document.getElementById(id);
    if (!el) {
        throw new Error(`dag_renderer: missing required element #${id}`);
    }
    return el;
}

function requireCytoscape() {
    if (typeof window.cytoscape !== 'function') {
        throw new Error('dag_renderer: cytoscape not available (CDN failed to load)');
    }
    return window.cytoscape;
}

const STATES = {
    PENDING: 'pending',
    ACTIVE: 'active',
    COMPLETED: 'completed',
    ERROR: 'error',
};

function assertNonEmptyString(value, path) {
    if (typeof value !== 'string' || value.trim().length === 0) {
        throw new Error(`dag_renderer: ${path} (non-empty string) is required`);
    }
    return value;
}

function assertObject(value, path) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error(`dag_renderer: ${path} (object) is required`);
    }
    return value;
}

function assertArray(value, path) {
    if (!Array.isArray(value)) {
        throw new Error(`dag_renderer: ${path} (array) is required`);
    }
    return value;
}

function assertEnum(value, path, allowed) {
    const str = assertNonEmptyString(value, path);
    if (!allowed.includes(str)) {
        throw new Error(`dag_renderer: ${path} must be one of: ${allowed.join(', ')}`);
    }
    return str;
}

function validateExecutionFlow(flowSpec) {
    const flow = assertObject(flowSpec, 'executionFlow');
    const nodes = assertArray(flow.nodes, 'executionFlow.nodes');
    const edges = assertArray(flow.edges, 'executionFlow.edges');

    const allowedKinds = ['start', 'step', 'service', 'evaluation', 'complete'];
    const nodeIds = new Set();

    nodes.forEach((n, idx) => {
        const node = assertObject(n, `executionFlow.nodes[${idx}]`);
        const id = assertNonEmptyString(node.id, `executionFlow.nodes[${idx}].id`);
        if (nodeIds.has(id)) {
            throw new Error(`dag_renderer: duplicate executionFlow node id '${id}'`);
        }
        nodeIds.add(id);
        assertNonEmptyString(node.label, `executionFlow.nodes[${idx}].label`);
        assertEnum(node.kind, `executionFlow.nodes[${idx}].kind`, allowedKinds);
    });

    edges.forEach((e, idx) => {
        const edge = assertObject(e, `executionFlow.edges[${idx}]`);
        assertNonEmptyString(edge.id, `executionFlow.edges[${idx}].id`);
        const source = assertNonEmptyString(edge.source, `executionFlow.edges[${idx}].source`);
        const target = assertNonEmptyString(edge.target, `executionFlow.edges[${idx}].target`);
        if (!nodeIds.has(source)) {
            throw new Error(`dag_renderer: edge source '${source}' not found in executionFlow.nodes`);
        }
        if (!nodeIds.has(target)) {
            throw new Error(`dag_renderer: edge target '${target}' not found in executionFlow.nodes`);
        }
    });

    return flow;
}

export class DAGRenderer {
    constructor(executionFlowSpec) {
        this.container = requireElementById('dag-container');
        this.cy = null;
        this._executionFlow = validateExecutionFlow(executionFlowSpec);
        this.nodeResults = new Map(); // nodeId -> { title, outputSummary, durationSeconds }
        this.isMaximized = false;
        this.overlay = null;
        this._placeholder = null;
        this._preMaximizeInlineStyle = null;
        this.modal = new ToolResultModal();
        this._initGraph(this._executionFlow);
        this._bindControls();
        logger.info('initialized');
    }

    handleEvent(eventInfo) {
        const event = assertObject(eventInfo, 'eventInfo');
        assertNonEmptyString(event.type, 'eventInfo.type');

        logger.debug('handleEvent', { type: event.type, dagUpdates: Boolean(event.dagUpdates) });

        if (event.dagUpdates !== undefined) {
            this._applyDagUpdates(event.dagUpdates);
        }

        if (event.dagNodeId && event.outputSummary) {
            this._storeNodeResult(event.dagNodeId, event.toolName || event.dagNodeId, event.outputSummary, event.durationSeconds);
        }
    }

    resetLayout() {
        if (!this.cy) {
            throw new Error('dag_renderer: cy not initialized');
        }
        this.cy.layout(this._layoutConfig()).run();
        this.cy.fit(undefined, 30);
        logger.info('reset layout');
    }

    toggleMaximize() {
        if (this.isMaximized) {
            this._minimizeGraph();
            return;
        }
        this._maximizeGraph();
    }

    _bindControls() {
        const resetBtn = requireElementById('dag-reset-btn');
        resetBtn.addEventListener('click', () => this.resetLayout());

        const maximizeBtn = requireElementById('dag-maximize-btn');
        maximizeBtn.addEventListener('click', () => this.toggleMaximize());

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isMaximized) {
                this.toggleMaximize();
            }
        });
    }

    _initGraph(executionFlowSpec) {
        const cytoscape = requireCytoscape();
        const nodes = executionFlowSpec.nodes.map((n) => ({
            data: { id: n.id, label: n.label, kind: n.kind },
            classes: `node kind-${n.kind} ${STATES.PENDING}`,
        }));
        const edges = executionFlowSpec.edges.map((e) => ({
            data: { id: e.id, source: e.source, target: e.target },
            classes: `edge ${STATES.PENDING}`,
        }));

        this.cy = cytoscape({
            container: this.container,
            elements: { nodes, edges },
            style: this._styles(),
            layout: this._layoutConfig(),
            userZoomingEnabled: true,
            userPanningEnabled: true,
            boxSelectionEnabled: false,
            wheelSensitivity: 0.12,
            minZoom: 0.5,
            maxZoom: 3,
        });

        this.cy.on('tap', 'node', (evt) => this._handleNodeClick(evt.target.data()));

        logger.info('graph initialized');
    }

    _handleNodeClick(nodeData) {
        if (!nodeData) {
            throw new Error('dag_renderer: nodeData is required');
        }
        const id = nodeData.id;
        if (!id) {
            throw new Error('dag_renderer: nodeData.id is required');
        }

        const result = this.nodeResults.get(id);
        if (!result) {
            return;
        }
        this.modal.show(result.title, result.outputSummary, result.durationSeconds);
    }

    _styles() {
        return [
            {
                selector: 'node',
                style: {
                    'label': 'data(label)',
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'font-size': '10px',
                    'color': '#111827',
                    'background-color': '#E5E7EB',
                    'border-width': 1,
                    'border-color': '#9CA3AF',
                    'text-wrap': 'wrap',
                    'text-max-width': 120,
                    'width': 120,
                    'height': 54,
                    'shape': 'round-rectangle',
                },
            },
            { selector: 'edge', style: { 'width': 2, 'line-color': '#CBD5E1', 'target-arrow-shape': 'triangle', 'target-arrow-color': '#CBD5E1', 'curve-style': 'bezier' } },
            { selector: 'edge.pending', style: { 'line-color': '#CBD5E1', 'target-arrow-color': '#CBD5E1' } },
            { selector: 'edge.active', style: { 'line-color': '#2563EB', 'target-arrow-color': '#2563EB' } },
            { selector: 'edge.completed', style: { 'line-color': '#16A34A', 'target-arrow-color': '#16A34A' } },
            { selector: 'edge.error', style: { 'line-color': '#DC2626', 'target-arrow-color': '#DC2626' } },
            { selector: '.pending', style: { 'background-color': '#E5E7EB', 'border-color': '#9CA3AF' } },
            { selector: '.active', style: { 'background-color': '#DBEAFE', 'border-color': '#2563EB', 'border-width': 2 } },
            { selector: '.completed', style: { 'background-color': '#DCFCE7', 'border-color': '#16A34A', 'border-width': 2 } },
            { selector: '.error', style: { 'background-color': '#FEE2E2', 'border-color': '#DC2626', 'border-width': 2 } },
            { selector: '.kind-service', style: { 'width': 150, 'height': 64, 'font-size': '9px', 'text-max-width': 140 } },
            { selector: '.kind-start', style: { 'shape': 'ellipse', 'width': 88, 'height': 44, 'font-size': '10px', 'text-max-width': 78 } },
            { selector: '.kind-complete', style: { 'shape': 'ellipse', 'width': 96, 'height': 44, 'font-size': '10px', 'text-max-width': 86 } },
            { selector: '.kind-evaluation', style: { 'shape': 'diamond', 'width': 72, 'height': 72, 'font-size': '9px', 'text-max-width': 66 } },
        ];
    }

    _layoutConfig() {
        return {
            name: 'dagre',
            rankDir: 'LR',
            nodeSep: 34,
            rankSep: 84,
            edgeSep: 10,
            padding: 20,
        };
    }

    _setNodeState(nodeId, state) {
        if (!this.cy) {
            throw new Error('dag_renderer: cy not initialized');
        }
        const node = this.cy.$(`#${nodeId}`);
        if (node.length === 0) {
            throw new Error(`dag_renderer: node '${nodeId}' not found`);
        }
        node.removeClass('pending active completed error');
        node.addClass(state);
        this._updateEdgeStates();
    }

    _updateEdgeStates() {
        if (!this.cy) {
            throw new Error('dag_renderer: cy not initialized');
        }

        this.cy.edges().forEach((edge) => {
            const sourceId = edge.data('source');
            const targetId = edge.data('target');
            const source = this.cy.$(`#${sourceId}`);
            const target = this.cy.$(`#${targetId}`);

            const state = this._deriveEdgeState(source, target);
            edge.removeClass('pending active completed error');
            edge.addClass(state);
        });
    }

    _deriveEdgeState(source, target) {
        const sourceState = this._nodeState(source);
        const targetState = this._nodeState(target);

        if (sourceState === STATES.ERROR || targetState === STATES.ERROR) {
            return STATES.ERROR;
        }
        if (sourceState === STATES.COMPLETED && targetState === STATES.COMPLETED) {
            return STATES.COMPLETED;
        }
        if (sourceState === STATES.ACTIVE || targetState === STATES.ACTIVE) {
            return STATES.ACTIVE;
        }
        return STATES.PENDING;
    }

    _nodeState(node) {
        if (node.hasClass(STATES.ERROR)) return STATES.ERROR;
        if (node.hasClass(STATES.COMPLETED)) return STATES.COMPLETED;
        if (node.hasClass(STATES.ACTIVE)) return STATES.ACTIVE;
        return STATES.PENDING;
    }

    _applyDagUpdates(updates) {
        const list = assertArray(updates, 'eventInfo.dagUpdates');
        list.forEach((u, idx) => {
            const update = assertObject(u, `eventInfo.dagUpdates[${idx}]`);
            const nodeId = assertNonEmptyString(update.nodeId, `eventInfo.dagUpdates[${idx}].nodeId`);
            const state = assertEnum(update.state, `eventInfo.dagUpdates[${idx}].state`, [
                STATES.PENDING,
                STATES.ACTIVE,
                STATES.COMPLETED,
                STATES.ERROR,
            ]);
            this._setNodeState(nodeId, state);
        });
    }

    _storeNodeResult(nodeId, title, outputSummary, durationSeconds) {
        assertNonEmptyString(nodeId, 'eventInfo.dagNodeId');
        assertNonEmptyString(title, 'eventInfo.title');
        assertNonEmptyString(outputSummary, 'eventInfo.outputSummary');
        if (durationSeconds !== undefined && typeof durationSeconds !== 'number') {
            throw new Error('dag_renderer: eventInfo.durationSeconds (number) is required when provided');
        }

        if (this.cy.$(`#${nodeId}`).length === 0) {
            throw new Error(`dag_renderer: cannot store result for unknown node '${nodeId}'`);
        }

        this.nodeResults.set(nodeId, { title, outputSummary, durationSeconds });
        logger.info('stored node result', { nodeId, title });
    }

    _maximizeGraph() {
        if (this._placeholder) {
            throw new Error('dag_renderer: maximize called while placeholder exists');
        }

        this.overlay = document.createElement('div');
        this.overlay.className = 'dag-maximize-overlay';

        const header = document.createElement('div');
        header.className = 'dag-maximize-header';
        header.innerHTML = `<span class="text-sm font-medium text-gray-700">Execution Flow</span>`;

        const closeBtn = document.createElement('button');
        closeBtn.className = 'dag-minimize-btn';
        closeBtn.innerHTML = '&times;';
        closeBtn.addEventListener('click', () => this.toggleMaximize());
        header.appendChild(closeBtn);

        const content = document.createElement('div');
        content.className = 'dag-maximize-content';

        const parent = this.container.parentElement;
        if (!parent) {
            throw new Error('dag_renderer: dag container has no parent');
        }

        try {
            this._placeholder = document.createElement('div');
            this._placeholder.className = this.container.className;
            this._placeholder.setAttribute('data-dag-placeholder', 'true');
            parent.replaceChild(this._placeholder, this.container);

            this._preMaximizeInlineStyle = {
                height: this.container.style.height,
                minHeight: this.container.style.minHeight,
                width: this.container.style.width,
            };
            this.container.style.height = '100%';
            this.container.style.minHeight = '100%';
            this.container.style.width = '100%';

            content.appendChild(this.container);
        } catch (e) {
            if (this._placeholder && this._placeholder.parentElement) {
                this._placeholder.parentElement.replaceChild(this.container, this._placeholder);
            }
            this._placeholder = null;
            this._preMaximizeInlineStyle = null;
            throw e;
        }

        this.overlay.appendChild(header);
        this.overlay.appendChild(content);
        document.body.appendChild(this.overlay);

        this.isMaximized = true;
        this.cy.resize();
        this.cy.fit(undefined, 30);
        logger.info('maximized');
    }

    _minimizeGraph() {
        if (!this._placeholder || !this._placeholder.parentElement) {
            throw new Error('dag_renderer: missing placeholder for minimize');
        }

        this._placeholder.parentElement.replaceChild(this.container, this._placeholder);
        this._placeholder = null;

        if (!this._preMaximizeInlineStyle) {
            throw new Error('dag_renderer: missing pre-maximize style');
        }
        this.container.style.height = this._preMaximizeInlineStyle.height;
        this.container.style.minHeight = this._preMaximizeInlineStyle.minHeight;
        this.container.style.width = this._preMaximizeInlineStyle.width;
        this._preMaximizeInlineStyle = null;

        if (this.overlay) {
            this.overlay.remove();
        }

        this.overlay = null;
        this.isMaximized = false;
        this.cy.resize();
        this.cy.fit(undefined, 30);
        logger.info('minimized');
    }
}
