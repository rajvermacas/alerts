import { createLogger } from './logger.js';

const logger = createLogger('timeline_renderer');

function requireElementById(id) {
    const element = document.getElementById(id);
    if (!element) {
        throw new Error(`timeline_renderer: missing required element #${id}`);
    }
    return element;
}

function requireSupportedColor(color) {
    const supported = new Set(['blue', 'green', 'red', 'yellow', 'gray', 'purple', 'indigo']);
    if (!supported.has(color)) {
        throw new Error(`timeline_renderer: unsupported color '${color}'`);
    }
    return color;
}

function getIconBgClass(color) {
    requireSupportedColor(color);
    return {
        blue: 'bg-blue-100',
        green: 'bg-green-100',
        red: 'bg-red-100',
        yellow: 'bg-yellow-100',
        gray: 'bg-gray-100',
        purple: 'bg-purple-100',
        indigo: 'bg-indigo-100',
    }[color];
}

function getIconSvg(icon, color) {
    requireSupportedColor(color);
    const colorClass = {
        blue: 'text-blue-600',
        green: 'text-green-600',
        red: 'text-red-600',
        yellow: 'text-yellow-600',
        gray: 'text-gray-600',
        purple: 'text-purple-600',
        indigo: 'text-indigo-600',
    }[color];

    const icons = {
        play: `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z"/></svg>`,
        cog: `<svg class="w-4 h-4 ${colorClass}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>`,
        check: `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>`,
        flag: `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M3 6a3 3 0 013-3h10a1 1 0 01.8 1.6L14.25 8l2.55 3.4A1 1 0 0116 13H6a1 1 0 00-1 1v3a1 1 0 11-2 0V6z" clip-rule="evenodd"/></svg>`,
        exclamation: `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>`,
        refresh: `<svg class="w-4 h-4 ${colorClass}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>`,
        wifi: `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M17.778 8.222c-4.296-4.296-11.26-4.296-15.556 0A1 1 0 01.808 6.808c5.076-5.077 13.308-5.077 18.384 0a1 1 0 01-1.414 1.414zM14.95 11.05a7 7 0 00-9.9 0 1 1 0 01-1.414-1.414 9 9 0 0112.728 0 1 1 0 01-1.414 1.414zM12.12 13.88a3 3 0 00-4.242 0 1 1 0 01-1.415-1.415 5 5 0 017.072 0 1 1 0 01-1.415 1.415zM9 16a1 1 0 011-1h.01a1 1 0 110 2H10a1 1 0 01-1-1z" clip-rule="evenodd"/></svg>`,
        'arrow-right': `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>`,
        dot: `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><circle cx="10" cy="10" r="4"/></svg>`,
        document: `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clip-rule="evenodd"/></svg>`,
        scale: `<svg class="w-4 h-4 ${colorClass}" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 2a1 1 0 011 1v1.323l3.954 1.582 1.599-.8a1 1 0 01.894 1.79l-1.233.616 1.738 5.42a1 1 0 01-.285 1.05A3.989 3.989 0 0115 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.715-5.349L11 6.477V16h2a1 1 0 110 2H7a1 1 0 110-2h2V6.477L6.237 7.582l1.715 5.349a1 1 0 01-.285 1.05A3.989 3.989 0 015 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.738-5.42-1.233-.617a1 1 0 01.894-1.788l1.599.799L9 4.323V3a1 1 0 011-1z" clip-rule="evenodd"/></svg>`,
    };

    const svg = icons[icon];
    if (!svg) {
        throw new Error(`timeline_renderer: unsupported icon '${icon}'`);
    }
    return svg;
}

