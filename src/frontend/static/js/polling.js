/**
 * Polling functionality for SMARTS Alert Analyzer.
 *
 * Handles status polling for analysis tasks and
 * triggers result rendering when complete.
 */

// Polling configuration
const POLL_INTERVAL_MS = 2000;  // 2 seconds
const MAX_POLL_ATTEMPTS = 180;  // 6 minutes max (180 * 2s)

// State
let pollInterval = null;
let pollAttempts = 0;
let currentTaskId = null;

// Status messages to show during polling
const STATUS_MESSAGES = [
    'Sending alert to analysis agents...',
    'Reading alert data...',
    'Analyzing trading patterns...',
    'Running compliance tools...',
    'Evaluating market context...',
    'Checking trader history...',
    'Analyzing counterparty relationships...',
    'Generating decision...',
    'Finalizing analysis...',
];

/**
 * Start polling for task status.
 * @param {string} taskId - Task ID to poll
 */
function startPolling(taskId) {
    console.log('Starting polling for task:', taskId);

    currentTaskId = taskId;
    pollAttempts = 0;

    // Update status message periodically
    updateLoadingStatus();

    // Start polling
    pollInterval = setInterval(() => {
        pollStatus(taskId);
    }, POLL_INTERVAL_MS);

    // Also poll immediately
    pollStatus(taskId);
}

/**
 * Stop polling.
 */
function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
    currentTaskId = null;
    pollAttempts = 0;
    console.log('Polling stopped');
}

/**
 * Poll for task status.
 * @param {string} taskId - Task ID to check
 */
async function pollStatus(taskId) {
    pollAttempts++;
    console.log(`Poll attempt ${pollAttempts} for task ${taskId}`);

    // Check max attempts
    if (pollAttempts > MAX_POLL_ATTEMPTS) {
        stopPolling();
        showError('Analysis timed out. Please try again.');
        return;
    }

    try {
        const response = await fetch(`/api/status/${taskId}`);

        if (!response.ok) {
            if (response.status === 404) {
                stopPolling();
                showError('Task not found. Please try again.');
                return;
            }
            throw new Error('Failed to check status');
        }

        const data = await response.json();
        console.log('Status:', data.status);

        switch (data.status) {
            case 'processing':
                // Continue polling, update status message
                updateLoadingStatus();
                break;

            case 'complete':
                stopPolling();
                console.log('Analysis complete:', data);
                renderResults(data.decision, data.alert_type, taskId);
                showSection('results');
                break;

            case 'error':
                stopPolling();
                showError(data.message || 'Analysis failed. Please try again.');
                break;

            default:
                console.warn('Unknown status:', data.status);
        }

    } catch (error) {
        console.error('Poll error:', error);
        // Don't stop polling on transient errors, but count them
        if (pollAttempts > 5 && pollAttempts % 5 === 0) {
            // After 5 failed attempts, show a warning but continue
            showToast('Having trouble connecting to server...', 'warning');
        }
    }
}

/**
 * Update loading status message.
 */
function updateLoadingStatus() {
    const loadingStatus = document.getElementById('loading-status');
    if (loadingStatus) {
        // Cycle through status messages based on poll attempts
        const messageIndex = Math.min(
            Math.floor(pollAttempts / 3),
            STATUS_MESSAGES.length - 1
        );
        loadingStatus.textContent = STATUS_MESSAGES[messageIndex];
    }
}
