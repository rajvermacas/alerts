/**
 * DAGVisualization - Real-time execution flow graph for SMARTS Alert Analyzer.
 *
 * Visualizes the multi-agent execution pipeline using Cytoscape.js with dagre layout.
 * Shows: User -> Orchestrator -> Agent (with tools) -> Output
 *
 * Tools are dynamically added as tool_started events arrive, providing real-time
 * visibility into which specific tool is currently executing within the agent.
 */

class DAGVisualization {
    /**
     * Node states for the DAG.
     */
    static STATES = {
        PENDING: 'pending',
        ACTIVE: 'active',
        COMPLETED: 'completed',
        ERROR: 'error'
    };

    /**
     * Main node IDs.
     */
    static MAIN_NODES = ['user', 'orchestrator', 'agent', 'output'];

    /**
     * Create a DAGVisualization instance.
     * @param {Object} options - Configuration options
     * @param {HTMLElement} options.container - Container element for the graph
     * @param {Function} options.onNodeClick - Optional click handler for nodes
     */
    constructor(options) {
        if (!options.container) {
            throw new Error('DAGVisualization: container element is required');
        }

        this.container = options.container;
        this.onNodeClick = options.onNodeClick || (() => {});
        this.cy = null;
        this.nodeStates = {};
        this.toolNodes = new Set();
        this.toolResults = new Map(); // toolName -> { outputSummary, durationSeconds }
        this.currentAgent = null;
        this.isInitialized = false;
        this.isMaximized = false;
        this.maximizeOverlay = null;

        this._initializeGraph();
        this._initializeMaximizeButton();
    }

    /**
     * Store tool result for later retrieval on click.
     * @param {string} toolName - Name of the tool
     * @param {string} outputSummary - Tool output summary
     * @param {number} durationSeconds - Execution duration in seconds
     */
    storeToolResult(toolName, outputSummary, durationSeconds) {
        this.toolResults.set(toolName, { outputSummary, durationSeconds });
        console.log(`[DAG] Stored result for tool: ${toolName}`);
    }

    /**
     * Get stored tool result.
     * @param {string} toolName - Name of the tool
     * @returns {Object|undefined} Tool result object with outputSummary and durationSeconds
     */
    getToolResult(toolName) {
        return this.toolResults.get(toolName);
    }

    /**
     * Initialize the Cytoscape graph with dagre layout.
     */
    _initializeGraph() {
        console.log('[DAG] Initializing graph...');

        // Define main node data
        // Node types are distinguished by shape: ellipse=agent, rectangle=tool, diamond=process
        const nodes = [
            {
                data: { id: 'user', label: 'User', nodeType: 'main' },
                classes: 'main-node'
            },
            {
                data: { id: 'orchestrator', label: 'Orchestrator', nodeType: 'main', nodeCategory: 'agent' },
                classes: 'main-node agent-node'
            },
            {
                data: { id: 'agent', label: 'Agent', nodeType: 'main', nodeCategory: 'agent' },
                classes: 'main-node agent-node'
            },
            {
                data: { id: 'output', label: 'Output', nodeType: 'main' },
                classes: 'main-node hidden-node'
            }
        ];

        // Define main edge data
        const edges = [
            {
                data: { id: 'e-user-orch', source: 'user', target: 'orchestrator', label: 'Submit' },
                classes: 'main-edge'
            },
            {
                data: { id: 'e-orch-agent', source: 'orchestrator', target: 'agent', label: 'Route' },
                classes: 'main-edge'
            },
            {
                data: { id: 'e-agent-output', source: 'agent', target: 'output', label: 'Result' },
                classes: 'main-edge hidden-edge'
            }
        ];

        // Initialize Cytoscape with dagre layout
        this.cy = cytoscape({
            container: this.container,
            elements: { nodes, edges },
            style: this._getStyles(),
            layout: this._getLayoutConfig(),
            userZoomingEnabled: true,
            userPanningEnabled: true,
            boxSelectionEnabled: false,
            autoungrabify: false,
            wheelSensitivity: 0.1,
            minZoom: 0.5,
            maxZoom: 3
        });

        // Initialize all main nodes to pending
        this._resetAllNodes();

        // Add click handler
        this.cy.on('tap', 'node', (evt) => {
            const nodeData = evt.target.data();
            console.log('[DAG] Node clicked:', nodeData);
            this.onNodeClick(nodeData);
        });

        // Add resize observer for container resizing
        this._initializeResizeObserver();

        this.isInitialized = true;
        console.log('[DAG] Graph initialized successfully');
    }