function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
        throw new Error('timeline_renderer: invalid timestamp');
    }
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function createOutputSummaryElement(summary, durationSeconds) {
    if (typeof summary !== 'string') {
        throw new Error('timeline_renderer: outputSummary (string) is required when provided');
    }
    if (durationSeconds !== undefined && typeof durationSeconds !== 'number') {
        throw new Error('timeline_renderer: durationSeconds (number) is required when provided');
    }

    const details = document.createElement('details');
    details.className = 'mt-2 bg-gray-50 rounded-md px-3 py-2 border border-gray-200';

    const summaryEl = document.createElement('summary');
    summaryEl.className = 'cursor-pointer text-xs font-medium text-gray-700 flex items-center gap-2 select-none';

    const headerText = durationSeconds !== undefined
        ? `Tool result (${durationSeconds.toFixed(2)}s)`
        : 'Tool result';

    summaryEl.innerHTML = `
        <svg class="w-3 h-3 transform transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
        </svg>
        <span>${headerText}</span>
    `;

    const content = document.createElement('div');
    content.className = 'mt-1 pl-4 text-xs text-gray-600 leading-relaxed border-l-2 border-gray-200 whitespace-pre-wrap';
    content.textContent = summary;

    details.appendChild(summaryEl);
    details.appendChild(content);
    details.addEventListener('toggle', () => {
        const chevron = summaryEl.querySelector('svg');
        if (!chevron) {
            throw new Error('timeline_renderer: missing chevron');
        }
        chevron.style.transform = details.open ? 'rotate(90deg)' : 'rotate(0deg)';
    });

    return details;
}

export class TimelineRenderer {
    constructor() {
        this.container = requireElementById('progress-timeline');
        this.container.innerHTML = '';
        this._toolNames = new Set();
        this._eventCount = 0;
        logger.info('initialized');
    }

    _getItemStateClass(eventType) {
        if (typeof eventType !== 'string' || eventType.trim().length === 0) {
            throw new Error('timeline_renderer: eventType (non-empty string) is required');
        }

        if (eventType === 'error') return 'error';
        if (eventType.endsWith('_complete') || eventType.endsWith('_completed') || eventType === 'complete') return 'completed';
        if (eventType.endsWith('_started') || eventType.endsWith('_progress') || eventType === 'routing') return 'active';
        return '';
    }

    addEvent(eventInfo) {
        const item = document.createElement('div');
        const stateClass = this._getItemStateClass(eventInfo.type);
        item.className = `timeline-item flex items-start gap-3 py-3 animate-fade-in ${stateClass}`;
        item.setAttribute('role', 'listitem');

        const iconContainer = document.createElement('div');
        iconContainer.className = `timeline-icon flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${getIconBgClass(eventInfo.color)}`;
        iconContainer.innerHTML = getIconSvg(eventInfo.icon, eventInfo.color);

        const content = document.createElement('div');
        content.className = 'timeline-content flex-1 min-w-0';

        const message = document.createElement('p');
        message.className = 'text-sm text-gray-800 break-words';
        message.textContent = eventInfo.message;
        content.appendChild(message);

        if (eventInfo.outputSummary) {
            content.appendChild(createOutputSummaryElement(eventInfo.outputSummary, eventInfo.durationSeconds));
        }

        const meta = document.createElement('div');
        meta.className = 'flex items-center gap-2 mt-1';

        const ts = document.createElement('span');
        ts.className = 'text-xs text-gray-400';
        ts.textContent = formatTimestamp(eventInfo.timestamp);
        meta.appendChild(ts);

        if (eventInfo.toolName) {
            const toolBadge = document.createElement('span');
            toolBadge.className = 'text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono';
            toolBadge.textContent = eventInfo.toolName;
            meta.appendChild(toolBadge);
        }

        if (eventInfo.agentName) {
            const agentBadge = document.createElement('span');
            agentBadge.className = 'text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded';
            agentBadge.textContent = eventInfo.agentName;
            meta.appendChild(agentBadge);
        }

        content.appendChild(meta);
        item.appendChild(iconContainer);
        item.appendChild(content);

        this.container.appendChild(item);
        this.container.scrollTop = this.container.scrollHeight;

        this._eventCount += 1;
        if (eventInfo.type === 'tool_completed' && eventInfo.toolName) {
            this._toolNames.add(eventInfo.toolName);
        }

        this._updateStats();
    }

    _updateStats() {
        const eventCount = requireElementById('timeline-event-count');
        const toolCount = requireElementById('timeline-tool-count');

        eventCount.textContent = `${this._eventCount} events`;
        toolCount.textContent = `${this._toolNames.size} tools executed`;
    }
}
