/**
 * Streaming integration for SMARTS Alert Analyzer.
 *
 * This module integrates the ProgressTimeline class with the upload flow,
 * providing real-time streaming updates via Server-Sent Events (SSE).
 *
 * Features:
 * - SSE streaming with fail-fast error handling
 * - UI state management for timeline
 * - Event counting and statistics
 * - Connection status display
 *
 * Note: This implementation uses fail-fast error handling.
 * If streaming fails, an error is shown to the user immediately.
 * No polling fallback is provided.
 */

// Global state for streaming
let currentTimeline = null;
let eventCount = 0;
let toolCount = 0;
let elapsedInterval = null;
let startTime = null;

/**
 * Start streaming analysis for a task.
 * Uses SSE for real-time progress updates.
 *
 * @param {string} taskId - Task ID to stream events for
 * @throws {Error} If streaming prerequisites are not met
 */
function startStreaming(taskId) {
    console.log('[Streaming] Starting streaming for task:', taskId);

    // Fail fast if EventSource is not supported
    if (!window.EventSource) {
        const errorMsg = 'Your browser does not support real-time streaming. Please use a modern browser (Chrome, Firefox, Safari, or Edge).';
        console.error('[Streaming] EventSource not supported');
        showError(errorMsg);
        throw new Error(errorMsg);
    }

    // Fail fast if ProgressTimeline is not available
    if (!window.ProgressTimeline) {
        const errorMsg = 'Streaming component failed to load. Please refresh the page.';
        console.error('[Streaming] ProgressTimeline not available');
        showError(errorMsg);
        throw new Error(errorMsg);
    }

    // Reset state
    resetTimelineState();

    // Get timeline container - fail fast if not found
    const timelineContainer = document.getElementById('progress-timeline');
    if (!timelineContainer) {
        const errorMsg = 'Failed to initialize progress display. Please refresh the page.';
        console.error('[Streaming] Timeline container not found');
        showError(errorMsg);
        throw new Error(errorMsg);
    }

    // Clear placeholder content
    timelineContainer.innerHTML = '';

    // Create and start timeline
    currentTimeline = new ProgressTimeline({
        taskId: taskId,
        container: timelineContainer,
        onComplete: handleStreamingComplete,
        onError: handleStreamingError,
        onProgress: handleProgressEvent,
        reconnectDelay: 3000,
        maxReconnectAttempts: 5,
    });

    // Update connection status to connecting
    updateConnectionStatus('connecting');

    // Start elapsed time counter
    startElapsedTimer();

    // Start the timeline
    try {
        currentTimeline.start();
    } catch (error) {
        console.error('[Streaming] Failed to start timeline:', error);
        stopElapsedTimer();
        currentTimeline = null;
        throw error;
    }

    // Update connection status when connected
    setTimeout(() => {
        if (currentTimeline && currentTimeline.isActive()) {
            updateConnectionStatus('connected');
        }
    }, 500);
}

/**
 * Handle streaming completion.
 *
 * @param {Object} result - Completion result from timeline
 */
function handleStreamingComplete(result) {
    console.log('[Streaming] Analysis complete:', result);

    // Stop elapsed timer
    stopElapsedTimer();

    // Update connection status
    updateConnectionStatus('disconnected');

    // Extract decision data
    const decision = result.decision || result.raw?.result?.metadata?.payload?.decision;
    const determination = result.determination || decision?.determination;
    const alertType = result.alertType || result.raw?.result?.metadata?.payload?.alert_type || 'unknown';

    if (decision) {
        console.log('[Streaming] Rendering results');

        // Get task ID from timeline
        const taskId = currentTimeline?.taskId;

        // Render results using existing results.js function
        if (typeof renderResults === 'function') {
            renderResults(decision, alertType, taskId);
            showSection('results');
        } else {
            console.error('[Streaming] renderResults function not found');
            showError('Failed to render results. Please refresh the page.');
        }
    } else if (result.state === 'failed') {
        console.error('[Streaming] Analysis failed');
        showError('Analysis failed. Please try again.');
    } else {
        // Try to fetch result from status endpoint
        fetchFinalResult(currentTimeline?.taskId);
    }

    // Cleanup
    currentTimeline = null;
}

/**
 * Handle streaming error.
 * Fail-fast: Shows error to user immediately, no fallback.
 *
 * @param {string} errorMessage - Error message
 */
function handleStreamingError(errorMessage) {
    console.error('[Streaming] Error:', errorMessage);

    // Stop elapsed timer
    stopElapsedTimer();

    // Update connection status
    updateConnectionStatus('disconnected');

    // Show error to user - fail fast, no fallback
    showError(errorMessage);

    // Cleanup
    if (currentTimeline) {
        currentTimeline.stop();
        currentTimeline = null;
    }
}

