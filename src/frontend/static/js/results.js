/**
 * Results rendering for SMARTS Alert Analyzer.
 *
 * Handles rendering of analysis results including:
 * - Common decision fields (determination, confidence, findings)
 * - Insider trading specific sections
 * - Wash trade specific sections with Cytoscape.js graphs
 */

/**
 * Render analysis results.
 * @param {Object} decision - Decision JSON from analysis
 * @param {string} alertType - Type of alert (insider_trading, wash_trade)
 * @param {string} taskId - Task ID for download links
 */
function renderResults(decision, alertType, taskId) {
    console.log('Rendering results:', alertType, decision);

    const resultsSection = document.getElementById('results-section');
    resultsSection.innerHTML = '';

    // Create main container
    const container = document.createElement('div');
    container.className = 'space-y-6';

    // Header with determination
    container.appendChild(renderHeader(decision, alertType));

    // Confidence scores
    container.appendChild(renderConfidenceScores(decision));

    // Key findings
    container.appendChild(renderKeyFindings(decision));

    // Favorable indicators and risk factors (side by side)
    container.appendChild(renderIndicatorsAndFactors(decision));

    // Alert-type specific sections
    if (alertType === 'insider_trading' || alertType === 'INSIDER_TRADING') {
        container.appendChild(renderInsiderTradingSections(decision));
    } else if (alertType === 'wash_trade' || alertType === 'WASH_TRADE') {
        container.appendChild(renderWashTradeSections(decision));
    }

    // Reasoning narrative
    container.appendChild(renderReasoning(decision));

    // Similar precedent
    if (decision.similar_precedent) {
        container.appendChild(renderPrecedent(decision));
    }

    // Download buttons
    container.appendChild(renderDownloadButtons(taskId));

    // New analysis button
    container.appendChild(renderNewAnalysisButton());

    resultsSection.appendChild(container);

    // Initialize Cytoscape graph if wash trade
    if ((alertType === 'wash_trade' || alertType === 'WASH_TRADE') && decision.relationship_network) {
        setTimeout(() => {
            initCytoscapeGraph(decision.relationship_network);
        }, 100);
    }
}

/**
 * Render header with determination badge.
 * @param {Object} decision - Decision object
 * @param {string} alertType - Alert type
 * @returns {HTMLElement} Header element
 */
function renderHeader(decision, alertType) {
    const header = document.createElement('div');
    header.className = 'bg-white rounded-lg shadow-md p-6';

    const determination = decision.determination || 'UNKNOWN';
    const badgeColors = {
        'ESCALATE': 'bg-red-100 text-red-800 border-red-300',
        'CLOSE': 'bg-green-100 text-green-800 border-green-300',
        'NEEDS_HUMAN_REVIEW': 'bg-yellow-100 text-yellow-800 border-yellow-300',
    };
    const badgeColor = badgeColors[determination] || 'bg-gray-100 text-gray-800 border-gray-300';

    const alertTypeDisplay = alertType.replace('_', ' ').toUpperCase();

    header.innerHTML = `
        <div class="flex items-center justify-between">
            <div>
                <h2 class="text-2xl font-bold text-gray-900">Analysis Complete</h2>
                <p class="text-gray-600 mt-1">${alertTypeDisplay} Alert Analysis</p>
            </div>
            <div class="text-right">
                <span class="inline-block px-4 py-2 rounded-full border-2 text-lg font-bold ${badgeColor}">
                    ${determination}
                </span>
            </div>
        </div>
    `;

    return header;
}

/**
 * Render confidence score bars.
 * @param {Object} decision - Decision object
 * @returns {HTMLElement} Confidence section
 */
function renderConfidenceScores(decision) {
    const section = document.createElement('div');
    section.className = 'bg-white rounded-lg shadow-md p-6';

    const genuine = decision.genuine_alert_confidence || 0;
    const falsePositive = decision.false_positive_confidence || 0;

    section.innerHTML = `
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Confidence Scores</h3>
        <div class="space-y-4">
            <div>
                <div class="flex justify-between mb-1">
                    <span class="text-sm font-medium text-gray-700">Genuine Alert Confidence</span>
                    <span class="text-sm font-bold text-gray-900">${genuine}%</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-3">
                    <div class="bg-red-500 h-3 rounded-full transition-all duration-500" style="width: ${genuine}%"></div>
                </div>
            </div>
            <div>
                <div class="flex justify-between mb-1">
                    <span class="text-sm font-medium text-gray-700">False Positive Confidence</span>
                    <span class="text-sm font-bold text-gray-900">${falsePositive}%</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-3">
                    <div class="bg-green-500 h-3 rounded-full transition-all duration-500" style="width: ${falsePositive}%"></div>
                </div>
            </div>
        </div>
    `;

    return section;
}

