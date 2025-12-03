/**
 * Upload functionality for SMARTS Alert Analyzer.
 *
 * Handles drag-and-drop file upload, file validation,
 * XML preview, and form submission.
 */

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const filePreview = document.getElementById('file-preview');
const fileName = document.getElementById('file-name');
const fileSize = document.getElementById('file-size');
const xmlPreview = document.getElementById('xml-preview');
const clearFileBtn = document.getElementById('clear-file');
const analyzeBtn = document.getElementById('analyze-btn');
const uploadSection = document.getElementById('upload-section');
const loadingSection = document.getElementById('loading-section');
const resultsSection = document.getElementById('results-section');
const errorSection = document.getElementById('error-section');
const tryAgainBtn = document.getElementById('try-again-btn');

// State
let selectedFile = null;

/**
 * Initialize upload handlers.
 */
function initUpload() {
    // Drag and drop handlers
    dropZone.addEventListener('dragover', handleDragOver);
    dropZone.addEventListener('dragleave', handleDragLeave);
    dropZone.addEventListener('drop', handleDrop);

    // File input handler
    fileInput.addEventListener('change', handleFileSelect);

    // Clear file handler
    clearFileBtn.addEventListener('click', clearFile);

    // Analyze button handler
    analyzeBtn.addEventListener('click', submitAnalysis);

    // Try again handler
    tryAgainBtn.addEventListener('click', resetToUpload);

    console.log('Upload handlers initialized');
}

/**
 * Handle drag over event.
 * @param {DragEvent} e - Drag event
 */
function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.add('border-blue-500', 'bg-blue-50');
}

/**
 * Handle drag leave event.
 * @param {DragEvent} e - Drag event
 */
function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove('border-blue-500', 'bg-blue-50');
}

/**
 * Handle file drop event.
 * @param {DragEvent} e - Drop event
 */
function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove('border-blue-500', 'bg-blue-50');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        processFile(files[0]);
    }
}

/**
 * Handle file input selection.
 * @param {Event} e - Change event
 */
function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        processFile(files[0]);
    }
}

/**
 * Process and validate selected file.
 * @param {File} file - Selected file
 */
function processFile(file) {
    // Validate file extension
    if (!file.name.toLowerCase().endsWith('.xml')) {
        showToast('Please upload an XML file', 'error');
        return;
    }

    selectedFile = file;
    console.log('File selected:', file.name);

    // Update file info
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);

    // Read and preview file content
    const reader = new FileReader();
    reader.onload = (e) => {
        const content = e.target.result;
        xmlPreview.textContent = content;
        filePreview.classList.remove('hidden');
        dropZone.classList.add('hidden');
    };
    reader.readAsText(file);
}

/**
 * Format file size for display.
 * @param {number} bytes - File size in bytes
 * @returns {string} Formatted file size
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Clear selected file.
 */
function clearFile() {
    selectedFile = null;
    fileInput.value = '';
    filePreview.classList.add('hidden');
    dropZone.classList.remove('hidden');
    console.log('File cleared');
}

/**
 * Submit file for analysis.
 */
async function submitAnalysis() {
    if (!selectedFile) {
        showToast('Please select a file first', 'error');
        return;
    }

    console.log('Submitting file for analysis:', selectedFile.name);

    // Show loading state
    showSection('loading');

    // Create form data
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to submit analysis');
        }

        const data = await response.json();
        console.log('Analysis started, task_id:', data.task_id);

        // Start polling for results
        startPolling(data.task_id);

    } catch (error) {
        console.error('Submit error:', error);
        showError(error.message);
    }
}

/**
 * Show a specific section and hide others.
 * @param {string} section - Section to show: 'upload', 'loading', 'results', 'error'
 */
function showSection(section) {
    uploadSection.classList.add('hidden');
    loadingSection.classList.add('hidden');
    resultsSection.classList.add('hidden');
    errorSection.classList.add('hidden');

    switch (section) {
        case 'upload':
            uploadSection.classList.remove('hidden');
            break;
        case 'loading':
            loadingSection.classList.remove('hidden');
            break;
        case 'results':
            resultsSection.classList.remove('hidden');
            break;
        case 'error':
            errorSection.classList.remove('hidden');
            break;
    }
}

/**
 * Show error section with message.
 * @param {string} message - Error message
 */
function showError(message) {
    const errorMessage = document.getElementById('error-message');
    errorMessage.textContent = message;
    showSection('error');
}

/**
 * Reset to upload state.
 */
function resetToUpload() {
    clearFile();
    showSection('upload');
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initUpload);