/**
 * Handle individual progress events.
 *
 * @param {Object} eventInfo - Event information from timeline
 */
function handleProgressEvent(eventInfo) {
    // Update event count
    eventCount++;
    updateEventCount();

    // Count tool completions
    if (eventInfo.type === 'tool_completed') {
        toolCount++;
        updateToolCount();
    }

    // Update loading status text
    updateLoadingStatusText(eventInfo.message);

    // Update connection status if we received an event
    if (currentTimeline?.isActive()) {
        updateConnectionStatus('connected');
    }
}

/**
 * Fetch final result from status endpoint.
 * Used when streaming completes but doesn't provide full decision.
 *
 * @param {string} taskId - Task ID
 */
async function fetchFinalResult(taskId) {
    if (!taskId) {
        showError('No task ID available. Please try again.');
        return;
    }

    try {
        const response = await fetch(`/api/status/${taskId}`);
        if (!response.ok) {
            throw new Error(`Server returned status ${response.status}`);
        }

        const data = await response.json();

        if (data.status === 'complete' && data.decision) {
            renderResults(data.decision, data.alert_type, taskId);
            showSection('results');
        } else if (data.status === 'error') {
            showError(data.message || 'Analysis failed. Please try again.');
        } else if (data.status === 'processing') {
            // Still processing - this shouldn't happen if streaming completed
            showError('Analysis is still in progress. Please wait and refresh the page.');
        } else {
            showError('Unexpected response from server. Please try again.');
        }
    } catch (error) {
        console.error('[Streaming] Failed to fetch final result:', error);
        showError('Failed to retrieve results. Please try again.');
    }
}

/**
 * Reset timeline state.
 */
function resetTimelineState() {
    eventCount = 0;
    toolCount = 0;

    updateEventCount();
    updateToolCount();

    // Reset connection status
    updateConnectionStatus('connecting');
}

/**
 * Update event count display.
 */
function updateEventCount() {
    const element = document.getElementById('timeline-event-count');
    if (element) {
        element.textContent = `${eventCount} event${eventCount !== 1 ? 's' : ''}`;
    }
}

/**
 * Update tool count display.
 */
function updateToolCount() {
    const element = document.getElementById('timeline-tool-count');
    if (element) {
        element.textContent = `${toolCount} tool${toolCount !== 1 ? 's' : ''} executed`;
    }
}

/**
 * Update loading status text.
 *
 * @param {string} message - Status message
 */
function updateLoadingStatusText(message) {
    const element = document.getElementById('loading-status');
    if (element && message) {
        element.textContent = message;
    }
}

/**
 * Update connection status indicator.
 *
 * @param {string} status - Status: 'connecting', 'connected', 'disconnected'
 */
function updateConnectionStatus(status) {
    const container = document.getElementById('connection-status');
    const text = document.getElementById('connection-status-text');

    if (!container || !text) return;

    // Remove all status classes
    container.classList.remove('connecting', 'connected', 'disconnected');

    // Add new status class
    container.classList.add(status);

    // Update text
    const statusText = {
        'connecting': 'Connecting',
        'connected': 'Connected',
        'disconnected': 'Disconnected',
    };
    text.textContent = statusText[status] || status;
}

/**
 * Start the elapsed time counter.
 */
function startElapsedTimer() {
    startTime = Date.now();

    // Clear any existing interval
    stopElapsedTimer();

    // Update every second
    elapsedInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const minutes = Math.floor(elapsed / 60);
        const seconds = elapsed % 60;

        const element = document.getElementById('timeline-elapsed');
        if (element) {
            element.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
        }
    }, 1000);
}

/**
 * Stop the elapsed time counter.
 */
function stopElapsedTimer() {
    if (elapsedInterval) {
        clearInterval(elapsedInterval);
        elapsedInterval = null;
    }
}

/**
 * Stop streaming and cleanup.
 */
function stopStreaming() {
    console.log('[Streaming] Stopping streaming');

    if (currentTimeline) {
        currentTimeline.stop();
        currentTimeline = null;
    }

    stopElapsedTimer();
}

/**
 * Override the default startPolling to use streaming.
 * This maintains API compatibility with upload.js which calls startPolling.
 * Streaming is the only mode - no polling fallback.
 */
(function() {
    window.startPolling = function(taskId) {
        console.log('[Streaming] startPolling called for task:', taskId);
        startStreaming(taskId);
    };
})();

// Export for testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        startStreaming,
        stopStreaming,
        handleStreamingComplete,
        handleStreamingError,
        handleProgressEvent,
    };
}
