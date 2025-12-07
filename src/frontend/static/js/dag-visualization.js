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
        this.currentAgent = null;
        this.isInitialized = false;

        this._initializeGraph();
    }

    /**
     * Initialize the Cytoscape graph with dagre layout.
     */
    _initializeGraph() {
        console.log('[DAG] Initializing graph...');

        // Define main node data
        const nodes = [
            {
                data: { id: 'user', label: 'User', nodeType: 'main' },
                classes: 'main-node'
            },
            {
                data: { id: 'orchestrator', label: 'Orchestrator', nodeType: 'main' },
                classes: 'main-node'
            },
            {
                data: { id: 'agent', label: 'Agent', nodeType: 'main' },
                classes: 'main-node'
            },
            {
                data: { id: 'output', label: 'Output', nodeType: 'main' },
                classes: 'main-node'
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
                classes: 'main-edge'
            }
        ];

        // Initialize Cytoscape with dagre layout
        this.cy = cytoscape({
            container: this.container,
            elements: { nodes, edges },
            style: this._getStyles(),
            layout: this._getLayoutConfig(),
            userZoomingEnabled: false,
            userPanningEnabled: false,
            boxSelectionEnabled: false,
            autoungrabify: true
        });

        // Initialize all main nodes to pending
        this._resetAllNodes();

        // Add click handler
        this.cy.on('tap', 'node', (evt) => {
            const nodeData = evt.target.data();
            console.log('[DAG] Node clicked:', nodeData);
            this.onNodeClick(nodeData);
        });

        this.isInitialized = true;
        console.log('[DAG] Graph initialized successfully');
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
            {
                selector: 'node',
                style: {
                    'background-color': '#E5E7EB',
                    'label': 'data(label)',
                    'text-valign': 'bottom',
                    'text-halign': 'center',
                    'font-size': '11px',
                    'font-weight': '500',
                    'text-margin-y': '6px',
                    'color': '#374151',
                    'border-width': '2px',
                    'border-color': '#D1D5DB',
                    'transition-property': 'background-color, border-color, border-width, width, height',
                    'transition-duration': '0.3s'
                }
            },
            // Main node style
            {
                selector: 'node.main-node',
                style: {
                    'width': '45px',
                    'height': '45px',
                    'shape': 'ellipse',
                    'font-size': '11px',
                    'font-weight': '600'
                }
            },
            // Tool node style
            {
                selector: 'node.tool-node',
                style: {
                    'width': '32px',
                    'height': '32px',
                    'shape': 'round-rectangle',
                    'font-size': '9px',
                    'font-weight': '400',
                    'text-margin-y': '5px'
                }
            },
            // Pending state
            {
                selector: 'node.pending',
                style: {
                    'background-color': '#E5E7EB',
                    'border-color': '#D1D5DB',
                    'opacity': 0.6
                }
            },
            // Active state
            {
                selector: 'node.active',
                style: {
                    'background-color': '#3B82F6',
                    'border-color': '#1D4ED8',
                    'border-width': '3px',
                    'opacity': 1
                }
            },
            // Completed state
            {
                selector: 'node.completed',
                style: {
                    'background-color': '#10B981',
                    'border-color': '#059669',
                    'opacity': 1
                }
            },
            // Error state
            {
                selector: 'node.error',
                style: {
                    'background-color': '#EF4444',
                    'border-color': '#DC2626',
                    'opacity': 1
                }
            },
            // Base edge style
            {
                selector: 'edge',
                style: {
                    'width': 2,
                    'line-color': '#D1D5DB',
                    'target-arrow-color': '#D1D5DB',
                    'target-arrow-shape': 'triangle',
                    'arrow-scale': 0.8,
                    'curve-style': 'bezier',
                    'opacity': 0.6,
                    'transition-property': 'line-color, target-arrow-color, opacity, width',
                    'transition-duration': '0.3s'
                }
            },
            // Main edge style (with labels)
            {
                selector: 'edge.main-edge',
                style: {
                    'label': 'data(label)',
                    'font-size': '9px',
                    'color': '#6B7280',
                    'text-margin-y': '-8px',
                    'text-rotation': 'autorotate'
                }
            },
            // Tool edge style (no labels)
            {
                selector: 'edge.tool-edge',
                style: {
                    'width': 1.5,
                    'line-style': 'dashed',
                    'arrow-scale': 0.6
                }
            },
            // Active edge
            {
                selector: 'edge.active',
                style: {
                    'line-color': '#3B82F6',
                    'target-arrow-color': '#3B82F6',
                    'opacity': 1,
                    'width': 2.5
                }
            },
            // Completed edge
            {
                selector: 'edge.completed',
                style: {
                    'line-color': '#10B981',
                    'target-arrow-color': '#10B981',
                    'opacity': 1
                }
            }
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
                this.setNodeState('orchestrator', DAGVisualization.STATES.ACTIVE);
                break;

            case 'routing':
                // Orchestrator is routing, stays active
                this.setNodeState('orchestrator', DAGVisualization.STATES.ACTIVE);
                break;

            case 'agent_handoff':
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
                }
                break;

            case 'agent_thinking':
                // Keep agent active during thinking
                this.setNodeState('agent', DAGVisualization.STATES.ACTIVE);
                if (agentName && agentName !== 'orchestrator') {
                    this.updateAgentLabel(agentName);
                }
                break;

            case 'analysis_complete':
            case 'complete':
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
