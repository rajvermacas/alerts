import { createLogger } from './logger.js';

const logger = createLogger('modal');

function requireElementById(id) {
    const el = document.getElementById(id);
    if (!el) {
        throw new Error(`modal: missing required element #${id}`);
    }
    return el;
}

function buildModalMarkup() {
    return `
        <div class="tool-result-modal-content" role="dialog" aria-modal="true" aria-label="Tool result">
            <div class="tool-result-modal-header">
                <h3 id="tool-result-title" class="text-sm font-semibold text-gray-900"></h3>
                <button class="tool-result-modal-close" aria-label="Close">&times;</button>
            </div>
            <div class="tool-result-modal-body">
                <div id="tool-result-duration" class="text-xs text-gray-500 mb-2"></div>
                <div id="tool-result-output"></div>
            </div>
        </div>
    `;
}

export class ToolResultModal {
    constructor() {
        this.root = requireElementById('tool-result-modal');
        this.root.innerHTML = buildModalMarkup();

        const closeBtn = this.root.querySelector('.tool-result-modal-close');
        if (!closeBtn) {
            throw new Error('modal: missing close button');
        }
        closeBtn.addEventListener('click', () => this.hide());

        this.root.addEventListener('click', (e) => {
            if (e.target === this.root) {
                this.hide();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isShown()) {
                this.hide();
            }
        });

        logger.info('initialized');
    }

    isShown() {
        return this.root.classList.contains('show');
    }

    show(toolName, outputSummary, durationSeconds) {
        if (typeof toolName !== 'string' || toolName.trim().length === 0) {
            throw new Error('modal: toolName (non-empty string) is required');
        }
        if (typeof outputSummary !== 'string' || outputSummary.trim().length === 0) {
            throw new Error('modal: outputSummary (non-empty string) is required');
        }
        if (durationSeconds !== undefined && typeof durationSeconds !== 'number') {
            throw new Error('modal: durationSeconds (number) is required when provided');
        }

        const title = requireElementById('tool-result-title');
        const duration = requireElementById('tool-result-duration');
        const output = requireElementById('tool-result-output');

        title.textContent = `[Tool] ${toolName}`;
        duration.textContent = durationSeconds !== undefined ? `Duration: ${durationSeconds.toFixed(2)}s` : '';
        output.textContent = outputSummary;

        this.root.classList.add('show');
        this.root.setAttribute('aria-hidden', 'false');
        logger.info('show', { toolName });
    }

    hide() {
        this.root.classList.remove('show');
        this.root.setAttribute('aria-hidden', 'true');
        logger.info('hide');
    }
}

