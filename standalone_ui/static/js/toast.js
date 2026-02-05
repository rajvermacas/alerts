import { createLogger } from './logger.js';

const logger = createLogger('toast');

function requireElementById(id) {
    const element = document.getElementById(id);
    if (!element) {
        throw new Error(`toast: missing required element #${id}`);
    }
    return element;
}

export function showToast(message, type) {
    if (typeof message !== 'string') {
        throw new Error('toast: message (string) is required');
    }
    if (typeof type !== 'string' || type.trim().length === 0) {
        throw new Error('toast: type (non-empty string) is required');
    }

    const container = requireElementById('toast-container');
    const toast = document.createElement('div');

    const colors = {
        info: 'bg-blue-500',
        success: 'bg-green-500',
        error: 'bg-red-500',
        warning: 'bg-yellow-500',
    };

    const colorClass = colors[type];
    if (!colorClass) {
        throw new Error(`toast: unsupported type '${type}'`);
    }

    toast.className = `${colorClass} text-white px-6 py-3 rounded-lg shadow-lg transform transition-all duration-300 ease-in-out`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => toast.classList.add('translate-y-0', 'opacity-100'), 10);
    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-2');
        setTimeout(() => toast.remove(), 300);
    }, 4500);

    logger.info('toast', { type, length: message.length });
}

