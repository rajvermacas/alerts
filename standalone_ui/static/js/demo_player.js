import { createLogger } from './logger.js';
import { loadSpecFromDom } from './spec_loader.js';
import { TimelineRenderer } from './timeline_renderer.js';
import { DAGRenderer } from './dag_renderer.js';
import { renderCardsIntoResults } from './cards_renderer.js';
import { initRelationshipNetwork } from './network_graph.js';

const logger = createLogger('demo_player');

function requireElementById(id) {
    const el = document.getElementById(id);
    if (!el) {
        throw new Error(`demo_player: missing required element #${id}`);
    }
    return el;
}

function sleep(ms) {
    if (typeof ms !== 'number' || Number.isNaN(ms) || ms < 0) {
        throw new Error('demo_player: sleep(ms>=0) requires a non-negative number');
    }
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function setHeaderComplete() {
    const spinnerContainer = requireElementById('timeline-spinner-container');
    spinnerContainer.innerHTML = `
        <div class="inline-flex items-center justify-center h-8 w-8 rounded-full bg-green-100">
            <svg class="h-5 w-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
            </svg>
        </div>
    `;

    const title = requireElementById('timeline-header-title');
    title.textContent = 'Demo complete';

    const status = requireElementById('loading-status');
    status.textContent = 'Rendered results from JSON.';
}

function startElapsedTimer() {
    const start = Date.now();
    const el = requireElementById('timeline-elapsed');

    const intervalId = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - start) / 1000);
        const minutes = Math.floor(elapsed / 60);
        const seconds = elapsed % 60;
        el.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }, 250);

    return () => window.clearInterval(intervalId);
}

function showError(err) {
    const errorSection = requireElementById('error-section');
    const errorMessage = requireElementById('error-message');
    errorMessage.textContent = err instanceof Error ? err.message : String(err);
    errorSection.classList.remove('hidden');
}

function showResults() {
    const results = requireElementById('results-section');
    results.classList.remove('hidden');
}

function setPageHeader(page) {
    const appTitle = requireElementById('app-title');
    const subtitle = requireElementById('app-subtitle');
    const headerTitle = requireElementById('timeline-header-title');

    appTitle.textContent = page.appTitle;
    subtitle.textContent = page.subtitle;
    headerTitle.textContent = page.pageTitle;
    document.title = `${page.pageTitle} - ${page.appTitle}`;
}

function renderRelationshipNetworkIfPresent(graphs) {
    if (!graphs || !graphs.relationshipNetwork) {
        return;
    }

    const rn = graphs.relationshipNetwork;
    const results = requireElementById('results-section');
    const section = document.createElement('div');
    section.className = 'bg-white rounded-lg shadow-md p-6';
    section.innerHTML = `
        <h3 class="text-lg font-semibold text-gray-900 mb-4">${rn.title}</h3>
        <div class="bg-gray-50 rounded-lg p-2 mb-4">
            <div id="cytoscape-container" class="w-full h-96 border border-gray-200 rounded-lg"></div>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div class="bg-gray-50 rounded p-3">
                <p class="text-gray-500">Pattern Type</p>
                <p class="font-medium text-gray-900">${rn.patternType}</p>
            </div>
            <div class="bg-gray-50 rounded p-3">
                <p class="text-gray-500">Pattern Confidence</p>
                <p class="font-medium text-gray-900">${rn.patternConfidence}%</p>
            </div>
            <div class="bg-gray-50 rounded p-3">
                <p class="text-gray-500">Nodes</p>
                <p class="font-medium text-gray-900">${rn.nodes.length}</p>
            </div>
            <div class="bg-gray-50 rounded p-3">
                <p class="text-gray-500">Edges</p>
                <p class="font-medium text-gray-900">${rn.edges.length}</p>
            </div>
        </div>
        <p class="text-sm text-gray-600 mt-4">${rn.patternDescription}</p>
    `;
    results.appendChild(section);

    initRelationshipNetwork('cytoscape-container', rn);
}

async function initDemo() {
    try {
        const spec = await loadSpecFromDom();
        setPageHeader(spec.page);

        const timeline = new TimelineRenderer();

        // State for playback
        let stopElapsed = null;

        // Callback when Start node is clicked
        const onStartClick = async () => {
            stopElapsed = startElapsedTimer();
            const status = requireElementById('loading-status');
            status.textContent = 'Playing demo timeline…';

            try {
                for (let i = 0; i < spec.timeline.events.length; i += 1) {
                    const evt = spec.timeline.events[i];
                    await sleep(evt.delayMs);
                    timeline.addEvent(evt);
                    dag.handleEvent(evt);
                }

                stopElapsed();
                setHeaderComplete();

                showResults();
                renderCardsIntoResults(spec.cards);
                renderRelationshipNetworkIfPresent(spec.graphs);

                logger.info('demo complete');
            } catch (err) {
                if (stopElapsed) {
                    stopElapsed();
                }
                logger.error('demo playback failed', err);
                showError(err);
                throw err;
            }
        };

        // Initialize DAG with the start callback
        const dag = new DAGRenderer(spec.executionFlow, onStartClick);

        // Update status to indicate ready state
        const status = requireElementById('loading-status');
        status.textContent = 'Click "Start" in the execution flow to begin.';

        const headerTitle = requireElementById('timeline-header-title');
        headerTitle.textContent = 'Ready to start';

        logger.info('demo initialized, waiting for start click');
    } catch (err) {
        logger.error('demo init failed', err);
        showError(err);
        throw err;
    }
}

function bindReload() {
    const btn = requireElementById('try-again-btn');
    btn.addEventListener('click', () => window.location.reload());
}

bindReload();
initDemo();