    /**
     * Initialize resize observer to handle container size changes.
     */
    _initializeResizeObserver() {
        if (typeof ResizeObserver === 'undefined') {
            console.warn('[DAG] ResizeObserver not supported');
            return;
        }

        this._resizeObserver = new ResizeObserver((entries) => {
            for (const entry of entries) {
                if (entry.target === this.container && this.cy) {
                    this.cy.resize();
                    this.cy.fit(undefined, 30);
                }
            }
        });

        this._resizeObserver.observe(this.container);
    }

    /**
     * Initialize the maximize button functionality.
     */
    _initializeMaximizeButton() {
        const maximizeBtn = document.getElementById('dag-maximize-btn');
        if (maximizeBtn) {
            maximizeBtn.addEventListener('click', () => this.toggleMaximize());
        }

        // Handle escape key to close maximized view
        this._handleEscapeKey = (e) => {
            if (e.key === 'Escape' && this.isMaximized) {
                this.toggleMaximize();
            }
        };
        document.addEventListener('keydown', this._handleEscapeKey);

        // Initialize reset layout button
        const resetBtn = document.getElementById('dag-reset-btn');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => this.resetLayout());
        }
    }

    /**
     * Reset the layout to the original dagre positions.
     */
    resetLayout() {
        console.log('[DAG] Resetting layout...');
        this._relayout();
        this.cy.fit(undefined, 30);
        console.log('[DAG] Layout reset complete');
    }

    /**
     * Toggle maximized/fullscreen view of the DAG.
     */
    toggleMaximize() {
        if (this.isMaximized) {
            this._minimizeGraph();
        } else {
            this._maximizeGraph();
        }
    }

    /**
     * Maximize the graph to fullscreen overlay.
     */
    _maximizeGraph() {
        console.log('[DAG] Maximizing graph...');

        // Create fullscreen overlay
        this.maximizeOverlay = document.createElement('div');
        this.maximizeOverlay.id = 'dag-maximize-overlay';
        this.maximizeOverlay.className = 'dag-maximize-overlay';
        this.maximizeOverlay.innerHTML = `
            <div class="dag-maximize-header">
                <span class="text-sm font-medium text-gray-700">Execution Flow</span>
                <button id="dag-minimize-btn" class="dag-minimize-btn" title="Close (Esc)">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </div>
            <div id="dag-maximize-container" class="dag-maximize-content"></div>
            <div class="dag-maximize-legend">
                <div class="dag-legend-section">
                    <span class="dag-legend-title">Status:</span>
                    <div class="flex items-center gap-1.5">
                        <span class="w-3 h-3 rounded-full bg-gray-300 border border-gray-400"></span>
                        <span>Pending</span>
                    </div>
                    <div class="flex items-center gap-1.5">
                        <span class="w-3 h-3 rounded-full bg-blue-500 border border-blue-600"></span>
                        <span>Active</span>
                    </div>
                    <div class="flex items-center gap-1.5">
                        <span class="w-3 h-3 rounded-full bg-green-500 border border-green-600"></span>
                        <span>Completed</span>
                    </div>
                    <div class="flex items-center gap-1.5">
                        <span class="w-3 h-3 rounded-full bg-red-500 border border-red-600"></span>
                        <span>Error</span>
                    </div>
                </div>
                <div class="dag-legend-divider"></div>
                <div class="dag-legend-section">
                    <span class="dag-legend-title">Node Type:</span>
                    <div class="flex items-center gap-1.5">
                        <span class="w-3 h-3 rounded-full bg-gray-400" style="border: 2px double #666;"></span>
                        <span>Agent</span>
                    </div>
                    <div class="flex items-center gap-1.5">
                        <span class="w-3 h-3 rounded bg-gray-400 border border-gray-600"></span>
                        <span>Tool</span>
                    </div>
                    <div class="flex items-center gap-1.5">
                        <span class="w-3 h-3 bg-gray-400 border border-dashed border-gray-600" style="transform: rotate(45deg);"></span>
                        <span>Process</span>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(this.maximizeOverlay);

        // Prevent body scroll
        document.body.style.overflow = 'hidden';

        // Get the new container
        const newContainer = document.getElementById('dag-maximize-container');

        // Move cytoscape to new container
        this.cy.mount(newContainer);

        // Re-run layout and fit
        this.cy.resize();
        this._relayout();
        this.cy.fit(undefined, 50);

        // Add close button handler
        const minimizeBtn = document.getElementById('dag-minimize-btn');
        if (minimizeBtn) {
            minimizeBtn.addEventListener('click', () => this.toggleMaximize());
        }

        // Click outside to close
        this.maximizeOverlay.addEventListener('click', (e) => {
            if (e.target === this.maximizeOverlay) {
                this.toggleMaximize();
            }
        });

        this.isMaximized = true;
        console.log('[DAG] Graph maximized');
    }

    /**
     * Minimize the graph back to original container.
     */
    _minimizeGraph() {
        console.log('[DAG] Minimizing graph...');

        if (!this.maximizeOverlay) return;

        // Move cytoscape back to original container
        this.cy.mount(this.container);

        // Remove overlay
        this.maximizeOverlay.remove();
        this.maximizeOverlay = null;

        // Restore body scroll
        document.body.style.overflow = '';

        // Re-run layout and fit
        this.cy.resize();
        this._relayout();

        this.isMaximized = false;
        console.log('[DAG] Graph minimized');
    }

    /**
     * Get the dagre layout configuration.
     * @returns {Object} Layout configuration
     */
    _getLayoutConfig() {
        return {
            name: 'dagre',
            rankDir: 'LR',
            nodeSep: 60,
            rankSep: 80,
            padding: 20,
            fit: true,
            animate: false,
            spacingFactor: 1.2
        };
    }

    /**
     * Get Cytoscape styles for nodes and edges.
     * @returns {Array} Style definitions
     */
    _getStyles() {
        return [
            // Base node style
            { selector: 'node', style: {
                'background-color': '#E5E7EB', 'label': 'data(label)', 'text-valign': 'bottom',
                'text-halign': 'center', 'font-size': '11px', 'font-weight': '500',
                'text-margin-y': '6px', 'color': '#374151', 'border-width': '2px',
                'border-color': '#D1D5DB', 'transition-property': 'background-color, border-color, border-width',
                'transition-duration': '0.3s'
            }},
            // Main node style (ellipse for agents)
            { selector: 'node.main-node', style: {
                'width': '45px', 'height': '45px', 'shape': 'ellipse', 'font-weight': '600'
            }},
            // Agent node style - double border to indicate "agent"
            { selector: 'node.agent-node', style: {
                'border-width': '3px', 'border-style': 'double'
            }},
            // Tool node style (rounded rectangle)
            { selector: 'node.tool-node', style: {
                'width': '32px', 'height': '32px', 'shape': 'round-rectangle',
                'font-size': '9px', 'font-weight': '400', 'text-margin-y': '5px',
                'border-style': 'solid'
            }},
            // Evaluation/Process node style (diamond shape)
            { selector: 'node.evaluation-node', style: {
                'width': '40px', 'height': '40px', 'shape': 'diamond',
                'font-size': '10px', 'font-weight': '500', 'text-margin-y': '6px',
                'border-style': 'dashed'
            }},
            // Node states
            { selector: 'node.pending', style: { 'background-color': '#E5E7EB', 'border-color': '#D1D5DB', 'opacity': 0.6 }},
            { selector: 'node.active', style: { 'background-color': '#3B82F6', 'border-color': '#1D4ED8', 'border-width': '3px', 'opacity': 1 }},
            { selector: 'node.completed', style: { 'background-color': '#10B981', 'border-color': '#059669', 'opacity': 1 }},
            { selector: 'node.error', style: { 'background-color': '#EF4444', 'border-color': '#DC2626', 'opacity': 1 }},
            // Interactive states
            { selector: 'node:grabbed', style: {
                'border-width': '4px', 'border-color': '#6366F1', 'shadow-blur': '10',
                'shadow-color': '#6366F1', 'shadow-opacity': 0.5
            }},
            { selector: 'node:active', style: { 'overlay-opacity': 0.1, 'overlay-color': '#3B82F6' }},
            // Base edge style
            { selector: 'edge', style: {
                'width': 2, 'line-color': '#D1D5DB', 'target-arrow-color': '#D1D5DB',
                'target-arrow-shape': 'triangle', 'arrow-scale': 0.8, 'curve-style': 'bezier',
                'opacity': 0.6, 'transition-property': 'line-color, target-arrow-color, opacity',
                'transition-duration': '0.3s'
            }},
            // Edge types
            { selector: 'edge.main-edge', style: { 'label': 'data(label)', 'font-size': '9px', 'color': '#6B7280', 'text-margin-y': '-8px', 'text-rotation': 'autorotate' }},
            { selector: 'edge.tool-edge', style: { 'width': 1.5, 'line-style': 'dashed', 'arrow-scale': 0.6 }},
            // Edge states
            { selector: 'edge.active', style: { 'line-color': '#3B82F6', 'target-arrow-color': '#3B82F6', 'opacity': 1, 'width': 2.5 }},
            { selector: 'edge.completed', style: { 'line-color': '#10B981', 'target-arrow-color': '#10B981', 'opacity': 1 }},
            // Hidden states (for output node before evaluation starts)
            { selector: 'node.hidden-node', style: { 'opacity': 0, 'visibility': 'hidden' }},
            { selector: 'edge.hidden-edge', style: { 'opacity': 0, 'visibility': 'hidden' }}
        ];
    }

    /**
     * Reset all main nodes to pending state.
     */
    _resetAllNodes() {
        DAGVisualization.MAIN_NODES.forEach(nodeId => {
            this._setNodeStateInternal(nodeId, DAGVisualization.STATES.PENDING);
        });
        this.cy.edges().removeClass('active completed').addClass('pending');
    }

    /**
     * Internal method to set a node's state without triggering edge updates.
     * @param {string} nodeId - Node identifier
     * @param {string} state - New state
     */
    _setNodeStateInternal(nodeId, state) {
        const node = this.cy.$(`#${nodeId}`);
        if (node.length === 0) {
            console.warn(`[DAG] Node not found: ${nodeId}`);
            return;
        }

        // Remove all state classes and add new one
        node.removeClass('pending active completed error').addClass(state);
        this.nodeStates[nodeId] = state;
    }

    /**
     * Set a node's state and update connected edges.
     * @param {string} nodeId - Node identifier
     * @param {string} state - New state
     */
    setNodeState(nodeId, state) {
        this._setNodeStateInternal(nodeId, state);
        this._updateEdgeStates();
        console.log(`[DAG] Node ${nodeId} -> ${state}`);
    }

    /**
     * Update edge states based on connected node states.
     */
    _updateEdgeStates() {
        this.cy.edges().forEach(edge => {
            const sourceState = this.nodeStates[edge.source().id()];
            const targetState = this.nodeStates[edge.target().id()];

            edge.removeClass('pending active completed');

            if (sourceState === DAGVisualization.STATES.COMPLETED &&
                targetState === DAGVisualization.STATES.COMPLETED) {
                edge.addClass('completed');
            } else if (sourceState === DAGVisualization.STATES.COMPLETED ||
                       sourceState === DAGVisualization.STATES.ACTIVE) {
                edge.addClass('active');
            } else {
                edge.addClass('pending');
            }
        });
    }

    /**
     * Update agent label based on detected agent type.
     * @param {string} agentName - Agent identifier (e.g., 'insider_trading', 'wash_trade')
     */
    updateAgentLabel(agentName) {
        if (!agentName || this.currentAgent === agentName) return;

        this.currentAgent = agentName;
        const labelMap = {
            'insider_trading': 'Insider Trading',
            'wash_trade': 'Wash Trade'
        };

        const label = labelMap[agentName] || agentName;
        const node = this.cy.$('#agent');
        if (node.length > 0) {
            node.data('label', label);
            console.log(`[DAG] Agent label updated: ${label}`);
        }
    }

    /**
     * Format tool name for display.
     * @param {string} toolName - Raw tool name (e.g., 'trader_history')
     * @returns {string} Formatted name (e.g., 'Trader History')
     */
    _formatToolName(toolName) {
        if (!toolName) return 'Unknown Tool';

        // Remove common suffixes
        let name = toolName.replace(/_tool$/i, '').replace(/Tool$/i, '');

        // Convert snake_case to Title Case
        return name
            .split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
            .join(' ');
    }

    /**
     * Generate a safe node ID from tool name.
     * @param {string} toolName - Raw tool name
     * @returns {string} Safe node ID
     */
    _getToolNodeId(toolName) {
        return `tool-${toolName.toLowerCase().replace(/[^a-z0-9]/g, '-')}`;
    }

    /**
     * Add a tool node dynamically.
     * @param {string} toolName - Name of the tool
     * @returns {string} Node ID of the added tool
     */
    addToolNode(toolName) {
        const nodeId = this._getToolNodeId(toolName);

        // Check if tool node already exists
        if (this.toolNodes.has(nodeId)) {
            console.log(`[DAG] Tool node already exists: ${nodeId}`);
            return nodeId;
        }

        const label = this._formatToolName(toolName);
        console.log(`[DAG] Adding tool node: ${nodeId} (${label})`);

        // Add tool node
        this.cy.add({
            group: 'nodes',
            data: {
                id: nodeId,
                label: label,
                nodeType: 'tool',
                nodeCategory: 'tool',
                toolName: toolName
            },
            classes: 'tool-node pending'
        });

        // Add edge from agent to tool
        this.cy.add({
            group: 'edges',
            data: {
                id: `e-agent-${nodeId}`,
                source: 'agent',
                target: nodeId
            },
            classes: 'tool-edge pending'
        });

        this.toolNodes.add(nodeId);
        this.nodeStates[nodeId] = DAGVisualization.STATES.PENDING;

        // Re-run layout to position new node
        this._relayout();

        return nodeId;
    }

    /**
     * Set a tool node's state.
     * @param {string} toolName - Name of the tool
     * @param {string} state - New state
     */
    setToolState(toolName, state) {
        const nodeId = this._getToolNodeId(toolName);

        // Add tool node if it doesn't exist
        if (!this.toolNodes.has(nodeId)) {
            this.addToolNode(toolName);
        }

        this._setNodeStateInternal(nodeId, state);
        this._updateEdgeStates();
        console.log(`[DAG] Tool ${toolName} -> ${state}`);
    }

    /**
     * Add the evaluation node dynamically when final determination begins.
     * This node appears between the agent and output nodes.
     */
    addEvaluationNode() {
        const nodeId = 'evaluation';

        // Check if evaluation node already exists
        if (this.cy.$(`#${nodeId}`).length > 0) {
            console.log('[DAG] Evaluation node already exists');
            return;
        }

        console.log('[DAG] Adding evaluation node');

        // Add evaluation node
        this.cy.add({
            group: 'nodes',
            data: {
                id: nodeId,
                label: 'Evaluation',
                nodeType: 'evaluation',
                nodeCategory: 'process'
            },
            classes: 'evaluation-node pending'
        });

        // Add edge from agent to evaluation
        this.cy.add({
            group: 'edges',
            data: {
                id: 'e-agent-evaluation',
                source: 'agent',
                target: nodeId
            },
            classes: 'main-edge pending'
        });

        // Add edge from evaluation to output
        this.cy.add({
            group: 'edges',
            data: {
                id: 'e-evaluation-output',
                source: nodeId,
                target: 'output'
            },
            classes: 'main-edge pending'
        });

        // Remove direct agent->output edge
        this.cy.$('#e-agent-output').remove();

        // Track evaluation node state
        this.nodeStates[nodeId] = DAGVisualization.STATES.PENDING;

        // Re-run layout to position new node
        this._relayout();
    }

    /**
     * Re-run the dagre layout after adding nodes.
     */
    _relayout() {
        console.log('[DAG] Re-running layout...');
        this.cy.layout(this._getLayoutConfig()).run();
    }

    /**
     * Process an event from the streaming system.
     * @param {Object} eventInfo - Event information from ProgressTimeline
     */
    handleEvent(eventInfo) {
        if (!eventInfo || !eventInfo.type) {
            console.warn('[DAG] Invalid event received:', eventInfo);
            return;
        }

        const eventType = eventInfo.type;
        const agentName = eventInfo.agentName;
        const toolName = eventInfo.toolName;

        console.log(`[DAG] Processing event: ${eventType}, agent: ${agentName}, tool: ${toolName}`);

        switch (eventType) {
            case 'analysis_started':
                this.setNodeState('user', DAGVisualization.STATES.COMPLETED);
                // Only set orchestrator to active if this event is from orchestrator itself
                // Specialized agents also emit analysis_started, but orchestrator should stay completed
                if (!agentName || agentName === 'orchestrator') {
                    this.setNodeState('orchestrator', DAGVisualization.STATES.ACTIVE);
                }
                // If the event is from a specialized agent (post-handoff), ensure agent is active
                if (agentName && agentName !== 'orchestrator') {
                    this.setNodeState('agent', DAGVisualization.STATES.ACTIVE);
                    this.updateAgentLabel(agentName);
                }
                break;

            case 'routing':
                // Orchestrator is routing, stays active
                this.setNodeState('orchestrator', DAGVisualization.STATES.ACTIVE);
                break;

            case 'agent_handoff':
                console.log('[DAG] agent_handoff received - marking orchestrator COMPLETED, agent ACTIVE');
                this.setNodeState('orchestrator', DAGVisualization.STATES.COMPLETED);
                this.setNodeState('agent', DAGVisualization.STATES.ACTIVE);
                if (agentName) {
                    this.updateAgentLabel(agentName);
                }
                break;

            case 'tool_started':
                // Ensure agent is active
                this.setNodeState('agent', DAGVisualization.STATES.ACTIVE);
                if (agentName && agentName !== 'orchestrator') {
                    this.updateAgentLabel(agentName);
                }
                // Add and activate tool node
                if (toolName) {
                    this.setToolState(toolName, DAGVisualization.STATES.ACTIVE);
                }
                break;

            case 'tool_progress':
                // Keep tool active during progress
                if (toolName) {
                    this.setToolState(toolName, DAGVisualization.STATES.ACTIVE);
                }
                break;

            case 'tool_completed':
                // Mark tool as completed
                if (toolName) {
                    this.setToolState(toolName, DAGVisualization.STATES.COMPLETED);
                    // Store tool result for click display
                    if (eventInfo.outputSummary) {
                        this.storeToolResult(toolName, eventInfo.outputSummary, eventInfo.durationSeconds);
                    }
                }
                break;

            case 'agent_thinking':
                // Keep agent active during thinking
                this.setNodeState('agent', DAGVisualization.STATES.ACTIVE);
                if (agentName && agentName !== 'orchestrator') {
                    this.updateAgentLabel(agentName);
                }
                break;

            case 'evaluation_started':
                // Add evaluation node dynamically and set it to active
                this.addEvaluationNode();
                this.setNodeState('evaluation', DAGVisualization.STATES.ACTIVE);
                // Show output node now that evaluation has started
                this.cy.$('#output').removeClass('hidden-node');
                // Note: e-agent-output edge is removed by addEvaluationNode() and replaced
                // with e-evaluation-output, so no need to unhide it here
                break;

            case 'analysis_complete':
            case 'complete':
                // Mark ALL nodes as completed when analysis finishes
                // This ensures orchestrator is completed even if agent_handoff event was missed
                this.setNodeState('orchestrator', DAGVisualization.STATES.COMPLETED);
                // Mark evaluation as completed if it exists
                if (this.cy.$('#evaluation').length > 0) {
                    this.setNodeState('evaluation', DAGVisualization.STATES.COMPLETED);
                }
                // Mark agent and all tools as completed
                this.setNodeState('agent', DAGVisualization.STATES.COMPLETED);
                this._completeAllTools();
                this.setNodeState('output', DAGVisualization.STATES.COMPLETED);
                break;

            case 'error':
                this._handleError();
                break;

            default:
                console.log(`[DAG] Unhandled event type: ${eventType}`);
        }
    }

    /**
     * Mark all tool nodes as completed.
     */
    _completeAllTools() {
        this.toolNodes.forEach(nodeId => {
            this._setNodeStateInternal(nodeId, DAGVisualization.STATES.COMPLETED);
        });
        this._updateEdgeStates();
    }

    /**
     * Handle error state by marking current active node as error.
     */
    _handleError() {
        // Find the currently active node and mark it as error
        const activeEntry = Object.entries(this.nodeStates)
            .find(([_, state]) => state === DAGVisualization.STATES.ACTIVE);

        if (activeEntry) {
            const [nodeId] = activeEntry;
            this.setNodeState(nodeId, DAGVisualization.STATES.ERROR);
            console.log(`[DAG] Error state set on node: ${nodeId}`);
        }
    }

    /**
     * Reset the visualization for a new analysis.
     */
    reset() {
        console.log('[DAG] Resetting visualization...');

        // Remove all tool nodes and their edges
        this.toolNodes.forEach(nodeId => {
            this.cy.$(`#${nodeId}`).remove();
            this.cy.$(`#e-agent-${nodeId}`).remove();
            delete this.nodeStates[nodeId];
        });
        this.toolNodes.clear();
        this.toolResults.clear();

        // Remove evaluation node if it exists
        const evaluationNode = this.cy.$('#evaluation');
        if (evaluationNode.length > 0) {
            this.cy.$('#e-agent-evaluation').remove();
            this.cy.$('#e-evaluation-output').remove();
            evaluationNode.remove();
            delete this.nodeStates['evaluation'];

            // Restore direct agent->output edge (hidden initially)
            this.cy.add({
                group: 'edges',
                data: {
                    id: 'e-agent-output',
                    source: 'agent',
                    target: 'output',
                    label: 'Result'
                },
                classes: 'main-edge hidden-edge'
            });
        }

        // Re-hide output node (it's shown when evaluation starts)
        const outputNode = this.cy.$('#output');
        if (outputNode.length > 0) {
            outputNode.addClass('hidden-node');
        }

        // Also hide e-agent-output edge if it exists
        const agentOutputEdge = this.cy.$('#e-agent-output');
        if (agentOutputEdge.length > 0) {
            agentOutputEdge.addClass('hidden-edge');
        }

        // Reset agent label
        this.currentAgent = null;
        const agentNode = this.cy.$('#agent');
        if (agentNode.length > 0) {
            agentNode.data('label', 'Agent');
        }

        // Reset all main nodes to pending
        this._resetAllNodes();

        // Re-run layout
        this._relayout();

        console.log('[DAG] Reset complete');
    }

    /**
     * Destroy the visualization and cleanup resources.
     */
    destroy() {
        console.log('[DAG] Destroying visualization...');

        // Close maximized view if open
        if (this.isMaximized) {
            this._minimizeGraph();
        }

        // Remove escape key listener
        if (this._handleEscapeKey) {
            document.removeEventListener('keydown', this._handleEscapeKey);
        }

        // Disconnect resize observer
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }

        if (this.cy) {
            this.cy.destroy();
            this.cy = null;
        }
        this.isInitialized = false;
        this.toolNodes.clear();
        this.nodeStates = {};
    }

    /**
     * Check if the visualization is initialized.
     * @returns {boolean} True if initialized
     */
    isReady() {
        return this.isInitialized && this.cy !== null;
    }

    /**
     * Get current state of all nodes.
     * @returns {Object} Map of node IDs to states
     */
    getNodeStates() {
        return { ...this.nodeStates };
    }

    /**
     * Get list of tool node IDs.
     * @returns {Array} Array of tool node IDs
     */
    getToolNodes() {
        return Array.from(this.toolNodes);
    }
}

// Export for module systems and global access
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DAGVisualization;
}
if (typeof window !== 'undefined') {
    window.DAGVisualization = DAGVisualization;
}
