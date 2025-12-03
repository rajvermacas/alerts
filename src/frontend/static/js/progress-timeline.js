/**
 * ProgressTimeline - Real-time streaming progress visualization.
 *
 * This class handles Server-Sent Events (SSE) from the backend and
 * renders a visual timeline showing the progress of alert analysis.
 *
 * Features:
 * - SSE connection with automatic reconnection
 * - Visual timeline with event icons and timestamps
 * - Tool-level progress tracking
 * - Fail-fast error handling (no polling fallback)
 * - Accessibility support (ARIA attributes)
 */

class ProgressTimeline {
    /**
     * Create a ProgressTimeline instance.
     * @param {Object} options - Configuration options
     * @param {string} options.taskId - The task ID to stream events for
     * @param {HTMLElement} options.container - Container element for the timeline
     * @param {Function} options.onComplete - Callback when analysis completes
     * @param {Function} options.onError - Callback on error
     * @param {Function} options.onProgress - Optional callback for progress events
     * @param {number} options.reconnectDelay - Delay between reconnection attempts (ms)
     * @param {number} options.maxReconnectAttempts - Maximum reconnection attempts
     */
    constructor(options) {
        this.taskId = options.taskId;
        this.container = options.container;
        this.onComplete = options.onComplete || (() => {});
        this.onError = options.onError || ((msg) => console.error('Timeline error:', msg));
        this.onProgress = options.onProgress || (() => {});
        this.reconnectDelay = options.reconnectDelay || 3000;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 5;

        // Internal state
        this.eventSource = null;
        this.events = [];
        this.reconnectAttempts = 0;
        this.isConnected = false;
        this.startTime = Date.now();
        this.lastEventId = null;

        // Bind methods
        this.handleOpen = this.handleOpen.bind(this);
        this.handleError = this.handleError.bind(this);
        this.handleMessage = this.handleMessage.bind(this);

        console.log(`[ProgressTimeline] Created for task ${this.taskId}`);
    }

    /**
     * Start streaming events from the server.
     * @throws {Error} If EventSource is not supported by the browser
     */
    start() {
        console.log(`[ProgressTimeline] Starting SSE connection for task ${this.taskId}`);

        // Check for EventSource support - fail fast if not available
        if (!window.EventSource) {
            const errorMsg = 'Your browser does not support real-time streaming. Please use a modern browser (Chrome, Firefox, Safari, or Edge).';
            console.error('[ProgressTimeline] EventSource not supported');
            this.onError(errorMsg);
            throw new Error(errorMsg);
        }

        this.connect();
    }

    /**
     * Connect to the SSE endpoint.
     */
    connect() {
        // Build URL with optional lastEventId for reconnection
        let url = `/api/stream/${this.taskId}`;
        if (this.lastEventId) {
            url += `?lastEventId=${encodeURIComponent(this.lastEventId)}`;
        }

        console.log(`[ProgressTimeline] Connecting to ${url}`);

        // Create EventSource
        this.eventSource = new EventSource(url);

        // Set up event handlers
        this.eventSource.onopen = this.handleOpen;
        this.eventSource.onerror = this.handleError;
        this.eventSource.onmessage = this.handleMessage;

        // Listen for specific event types
        this.eventSource.addEventListener('analysis_started', (e) => this.handleEvent('analysis_started', e));
        this.eventSource.addEventListener('tool_started', (e) => this.handleEvent('tool_started', e));
        this.eventSource.addEventListener('tool_progress', (e) => this.handleEvent('tool_progress', e));
        this.eventSource.addEventListener('tool_completed', (e) => this.handleEvent('tool_completed', e));
        this.eventSource.addEventListener('analysis_complete', (e) => this.handleEvent('analysis_complete', e));
        this.eventSource.addEventListener('update', (e) => this.handleEvent('update', e));
        this.eventSource.addEventListener('error', (e) => this.handleEvent('error', e));
        this.eventSource.addEventListener('complete', (e) => this.handleEvent('complete', e));
        this.eventSource.addEventListener('keepalive', (e) => this.handleKeepalive(e));

        // Orchestrator events
        this.eventSource.addEventListener('routing', (e) => this.handleEvent('routing', e));
        this.eventSource.addEventListener('agent_handoff', (e) => this.handleEvent('agent_handoff', e));

        // Agent events
        this.eventSource.addEventListener('agent_thinking', (e) => this.handleEvent('agent_thinking', e));

        // Keep-alive (snake_case version to match backend)
        this.eventSource.addEventListener('keep_alive', (e) => this.handleKeepalive(e));
    }