/**
 * Render key findings list.
 * @param {Object} decision - Decision object
 * @returns {HTMLElement} Findings section
 */
function renderKeyFindings(decision) {
    const section = document.createElement('div');
    section.className = 'bg-white rounded-lg shadow-md p-6';

    const findings = decision.key_findings || [];

    section.innerHTML = `
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Key Findings</h3>
        <ul class="space-y-2">
            ${findings.map(finding => `
                <li class="flex items-start">
                    <svg class="h-5 w-5 text-blue-500 mr-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                    </svg>
                    <span class="text-gray-700">${escapeHtml(finding)}</span>
                </li>
            `).join('')}
        </ul>
    `;

    return section;
}

/**
 * Render favorable indicators and risk factors side by side.
 * @param {Object} decision - Decision object
 * @returns {HTMLElement} Two-column section
 */
function renderIndicatorsAndFactors(decision) {
    const section = document.createElement('div');
    section.className = 'grid grid-cols-1 md:grid-cols-2 gap-6';

    const favorable = decision.favorable_indicators || [];
    const risk = decision.risk_mitigating_factors || [];

    section.innerHTML = `
        <div class="bg-white rounded-lg shadow-md p-6">
            <h3 class="text-lg font-semibold text-red-700 mb-4 flex items-center">
                <svg class="h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                </svg>
                Favorable Indicators (Violation)
            </h3>
            <ul class="space-y-2">
                ${favorable.map(item => `
                    <li class="flex items-start text-sm">
                        <span class="inline-block w-2 h-2 bg-red-400 rounded-full mr-2 mt-1.5 flex-shrink-0"></span>
                        <span class="text-gray-700">${escapeHtml(item)}</span>
                    </li>
                `).join('')}
            </ul>
        </div>
        <div class="bg-white rounded-lg shadow-md p-6">
            <h3 class="text-lg font-semibold text-green-700 mb-4 flex items-center">
                <svg class="h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                Risk Mitigating Factors
            </h3>
            <ul class="space-y-2">
                ${risk.map(item => `
                    <li class="flex items-start text-sm">
                        <span class="inline-block w-2 h-2 bg-green-400 rounded-full mr-2 mt-1.5 flex-shrink-0"></span>
                        <span class="text-gray-700">${escapeHtml(item)}</span>
                    </li>
                `).join('')}
            </ul>
        </div>
    `;

    return section;
}

/**
 * Render insider trading specific sections.
 * @param {Object} decision - Decision object
 * @returns {HTMLElement} IT sections container
 */
function renderInsiderTradingSections(decision) {
    const container = document.createElement('div');
    container.className = 'space-y-6';

    // Trader baseline analysis
    if (decision.trader_baseline_analysis) {
        const baseline = decision.trader_baseline_analysis;
        const baselineSection = document.createElement('div');
        baselineSection.className = 'bg-white rounded-lg shadow-md p-6';
        baselineSection.innerHTML = `
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Trader Baseline Analysis</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-sm text-gray-500 mb-1">Typical Volume</p>
                    <p class="text-gray-900">${escapeHtml(baseline.typical_volume || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-sm text-gray-500 mb-1">Typical Sectors</p>
                    <p class="text-gray-900">${escapeHtml(baseline.typical_sectors || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-sm text-gray-500 mb-1">Trading Frequency</p>
                    <p class="text-gray-900">${escapeHtml(baseline.typical_frequency || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-sm text-gray-500 mb-1">Deviation Assessment</p>
                    <p class="text-gray-900">${escapeHtml(baseline.deviation_assessment || 'N/A')}</p>
                </div>
            </div>
        `;
        container.appendChild(baselineSection);
    }

    // Market context
    if (decision.market_context) {
        const context = decision.market_context;
        const contextSection = document.createElement('div');
        contextSection.className = 'bg-white rounded-lg shadow-md p-6';
        contextSection.innerHTML = `
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Market Context</h3>
            <div class="space-y-4">
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-sm font-medium text-gray-700 mb-2">News Timeline</p>
                    <p class="text-gray-600 text-sm whitespace-pre-wrap">${escapeHtml(context.news_timeline || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-sm font-medium text-gray-700 mb-2">Volatility Assessment</p>
                    <p class="text-gray-600 text-sm">${escapeHtml(context.volatility_assessment || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-sm font-medium text-gray-700 mb-2">Peer Activity Summary</p>
                    <p class="text-gray-600 text-sm">${escapeHtml(context.peer_activity_summary || 'N/A')}</p>
                </div>
            </div>
        `;
        container.appendChild(contextSection);
    }

    return container;
}

