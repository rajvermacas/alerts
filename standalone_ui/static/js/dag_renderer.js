import { createLogger } from './logger.js';
import { ToolResultModal } from './modal.js';
import { showToast } from './toast.js';

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

const FADE_DURATION_MS = 300;
const FIT_PADDING_PX = 16;

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
    constructor(executionFlowSpec, onStartClick) {
        if (typeof onStartClick !== 'function') {
            throw new Error('dag_renderer: onStartClick callback (function) is required');
        }
        this.section = requireElementById('dag-section');
        this.container = requireElementById('dag-container');
        this._maximizeBtn = requireElementById('dag-maximize-btn');
        this.cy = null;
        this._executionFlow = validateExecutionFlow(executionFlowSpec);
        this._onStartClick = onStartClick;
        this._playbackStarted = false;
        this._revealedNodes = new Set();
        this._startNodeId = this._findStartNodeId();
        this._startNodeNaturalPosition = null;
        this.nodeResults = new Map(); // nodeId -> { title, outputSummary, durationSeconds }
        this.isMaximized = false;
        this.modal = new ToolResultModal();
        this._initGraph(this._executionFlow);
        this._bindControls();
        this._bindFullscreenEvents();
        this._bindWindowResize();
        logger.info('initialized');
    }

    _bindWindowResize() {
        window.addEventListener('resize', () => {
            try {
                this._resizeAndFitGraph('windowresize');
            } catch (err) {
                logger.error('window resize handling failed', err);
            }
        });
    }

    _findStartNodeId() {
        const startNode = this._executionFlow.nodes.find((n) => n.kind === 'start');
        if (!startNode) {
            throw new Error('dag_renderer: executionFlow must have a node with kind="start"');
        }
        return startNode.id;
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

    _revealNode(nodeId) {
        if (this._revealedNodes.has(nodeId)) {
            return Promise.resolve();
        }

        const node = this.cy.$(`#${nodeId}`);
        if (node.length === 0) {
            throw new Error(`dag_renderer: cannot reveal unknown node '${nodeId}'`);
        }

        this._revealedNodes.add(nodeId);
        logger.debug('revealing node', { nodeId });

        // Reveal incoming edges (only from already-revealed source nodes)
        const incomingEdges = node.incomers('edge').filter((edge) => {
            const sourceId = edge.data('source');
            return this._revealedNodes.has(sourceId);
        });

        // Remove hidden class so edges can receive state updates
        incomingEdges.removeClass('hidden-edge');

        // Animate node and edges fade in
        return new Promise((resolve) => {
            node.animate(
                { style: { opacity: 1 } },
                { duration: FADE_DURATION_MS, easing: 'ease-out' }
            );
            incomingEdges.animate(
                { style: { opacity: 1 } },
                { duration: FADE_DURATION_MS, easing: 'ease-out', complete: resolve }
            );
            // If no incoming edges, resolve after node animation
            if (incomingEdges.length === 0) {
                setTimeout(resolve, FADE_DURATION_MS);
            }
        });
    }

    resetLayout() {
        if (!this.cy) {
            throw new Error('dag_renderer: cy not initialized');
        }
        this.cy.layout(this._layoutConfig()).run();
        this.cy.fit(undefined, FIT_PADDING_PX);
        logger.info('reset layout');
    }

    async toggleMaximize() {
        await this._toggleFullscreen();
    }

    _bindControls() {
        const resetBtn = requireElementById('dag-reset-btn');
        resetBtn.addEventListener('click', () => this.resetLayout());

        this._maximizeBtn.addEventListener('click', () => {
            void this.toggleMaximize().catch((err) => {
                const message = err instanceof Error ? err.message : String(err);
                logger.error('fullscreen toggle failed', err);
                showToast(message, 'error');
            });
        });
    }

    _bindFullscreenEvents() {
        document.addEventListener('fullscreenchange', () => {
            const isFullscreen = document.fullscreenElement === this.section;
            this.isMaximized = isFullscreen;
            this._maximizeBtn.title = isFullscreen ? 'Exit fullscreen' : 'Fullscreen graph';
            this._resizeAndFitGraph('fullscreenchange');
            logger.info('fullscreenchange', {
                active: isFullscreen,
                fullscreenElementTag: document.fullscreenElement ? document.fullscreenElement.tagName : null,
            });
        });
    }

    async _toggleFullscreen() {
        if (typeof this.section.requestFullscreen !== 'function') {
            throw new Error('dag_renderer: Fullscreen API not available (element.requestFullscreen missing)');
        }
        if (typeof document.exitFullscreen !== 'function') {
            throw new Error('dag_renderer: Fullscreen API not available (document.exitFullscreen missing)');
        }

        const current = document.fullscreenElement;
        if (current && current !== this.section) {
            throw new Error('dag_renderer: fullscreen already active on a different element');
        }

        if (!current) {
            logger.info('entering fullscreen');
            await this.section.requestFullscreen();
            return;
        }

        logger.info('exiting fullscreen');
        await document.exitFullscreen();
    }

    _resizeAndFitGraph(reason) {
        if (!this.cy) {
            throw new Error('dag_renderer: cy not initialized');
        }
        if (typeof reason !== 'string' || reason.trim().length === 0) {
            throw new Error('dag_renderer: reason (non-empty string) is required');
        }

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                logger.debug('resizing graph', { reason, maximized: this.isMaximized });
                this.cy.resize();
                this.cy.fit(undefined, FIT_PADDING_PX);
            });
        });
    }

    _initGraph(executionFlowSpec) {
        const cytoscape = requireCytoscape();
        const startId = this._startNodeId;

        const nodes = executionFlowSpec.nodes.map((n) => {
            const isStart = n.id === startId;
            return {
                data: {
                    id: n.id,
                    label: isStart ? 'Click to Start' : n.label,
                    originalLabel: n.label,
                    kind: n.kind,
                },
                classes: isStart
                    ? `node kind-${n.kind} ${STATES.PENDING} clickable-start`
                    : `node kind-${n.kind} ${STATES.PENDING} hidden-node`,
            };
        });

        const edges = executionFlowSpec.edges.map((e) => ({
            data: { id: e.id, source: e.source, target: e.target },
            classes: `edge ${STATES.PENDING} hidden-edge`,
        }));

        this.cy = cytoscape({
            container: this.container,
            elements: { nodes, edges },
            style: this._styles(),
            layout: { name: 'preset' }, // Start with preset (no positions yet)
            userZoomingEnabled: true,
            userPanningEnabled: true,
            boxSelectionEnabled: false,
            wheelSensitivity: 0.18,
            minZoom: 0.5,
            maxZoom: 6,
        });

        this.cy.on('tap', 'node', (evt) => this._handleNodeClick(evt.target));

        // Mark start node as revealed
        this._revealedNodes.add(startId);

        // Run dagre layout, store natural position, then center start node
        const layout = this.cy.layout(this._layoutConfig());
        layout.run();

        const startNode = this.cy.$(`#${startId}`);
        this._startNodeNaturalPosition = { ...startNode.position() };

        // Center start node immediately (before browser paints)
        this.cy.center(startNode);

        logger.info('graph initialized with hidden nodes');
    }

    _handleNodeClick(node) {
        if (!node) {
            throw new Error('dag_renderer: node is required');
        }
        const nodeData = node.data();
        const id = nodeData.id;
        if (!id) {
            throw new Error('dag_renderer: nodeData.id is required');
        }

        // Handle start node click to begin playback
        if (id === this._startNodeId && !this._playbackStarted) {
            this._playbackStarted = true;
            node.removeClass('clickable-start');
            node.data('label', nodeData.originalLabel);
            logger.info('start node clicked, animating to position');

            // Animate node from center to natural left position
            node.animate(
                { position: this._startNodeNaturalPosition },
                {
                    duration: 500,
                    easing: 'ease-in-out',
                    complete: () => {
                        // Fit graph into view, then start playback
                        this.cy.animate({
                            fit: { eles: this.cy.elements(), padding: FIT_PADDING_PX }
                        }, {
                            duration: 300,
                            complete: () => {
                                logger.info('animation complete, triggering playback');
                                this._onStartClick();
                            }
                        });
                    }
                }
            );
            return;
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
                    'font-size': '16px',
                    'color': '#111827',
                    'background-color': '#E5E7EB',
                    'border-width': 1,
                    'border-color': '#9CA3AF',
                    'text-wrap': 'wrap',
                    'text-max-width': 140,
                    'width': 150,
                    'height': 82,
                    'shape': 'round-rectangle',
                    'opacity': 1,
                },
            },
            { selector: 'edge', style: { 'width': 2, 'line-color': '#CBD5E1', 'target-arrow-shape': 'triangle', 'target-arrow-color': '#CBD5E1', 'curve-style': 'bezier', 'opacity': 1 } },
            { selector: 'edge.pending', style: { 'line-color': '#CBD5E1', 'target-arrow-color': '#CBD5E1' } },
            { selector: 'edge.active', style: { 'line-color': '#DC2626', 'target-arrow-color': '#DC2626' } },
            { selector: 'edge.completed', style: { 'line-color': '#10B981', 'target-arrow-color': '#10B981' } },
            { selector: 'edge.error', style: { 'line-color': '#DC2626', 'target-arrow-color': '#DC2626' } },
            { selector: '.pending', style: { 'background-color': '#E5E7EB', 'border-color': '#9CA3AF' } },
            { selector: '.active', style: { 'background-color': '#FEE2E2', 'border-color': '#DC2626', 'border-width': 2 } },
            { selector: '.completed', style: { 'background-color': '#D1FAE5', 'border-color': '#10B981', 'border-width': 2 } },
            { selector: '.error', style: { 'background-color': '#FEE2E2', 'border-color': '#DC2626', 'border-width': 2 } },
            { selector: '.kind-service', style: { 'width': 210, 'height': 98, 'font-size': '15px', 'text-max-width': 196 } },
            { selector: '.kind-start', style: { 'shape': 'ellipse', 'width': 126, 'height': 64, 'font-size': '16px', 'text-max-width': 116 } },
            { selector: '.kind-complete', style: { 'shape': 'ellipse', 'width': 134, 'height': 64, 'font-size': '16px', 'text-max-width': 124 } },
            { selector: '.kind-evaluation', style: { 'shape': 'diamond', 'width': 104, 'height': 104, 'font-size': '15px', 'text-max-width': 96 } },
            // Hidden nodes and edges (initially invisible)
            { selector: '.hidden-node', style: { 'opacity': 0, 'events': 'no' } },
            { selector: '.hidden-edge', style: { 'opacity': 0 } },
            // Clickable start node styling
            { selector: '.clickable-start', style: { 'border-width': 2, 'border-color': '#DC2626', 'cursor': 'pointer' } },
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
            // Skip hidden edges (not yet revealed)
            if (edge.hasClass('hidden-edge')) {
                return;
            }

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

    async _applyDagUpdates(updates) {
        const list = assertArray(updates, 'eventInfo.dagUpdates');
        for (let idx = 0; idx < list.length; idx += 1) {
            const update = assertObject(list[idx], `eventInfo.dagUpdates[${idx}]`);
            const nodeId = assertNonEmptyString(update.nodeId, `eventInfo.dagUpdates[${idx}].nodeId`);
            const state = assertEnum(update.state, `eventInfo.dagUpdates[${idx}].state`, [
                STATES.PENDING,
                STATES.ACTIVE,
                STATES.COMPLETED,
                STATES.ERROR,
            ]);

            // Reveal node if not yet revealed (fade in)
            if (!this._revealedNodes.has(nodeId)) {
                const node = this.cy.$(`#${nodeId}`);
                node.removeClass('hidden-node');
                await this._revealNode(nodeId);
            }

            this._setNodeState(nodeId, state);
        }
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
}