    /**
     * Handle SSE connection opened.
     * @param {Event} event - Open event
     */
    handleOpen(event) {
        console.log('[ProgressTimeline] SSE connection opened');
        this.isConnected = true;
        this.reconnectAttempts = 0;

        // Add connection event to timeline
        this.addTimelineEvent({
            type: 'connection',
            message: 'Connected to analysis stream',
            timestamp: new Date().toISOString(),
            icon: 'wifi',
            color: 'green',
        });
    }

    /**
     * Handle SSE connection error.
     * @param {Event} event - Error event
     */
    handleError(event) {
        console.error('[ProgressTimeline] SSE error:', event);

        if (this.eventSource.readyState === EventSource.CLOSED) {
            this.isConnected = false;

            // Attempt reconnection
            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                console.log(`[ProgressTimeline] Reconnecting (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);

                this.addTimelineEvent({
                    type: 'reconnecting',
                    message: `Connection lost. Reconnecting (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`,
                    timestamp: new Date().toISOString(),
                    icon: 'refresh',
                    color: 'yellow',
                });

                setTimeout(() => this.connect(), this.reconnectDelay);
            } else {
                // Fail fast - no polling fallback
                console.error('[ProgressTimeline] Max reconnection attempts reached - failing');
                this.addTimelineEvent({
                    type: 'error',
                    message: 'Connection lost. Please try again.',
                    timestamp: new Date().toISOString(),
                    icon: 'exclamation',
                    color: 'red',
                });
                this.stop();
                this.onError('Connection lost after maximum reconnection attempts. Please try again.');
            }
        }
    }

    /**
     * Handle generic SSE message.
     * @param {MessageEvent} event - Message event
     */
    handleMessage(event) {
        console.log('[ProgressTimeline] Received message:', event.data);
        this.processEventData(event.data, event.lastEventId, 'message');
    }

    /**
     * Handle typed SSE event.
     * @param {string} eventType - Event type
     * @param {MessageEvent} event - Message event
     */
    handleEvent(eventType, event) {
        console.log(`[ProgressTimeline] Received ${eventType} event:`, event.data);
        this.processEventData(event.data, event.lastEventId, eventType);
    }

    /**
     * Handle keepalive event.
     * @param {MessageEvent} event - Keepalive event
     */
    handleKeepalive(event) {
        console.log('[ProgressTimeline] Keepalive received');
        // Just update the last event ID for reconnection
        if (event.lastEventId) {
            this.lastEventId = event.lastEventId;
        }
    }

    /**
     * Process event data from SSE.
     * @param {string} data - Raw event data (JSON string)
     * @param {string} eventId - Event ID from SSE
     * @param {string} eventType - Event type
     */
    processEventData(data, eventId, eventType) {
        // Store last event ID for reconnection
        if (eventId) {
            this.lastEventId = eventId;
        }

        try {
            const parsed = JSON.parse(data);
            this.processA2AEvent(parsed, eventType);
        } catch (e) {
            console.warn('[ProgressTimeline] Failed to parse event data:', e);
        }
    }

    /**
     * Process A2A protocol event.
     * @param {Object} event - Parsed A2A event
     * @param {string} eventType - Event type from SSE
     */
    processA2AEvent(event, eventType) {
        // Extract metadata from A2A format
        const result = event.result || {};
        const metadata = result.metadata || {};
        const taskStatusEvent = result.taskStatusUpdateEvent || {};
        const task = taskStatusEvent.task || result.task || {};
        const isFinal = taskStatusEvent.final || false;

        // Determine event details
        const eventInfo = this.extractEventInfo(metadata, taskStatusEvent, eventType);

        // Add to internal events list
        this.events.push({
            ...eventInfo,
            raw: event,
            timestamp: metadata.timestamp || new Date().toISOString(),
        });

        // Add to visual timeline
        this.addTimelineEvent(eventInfo);

        // Call progress callback
        this.onProgress(eventInfo);

        // Check for completion
        if (isFinal) {
            console.log('[ProgressTimeline] Received final event');
            this.handleCompletion(event, task.state);
        }
    }

    /**
     * Extract event information from A2A event.
     * @param {Object} metadata - Event metadata
     * @param {Object} taskStatusEvent - Task status event
     * @param {string} eventType - SSE event type
     * @returns {Object} Event info for timeline
     */
    extractEventInfo(metadata, taskStatusEvent, eventType) {
        const type = metadata.event_type || eventType || 'update';
        const payload = metadata.payload || {};
        const toolName = metadata.tool_name || payload.tool_name;

        // Get message from various possible locations
        let message = payload.message || payload.insight || '';
        if (taskStatusEvent.task?.messages?.length > 0) {
            const parts = taskStatusEvent.task.messages[0].parts || [];
            if (parts.length > 0 && parts[0].type === 'textPart') {
                message = parts[0].text || message;
            }
        }

        // Extract output_summary and duration_seconds for tool_completed events
        let outputSummary = null;
        let durationSeconds = null;
        if (type === 'tool_completed') {
            if (payload.output_summary) {
                outputSummary = this.cleanOutputSummary(payload.output_summary);
            }
            if (payload.duration_seconds !== undefined && payload.duration_seconds !== null) {
                durationSeconds = payload.duration_seconds;
            }
        }

        // Determine icon and color based on event type
        const { icon, color } = this.getEventStyle(type, payload);

        return {
            type,
            toolName,
            message: message || this.getDefaultMessage(type, toolName),
            timestamp: metadata.timestamp || new Date().toISOString(),
            icon,
            color,
            stage: payload.stage,
            confidence: payload.confidence,
            determination: payload.determination,
            outputSummary,
            durationSeconds,
        };
    }

    /**
     * Get icon and color for event type.
     * @param {string} type - Event type
     * @param {Object} payload - Event payload
     * @returns {Object} Icon and color
     */
    getEventStyle(type, payload = {}) {
        const styles = {
            'analysis_started': { icon: 'play', color: 'blue' },
            'tool_started': { icon: 'cog', color: 'blue' },
            'tool_progress': { icon: 'refresh', color: 'blue' },
            'tool_completed': { icon: 'check', color: 'green' },
            'analysis_complete': { icon: 'flag', color: 'green' },
            'complete': { icon: 'flag', color: 'green' },
            'error': { icon: 'exclamation', color: 'red' },
            'update': { icon: 'arrow-right', color: 'gray' },
            'connection': { icon: 'wifi', color: 'green' },
            'reconnecting': { icon: 'refresh', color: 'yellow' },
            // Orchestrator events
            'routing': { icon: 'arrow-right', color: 'purple' },
            'agent_handoff': { icon: 'play', color: 'purple' },
            // Agent events
            'agent_thinking': { icon: 'cog', color: 'indigo' },
        };

        // Special handling for determination in complete events
        if ((type === 'analysis_complete' || type === 'complete') && payload.determination) {
            if (payload.determination === 'ESCALATE') {
                return { icon: 'flag', color: 'red' };
            } else if (payload.determination === 'CLOSE') {
                return { icon: 'flag', color: 'green' };
            } else if (payload.determination === 'NEEDS_HUMAN_REVIEW') {
                return { icon: 'flag', color: 'yellow' };
            }
        }

        return styles[type] || { icon: 'dot', color: 'gray' };
    }

    /**
     * Get default message for event type.
     * @param {string} type - Event type
     * @param {string} toolName - Tool name if applicable
     * @returns {string} Default message
     */
    getDefaultMessage(type, toolName) {
        const messages = {
            'analysis_started': 'Starting alert analysis...',
            'tool_started': toolName ? `Running ${this.formatToolName(toolName)}...` : 'Running tool...',
            'tool_progress': toolName ? `${this.formatToolName(toolName)} processing...` : 'Processing...',
            'tool_completed': toolName ? `${this.formatToolName(toolName)} completed` : 'Tool completed',
            'analysis_complete': 'Analysis complete',
            'complete': 'Analysis complete',
            'error': 'An error occurred',
            'update': 'Processing...',
            // Orchestrator events
            'routing': 'Routing to specialized agent...',
            'agent_handoff': 'Handing off to agent...',
            // Agent events
            'agent_thinking': 'Agent is analyzing...',
        };
        return messages[type] || 'Processing...';
    }

    /**
     * Format tool name for display.
     * @param {string} name - Raw tool name
     * @returns {string} Formatted name
     */
    formatToolName(name) {
        if (!name) return 'Tool';
        return name
            .replace(/_/g, ' ')
            .replace(/([A-Z])/g, ' $1')
            .replace(/^\s+/, '')
            .split(' ')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
            .join(' ')
            .trim();
    }

    /**
     * Clean output summary by removing LangChain wrapper format.
     * @param {string} summary - Raw output summary
     * @returns {string|null} Cleaned summary text
     */
    cleanOutputSummary(summary) {
        if (!summary || typeof summary !== 'string') {
            return null;
        }

        let cleaned = summary.trim();

        // Remove "content='" prefix if present (LangChain format)
        if (cleaned.startsWith("content='")) {
            cleaned = cleaned.substring(9);
        }

        // Remove trailing quote if the string was truncated mid-content
        if (cleaned.endsWith("'")) {
            cleaned = cleaned.slice(0, -1);
        }

        // Trim again and return null if empty
        cleaned = cleaned.trim();
        return cleaned.length > 0 ? cleaned : null;
    }

    /**
     * Create DOM element for output summary display.
     * Uses a collapsible details element for better UX.
     * @param {string} summary - Cleaned output summary text
     * @param {number|null} durationSeconds - Tool execution duration
     * @returns {HTMLElement} Summary container element
     */
    createOutputSummaryElement(summary, durationSeconds) {
        const container = document.createElement('div');
        container.className = 'output-summary mt-2';

        // Create collapsible details element
        const details = document.createElement('details');
        details.className = 'output-summary-details';

        // Summary header (clickable) with duration
        const summaryHeader = document.createElement('summary');
        summaryHeader.className = 'output-summary-header text-xs text-blue-600 cursor-pointer hover:text-blue-800 flex items-center gap-1';

        // Build header text with optional duration
        let headerText = 'Tool result';
        if (durationSeconds !== null && durationSeconds !== undefined) {
            headerText += ` (${durationSeconds.toFixed(2)}s)`;
        }

        summaryHeader.innerHTML = `
            <svg class="output-summary-chevron w-3 h-3 transform transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
            </svg>
            <span>${headerText}</span>
        `;

        // Content (revealed when expanded)
        const contentDiv = document.createElement('div');
        contentDiv.className = 'output-summary-content mt-1 pl-4 text-xs text-gray-600 leading-relaxed border-l-2 border-gray-200';
        contentDiv.textContent = summary;

        details.appendChild(summaryHeader);
        details.appendChild(contentDiv);
        container.appendChild(details);

        return container;
    }

    /**
     * Add an event to the visual timeline.
     * @param {Object} eventInfo - Event information
     */
    addTimelineEvent(eventInfo) {
        // Create timeline item element
        const item = document.createElement('div');
        item.className = 'timeline-item flex items-start gap-3 py-3 animate-fade-in';
        item.setAttribute('role', 'listitem');

        // Icon container
        const iconContainer = document.createElement('div');
        iconContainer.className = `timeline-icon flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${this.getIconBgClass(eventInfo.color)}`;
        iconContainer.innerHTML = this.getIconSvg(eventInfo.icon, eventInfo.color);

        // Content container
        const content = document.createElement('div');
        content.className = 'timeline-content flex-1 min-w-0';

        // Message
        const message = document.createElement('p');
        message.className = 'text-sm text-gray-800 break-words';
        message.textContent = eventInfo.message;

        content.appendChild(message);

        // Output summary (for tool_completed events with summary data)
        if (eventInfo.outputSummary) {
            const summaryElement = this.createOutputSummaryElement(
                eventInfo.outputSummary,
                eventInfo.durationSeconds
            );
            content.appendChild(summaryElement);
        }

        // Meta info (timestamp, tool name)
        const meta = document.createElement('div');
        meta.className = 'flex items-center gap-2 mt-1';

        const timestamp = document.createElement('span');
        timestamp.className = 'text-xs text-gray-400';
        timestamp.textContent = this.formatTimestamp(eventInfo.timestamp);

        meta.appendChild(timestamp);

        if (eventInfo.toolName) {
            const toolBadge = document.createElement('span');
            toolBadge.className = 'text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded';
            toolBadge.textContent = this.formatToolName(eventInfo.toolName);
            meta.appendChild(toolBadge);
        }

        content.appendChild(meta);

        item.appendChild(iconContainer);
        item.appendChild(content);

        // Add to container
        if (this.container) {
            this.container.appendChild(item);
            // Scroll to bottom
            this.container.scrollTop = this.container.scrollHeight;
        }

        // Update elapsed time
        this.updateElapsedTime();
    }

    /**
     * Get background class for icon based on color.
     * @param {string} color - Color name
     * @returns {string} Tailwind CSS class
     */
    getIconBgClass(color) {
        const classes = {
            'blue': 'bg-blue-100',
            'green': 'bg-green-100',
            'red': 'bg-red-100',
            'yellow': 'bg-yellow-100',
            'gray': 'bg-gray-100',
            'purple': 'bg-purple-100',
            'indigo': 'bg-indigo-100',
        };
        return classes[color] || 'bg-gray-100';
    }

    /**
     * Get SVG icon markup.
     * @param {string} icon - Icon name
     * @param {string} color - Color name
     * @returns {string} SVG markup
     */
    getIconSvg(icon, color) {
        const colorClass = {
            'blue': 'text-blue-600',
            'green': 'text-green-600',
            'red': 'text-red-600',
            'yellow': 'text-yellow-600',
            'gray': 'text-gray-600',
            'purple': 'text-purple-600',
            'indigo': 'text-indigo-600',
        }[color] || 'text-gray-600';

        const icons = {
            'play': `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z"/></svg>`,
            'cog': `<svg class="w-4 h-4 ${colorClass} animate-spin-slow" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>`,
            'check': `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>`,
            'flag': `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M3 6a3 3 0 013-3h10a1 1 0 01.8 1.6L14.25 8l2.55 3.4A1 1 0 0116 13H6a1 1 0 00-1 1v3a1 1 0 11-2 0V6z" clip-rule="evenodd"/></svg>`,
            'exclamation': `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>`,
            'refresh': `<svg class="w-4 h-4 ${colorClass} animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>`,
            'wifi': `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M17.778 8.222c-4.296-4.296-11.26-4.296-15.556 0A1 1 0 01.808 6.808c5.076-5.077 13.308-5.077 18.384 0a1 1 0 01-1.414 1.414zM14.95 11.05a7 7 0 00-9.9 0 1 1 0 01-1.414-1.414 9 9 0 0112.728 0 1 1 0 01-1.414 1.414zM12.12 13.88a3 3 0 00-4.242 0 1 1 0 01-1.415-1.415 5 5 0 017.072 0 1 1 0 01-1.415 1.415zM9 16a1 1 0 011-1h.01a1 1 0 110 2H10a1 1 0 01-1-1z" clip-rule="evenodd"/></svg>`,
            'arrow-right': `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>`,
            'dot': `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><circle cx="10" cy="10" r="4"/></svg>`,
        };
        return icons[icon] || icons['dot'];
    }

    /**
     * Format timestamp for display.
     * @param {string} timestamp - ISO timestamp
     * @returns {string} Formatted timestamp
     */
    formatTimestamp(timestamp) {
        try {
            const date = new Date(timestamp);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        } catch (e) {
            return '';
        }
    }

    /**
     * Update elapsed time display.
     */
    updateElapsedTime() {
        const elapsedElement = document.getElementById('timeline-elapsed');
        if (elapsedElement) {
            const elapsed = Math.floor((Date.now() - this.startTime) / 1000);
            const minutes = Math.floor(elapsed / 60);
            const seconds = elapsed % 60;
            elapsedElement.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
        }
    }

    /**
     * Handle completion event.
     * @param {Object} event - Complete event
     * @param {string} state - Task state
     */
    handleCompletion(event, state) {
        console.log(`[ProgressTimeline] Analysis completed with state: ${state}`);

        // Close EventSource
        this.stop();

        // Extract decision from event if available
        const result = event.result || {};
        const metadata = result.metadata || {};
        const payload = metadata.payload || {};

        // Call completion callback
        this.onComplete({
            state,
            determination: payload.determination,
            confidence: payload.confidence,
            decision: payload.decision,
            raw: event,
        });
    }

    /**
     * Stop streaming and clean up.
     */
    stop() {
        console.log('[ProgressTimeline] Stopping');

        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }

        this.isConnected = false;
    }

    /**
     * Get all received events.
     * @returns {Array} All events
     */
    getEvents() {
        return [...this.events];
    }

    /**
     * Get connection status.
     * @returns {boolean} True if connected
     */
    isActive() {
        return this.isConnected && this.eventSource?.readyState === EventSource.OPEN;
    }
}

// Export for module systems and global access
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ProgressTimeline;
}
if (typeof window !== 'undefined') {
    window.ProgressTimeline = ProgressTimeline;
}