/**
 * Render wash trade specific sections.
 * @param {Object} decision - Decision object
 * @returns {HTMLElement} WT sections container
 */
function renderWashTradeSections(decision) {
    const container = document.createElement('div');
    container.className = 'space-y-6';

    // Relationship network graph
    if (decision.relationship_network) {
        const graphSection = document.createElement('div');
        graphSection.className = 'bg-white rounded-lg shadow-md p-6';
        graphSection.innerHTML = `
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Relationship Network</h3>
            <div class="bg-gray-50 rounded-lg p-2 mb-4">
                <div id="cytoscape-container" class="w-full h-96 border border-gray-200 rounded-lg"></div>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500">Pattern Type</p>
                    <p class="font-medium text-gray-900">${escapeHtml(decision.relationship_network.pattern_type || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500">Pattern Confidence</p>
                    <p class="font-medium text-gray-900">${decision.relationship_network.pattern_confidence || 0}%</p>
                </div>
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500">Nodes</p>
                    <p class="font-medium text-gray-900">${decision.relationship_network.nodes?.length || 0}</p>
                </div>
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500">Edges</p>
                    <p class="font-medium text-gray-900">${decision.relationship_network.edges?.length || 0}</p>
                </div>
            </div>
            <p class="text-sm text-gray-600 mt-4">${escapeHtml(decision.relationship_network.pattern_description || '')}</p>
        `;
        container.appendChild(graphSection);
    }

    // Timing patterns
    if (decision.timing_patterns) {
        const timing = decision.timing_patterns;
        const timingSection = document.createElement('div');
        timingSection.className = 'bg-white rounded-lg shadow-md p-6';

        const preArrangedBadge = timing.is_pre_arranged
            ? '<span class="bg-red-100 text-red-800 px-2 py-1 rounded text-xs font-medium">Pre-arranged</span>'
            : '<span class="bg-green-100 text-green-800 px-2 py-1 rounded text-xs font-medium">Not Pre-arranged</span>';

        timingSection.innerHTML = `
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Timing Analysis</h3>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500 text-sm">Time Delta</p>
                    <p class="font-medium text-gray-900">${escapeHtml(timing.time_delta_description || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500 text-sm">Market Phase</p>
                    <p class="font-medium text-gray-900">${escapeHtml(timing.market_phase?.replace('_', ' ') || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500 text-sm">Liquidity</p>
                    <p class="font-medium text-gray-900">${escapeHtml(timing.liquidity_assessment || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500 text-sm">Pre-arrangement</p>
                    ${preArrangedBadge}
                    <p class="text-xs text-gray-500 mt-1">${timing.pre_arrangement_confidence || 0}% confidence</p>
                </div>
            </div>
            <div class="bg-gray-50 rounded p-4">
                <p class="text-sm text-gray-600">${escapeHtml(timing.timing_analysis || '')}</p>
            </div>
        `;
        container.appendChild(timingSection);
    }

    // Counterparty pattern
    if (decision.counterparty_pattern) {
        const cp = decision.counterparty_pattern;
        const cpSection = document.createElement('div');
        cpSection.className = 'bg-white rounded-lg shadow-md p-6';

        const badges = [];
        if (cp.is_circular) badges.push('<span class="bg-red-100 text-red-800 px-2 py-1 rounded text-xs font-medium">Circular</span>');
        if (cp.is_offsetting) badges.push('<span class="bg-yellow-100 text-yellow-800 px-2 py-1 rounded text-xs font-medium">Offsetting</span>');
        if (cp.same_beneficial_owner) badges.push('<span class="bg-red-100 text-red-800 px-2 py-1 rounded text-xs font-medium">Same Owner</span>');

        cpSection.innerHTML = `
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Counterparty Pattern</h3>
            <div class="flex flex-wrap gap-2 mb-4">
                ${badges.join('')}
            </div>
            ${cp.trade_flow && cp.trade_flow.length > 0 ? `
                <div class="overflow-x-auto">
                    <table class="min-w-full text-sm">
                        <thead class="bg-gray-50">
                            <tr>
                                <th class="px-4 py-2 text-left">#</th>
                                <th class="px-4 py-2 text-left">Account</th>
                                <th class="px-4 py-2 text-left">Side</th>
                                <th class="px-4 py-2 text-right">Quantity</th>
                                <th class="px-4 py-2 text-right">Price</th>
                                <th class="px-4 py-2 text-left">Timestamp</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-200">
                            ${cp.trade_flow.map(trade => `
                                <tr>
                                    <td class="px-4 py-2">${trade.sequence_number}</td>
                                    <td class="px-4 py-2 font-mono text-xs">${escapeHtml(trade.account_id)}</td>
                                    <td class="px-4 py-2">
                                        <span class="${trade.side === 'BUY' ? 'text-green-600' : 'text-red-600'} font-medium">
                                            ${trade.side}
                                        </span>
                                    </td>
                                    <td class="px-4 py-2 text-right">${trade.quantity?.toLocaleString()}</td>
                                    <td class="px-4 py-2 text-right">$${trade.price?.toFixed(2)}</td>
                                    <td class="px-4 py-2 font-mono text-xs">${escapeHtml(trade.timestamp || '')}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            ` : ''}
            ${cp.economic_purpose_identified ? `
                <div class="mt-4 bg-green-50 rounded p-4">
                    <p class="text-sm font-medium text-green-800">Economic Purpose Identified:</p>
                    <p class="text-sm text-green-700">${escapeHtml(cp.economic_purpose_description || 'N/A')}</p>
                </div>
            ` : ''}
        `;
        container.appendChild(cpSection);
    }

    // Historical patterns
    if (decision.historical_patterns) {
        const hp = decision.historical_patterns;
        const hpSection = document.createElement('div');
        hpSection.className = 'bg-white rounded-lg shadow-md p-6';
        hpSection.innerHTML = `
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Historical Patterns</h3>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500 text-sm">Similar Patterns</p>
                    <p class="font-medium text-gray-900">${hp.pattern_count || 0}</p>
                </div>
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500 text-sm">Time Window</p>
                    <p class="font-medium text-gray-900">${hp.time_window_days || 0} days</p>
                </div>
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500 text-sm">Avg Frequency</p>
                    <p class="font-medium text-gray-900">${escapeHtml(hp.average_frequency || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded p-3">
                    <p class="text-gray-500 text-sm">Trend</p>
                    <p class="font-medium text-gray-900 capitalize">${escapeHtml(hp.pattern_trend || 'N/A')}</p>
                </div>
            </div>
            <div class="bg-gray-50 rounded p-4">
                <p class="text-sm text-gray-600">${escapeHtml(hp.historical_analysis || '')}</p>
            </div>
        `;
        container.appendChild(hpSection);
    }

    // Regulatory flags
    if (decision.regulatory_flags && decision.regulatory_flags.length > 0) {
        const regSection = document.createElement('div');
        regSection.className = 'bg-white rounded-lg shadow-md p-6';
        regSection.innerHTML = `
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Regulatory Framework</h3>
            <div class="flex flex-wrap gap-2">
                ${decision.regulatory_flags.map(flag => `
                    <span class="bg-purple-100 text-purple-800 px-3 py-1 rounded-full text-sm font-medium">
                        ${escapeHtml(flag)}
                    </span>
                `).join('')}
            </div>
        `;
        container.appendChild(regSection);
    }

    return container;
}

/**
 * Render reasoning narrative section.
 * @param {Object} decision - Decision object
 * @returns {HTMLElement} Reasoning section
 */
function renderReasoning(decision) {
    const section = document.createElement('div');
    section.className = 'bg-white rounded-lg shadow-md p-6';

    section.innerHTML = `
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Reasoning Narrative</h3>
        <div class="prose prose-sm max-w-none text-gray-700">
            ${escapeHtml(decision.reasoning_narrative || 'No reasoning provided.').split('\n\n').map(p => `<p class="mb-4">${p}</p>`).join('')}
        </div>
    `;

    return section;
}

/**
 * Render similar precedent section.
 * @param {Object} decision - Decision object
 * @returns {HTMLElement} Precedent section
 */
function renderPrecedent(decision) {
    const section = document.createElement('div');
    section.className = 'bg-blue-50 rounded-lg shadow-md p-6';

    section.innerHTML = `
        <h3 class="text-lg font-semibold text-blue-900 mb-2">Similar Precedent</h3>
        <p class="text-blue-800">${escapeHtml(decision.similar_precedent)}</p>
    `;

    return section;
}

/**
 * Render download buttons.
 * @param {string} taskId - Task ID
 * @returns {HTMLElement} Download section
 */
function renderDownloadButtons(taskId) {
    const section = document.createElement('div');
    section.className = 'bg-white rounded-lg shadow-md p-6';

    section.innerHTML = `
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Download Reports</h3>
        <div class="flex flex-wrap gap-4">
            <a href="/api/download/${taskId}/json"
               class="inline-flex items-center px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-800 rounded-lg transition-colors">
                <svg class="h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                </svg>
                Download JSON
            </a>
            <a href="/api/download/${taskId}/html"
               class="inline-flex items-center px-4 py-2 bg-blue-100 hover:bg-blue-200 text-blue-800 rounded-lg transition-colors">
                <svg class="h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                </svg>
                Download HTML Report
            </a>
        </div>
    `;

    return section;
}

/**
 * Render new analysis button.
 * @returns {HTMLElement} Button section
 */
function renderNewAnalysisButton() {
    const section = document.createElement('div');
    section.className = 'text-center';

    section.innerHTML = `
        <button onclick="resetToUpload()"
                class="inline-flex items-center px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold transition-colors">
            <svg class="h-5 w-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
            </svg>
            Analyze Another Alert
        </button>
    `;

    return section;
}

/**
 * Initialize Cytoscape.js graph for relationship network.
 * @param {Object} network - Relationship network data
 */
function initCytoscapeGraph(network) {
    const container = document.getElementById('cytoscape-container');
    if (!container) {
        console.error('Cytoscape container not found');
        return;
    }

    console.log('Initializing Cytoscape graph');

    // Map nodes to Cytoscape format
    const nodes = (network.nodes || []).map(node => ({
        data: {
            id: node.account_id,
            label: node.account_id,
            owner: node.beneficial_owner_name || node.beneficial_owner_id,
            type: node.relationship_type,
            flagged: node.is_flagged,
        },
    }));

    // Map edges to Cytoscape format
    const edges = (network.edges || []).map((edge, idx) => ({
        data: {
            id: `edge-${idx}`,
            source: edge.from_account,
            target: edge.to_account,
            type: edge.edge_type,
            label: edge.trade_details || edge.edge_type,
            suspicious: edge.is_suspicious,
        },
    }));

    // Initialize Cytoscape
    const cy = cytoscape({
        container: container,
        elements: { nodes, edges },
        style: [
            {
                selector: 'node',
                style: {
                    'background-color': '#4B5563',
                    'label': 'data(label)',
                    'text-valign': 'bottom',
                    'text-halign': 'center',
                    'font-size': '10px',
                    'text-margin-y': '5px',
                    'width': '40px',
                    'height': '40px',
                },
            },
            {
                selector: 'node[?flagged]',
                style: {
                    'background-color': '#DC2626',
                    'border-width': '3px',
                    'border-color': '#991B1B',
                },
            },
            {
                selector: 'edge',
                style: {
                    'width': 2,
                    'line-color': '#9CA3AF',
                    'target-arrow-color': '#9CA3AF',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'label': 'data(label)',
                    'font-size': '8px',
                    'text-rotation': 'autorotate',
                    'text-margin-y': '-10px',
                },
            },
            {
                selector: 'edge[?suspicious]',
                style: {
                    'line-color': '#DC2626',
                    'target-arrow-color': '#DC2626',
                    'width': 3,
                },
            },
            {
                selector: 'edge[type="ownership"]',
                style: {
                    'line-style': 'dashed',
                    'line-color': '#6366F1',
                    'target-arrow-color': '#6366F1',
                },
            },
            {
                selector: 'edge[type="beneficial_owner"]',
                style: {
                    'line-style': 'dotted',
                    'line-color': '#8B5CF6',
                    'target-arrow-color': '#8B5CF6',
                },
            },
        ],
        layout: {
            name: 'cose',
            idealEdgeLength: 100,
            nodeOverlap: 20,
            refresh: 20,
            fit: true,
            padding: 30,
            randomize: false,
            componentSpacing: 100,
            nodeRepulsion: 400000,
            edgeElasticity: 100,
            nestingFactor: 5,
            gravity: 80,
            numIter: 1000,
            initialTemp: 200,
            coolingFactor: 0.95,
            minTemp: 1.0,
        },
    });

    // Fit graph to container
    cy.fit();

    // Add interactivity
    cy.on('tap', 'node', function(evt) {
        const node = evt.target;
        const data = node.data();
        showToast(`Account: ${data.id}\nOwner: ${data.owner}\nType: ${data.type}`, 'info');
    });

    console.log('Cytoscape graph initialized with', nodes.length, 'nodes and', edges.length, 'edges');
}

/**
 * Escape HTML to prevent XSS.
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
