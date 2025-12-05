/**
 * Results rendering for SMARTS Alert Analyzer.
 *
 * Handles rendering of analysis results matching the downloadable HTML report format.
 * Includes:
 * - Common decision fields (determination, confidence, findings)
 * - Insider trading specific sections
 * - Wash trade specific sections with Cytoscape.js graphs
 */

/**
 * Render analysis results.
 * @param {Object} decision - Decision JSON from analysis
 * @param {string} alertType - Type of alert (insider_trading, wash_trade)
 * @param {string} taskId - Task ID for download links
 * @param {Object} alertSummary - Original alert summary data (optional)
 */
function renderResults(decision, alertType, taskId, alertSummary) {
    console.log('Rendering results:', alertType, decision);

    const resultsSection = document.getElementById('results-section');
    resultsSection.innerHTML = '';

    // Create main container matching downloadable report width
    const container = document.createElement('div');
    container.className = 'max-w-5xl mx-auto space-y-6';

    // Header matching downloadable report format
    container.appendChild(renderReportHeader(decision, alertType));

    // Determination banner with confidence scores
    container.appendChild(renderDeterminationBanner(decision, alertType));

    // Alert-type specific sections
    if (alertType === 'insider_trading' || alertType === 'INSIDER_TRADING') {
        // Relationship network graph for wash trade (before other sections)
        // Original SMARTS Alert section
        if (alertSummary) {
            container.appendChild(renderOriginalAlertSection(alertSummary));
        }

        // AI Analysis Insights (key findings + indicators)
        container.appendChild(renderAnalysisInsights(decision));

        // Insider trading specific sections
        container.appendChild(renderInsiderTradingSections(decision));
    } else if (alertType === 'wash_trade' || alertType === 'WASH_TRADE') {
        // Relationship network graph first (important for wash trade)
        if (decision.relationship_network) {
            container.appendChild(renderRelationshipNetworkSection(decision.relationship_network));
        }

        // Flagged trades and wash indicators
        if (alertSummary) {
            container.appendChild(renderWashTradeAlertSection(alertSummary));
        }

        // Wash trade specific sections
        container.appendChild(renderWashTradeSections(decision));
    }

    // Reasoning narrative with similar precedent
    container.appendChild(renderReasoningSection(decision));

    // Data gaps section (if available)
    if (decision.data_gaps && decision.data_gaps.length > 0) {
        container.appendChild(renderDataGapsSection(decision.data_gaps));
    }

    // Download buttons
    container.appendChild(renderDownloadButtons(taskId));

    // Footer
    container.appendChild(renderReportFooter(alertType));

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
 * Render report header matching downloadable report format.
 * @param {Object} decision - Decision object
 * @param {string} alertType - Alert type
 * @returns {HTMLElement} Header element
 */
function renderReportHeader(decision, alertType) {
    const header = document.createElement('header');
    header.className = 'bg-white rounded-lg shadow-md p-6';

    const isWashTrade = alertType === 'wash_trade' || alertType === 'WASH_TRADE';
    const title = isWashTrade ? 'Wash Trade Analysis Report' : 'SMARTS Alert Analysis Report';
    const subtitle = isWashTrade ? 'AI-Powered Compliance Analysis | APAC Regulatory Framework' : 'AI-Powered Compliance Analysis';

    // Format timestamp
    const timestamp = decision.timestamp
        ? new Date(decision.timestamp).toLocaleString('en-US', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            timeZoneName: 'short'
          })
        : new Date().toLocaleString();

    // Severity badge for wash trade
    const severityBadge = isWashTrade && decision.severity ? `
        <div>
            <span class="text-sm text-gray-600">Severity:</span>
            <span class="px-2 py-1 rounded text-sm font-medium ml-2 ${getSeverityColor(decision.severity)}">
                ${escapeHtml(decision.severity)}
            </span>
        </div>
    ` : '';

    header.innerHTML = `
        <div class="flex justify-between items-start">
            <div>
                <h1 class="text-2xl font-bold text-gray-900">${title}</h1>
                <p class="text-gray-600 mt-1">${subtitle}</p>
            </div>
            <div class="text-right">
                <p class="text-sm text-gray-500">Report Generated</p>
                <p class="text-sm font-medium text-gray-700">${escapeHtml(timestamp)}</p>
            </div>
        </div>
        <div class="mt-4 pt-4 border-t border-gray-200 flex flex-wrap gap-4">
            <div>
                <span class="text-sm text-gray-600">Alert ID:</span>
                <span class="font-mono bg-gray-100 px-2 py-1 rounded ml-2">${escapeHtml(decision.alert_id || 'N/A')}</span>
            </div>
            ${severityBadge}
        </div>
    `;

    return header;
}

/**
 * Get severity color class.
 * @param {string} severity - Severity level
 * @returns {string} Tailwind color classes
 */
function getSeverityColor(severity) {
    const colors = {
        'CRITICAL': 'bg-red-100 text-red-800',
        'HIGH': 'bg-orange-100 text-orange-800',
        'MEDIUM': 'bg-yellow-100 text-yellow-800',
        'LOW': 'bg-green-100 text-green-800',
    };
    return colors[(severity || '').toUpperCase()] || 'bg-gray-100 text-gray-800';
}

/**
 * Render determination banner matching downloadable report format.
 * Shows determination badge and confidence scores as large percentages.
 * @param {Object} decision - Decision object
 * @param {string} alertType - Alert type
 * @returns {HTMLElement} Determination banner section
 */
function renderDeterminationBanner(decision, alertType) {
    const section = document.createElement('section');
    section.className = 'bg-white rounded-lg shadow-md p-6';

    const determination = decision.determination || 'UNKNOWN';
    const badgeColors = {
        'ESCALATE': { bg: 'bg-red-600', text: 'text-white', label: 'ESCALATE' },
        'CLOSE': { bg: 'bg-green-600', text: 'text-white', label: 'CLOSE' },
        'NEEDS_HUMAN_REVIEW': { bg: 'bg-yellow-500', text: 'text-white', label: 'NEEDS HUMAN REVIEW' },
    };
    const colors = badgeColors[determination] || badgeColors['NEEDS_HUMAN_REVIEW'];

    const genuine = decision.genuine_alert_confidence || 0;
    const falsePositive = decision.false_positive_confidence || 0;

    // Get confidence text color
    const genuineColor = genuine >= 70 ? 'text-red-600' : genuine >= 40 ? 'text-yellow-600' : 'text-green-600';
    const fpColor = falsePositive >= 70 ? 'text-green-600' : falsePositive >= 40 ? 'text-yellow-600' : 'text-red-600';

    const isWashTrade = alertType === 'wash_trade' || alertType === 'WASH_TRADE';

    // Additional wash trade info
    let additionalInfo = '';
    if (isWashTrade) {
        const patternType = decision.relationship_network?.pattern_type || 'NO_PATTERN';
        const patternColors = {
            'DIRECT_WASH': 'bg-red-100 text-red-800 border-red-300',
            'LAYERED_WASH': 'bg-orange-100 text-orange-800 border-orange-300',
            'INTERMEDIARY_WASH': 'bg-yellow-100 text-yellow-800 border-yellow-300',
            'NO_PATTERN': 'bg-green-100 text-green-800 border-green-300',
        };
        const patternColor = patternColors[patternType] || patternColors['NO_PATTERN'];
        const volumeImpact = decision.volume_impact_percentage || 0;
        const beneficialOwnerMatch = decision.beneficial_ownership_match;

        additionalInfo = `
            <div class="mt-4 pt-4 border-t border-gray-200 flex flex-wrap gap-4">
                <div>
                    <span class="text-sm text-gray-500">Pattern Detected:</span>
                    <span class="ml-2 px-3 py-1 rounded-full text-sm font-medium border ${patternColor}">
                        ${escapeHtml(patternType.replace(/_/g, ' '))}
                    </span>
                </div>
                <div>
                    <span class="text-sm text-gray-500">Volume Impact:</span>
                    <span class="ml-2 font-medium text-gray-700">${volumeImpact.toFixed(1)}%</span>
                </div>
                <div>
                    <span class="text-sm text-gray-500">Same Beneficial Owner:</span>
                    <span class="ml-2 font-medium ${beneficialOwnerMatch ? 'text-red-600' : 'text-green-600'}">
                        ${beneficialOwnerMatch ? 'Yes' : 'No'}
                    </span>
                </div>
            </div>
        `;
    } else {
        // Insider trading additional info
        const recommendedAction = decision.recommended_action || '';
        const actionColors = {
            'ESCALATE': 'bg-red-100 text-red-800',
            'CLOSE': 'bg-green-100 text-green-800',
            'MONITOR': 'bg-blue-100 text-blue-800',
            'REQUEST_MORE_DATA': 'bg-purple-100 text-purple-800',
        };
        const actionColor = actionColors[recommendedAction] || 'bg-gray-100 text-gray-800';
        const precedent = decision.similar_precedent || '';

        additionalInfo = `
            <div class="mt-4 pt-4 border-t border-gray-200 flex flex-wrap gap-4">
                <div>
                    <span class="text-sm text-gray-500">Recommended Action:</span>
                    <span class="ml-2 px-3 py-1 rounded-full text-sm font-medium ${actionColor}">
                        ${escapeHtml(recommendedAction)}
                    </span>
                </div>
                ${precedent ? `
                <div class="flex-1 text-right">
                    <span class="text-sm text-gray-500">Similar Precedent:</span>
                    <span class="ml-2 text-sm text-gray-700">${escapeHtml(precedent.substring(0, 80))}${precedent.length > 80 ? '...' : ''}</span>
                </div>
                ` : ''}
            </div>
        `;
    }

    const genuineLabel = isWashTrade ? 'Genuine Wash Trade' : 'Genuine Alert';

    section.innerHTML = `
        <div class="flex flex-col md:flex-row md:items-center md:justify-between">
            <div class="mb-4 md:mb-0">
                <p class="text-sm font-medium text-gray-500 uppercase tracking-wide mb-2">AI Determination</p>
                <span class="inline-flex items-center px-4 py-2 rounded-md text-lg font-bold ${colors.bg} ${colors.text}">
                    ${escapeHtml(colors.label)}
                </span>
            </div>
            <div class="flex space-x-8">
                <div class="text-center">
                    <p class="text-sm text-gray-500">${genuineLabel}</p>
                    <p class="text-2xl font-bold ${genuineColor}">${genuine}%</p>
                </div>
                <div class="text-center">
                    <p class="text-sm text-gray-500">False Positive</p>
                    <p class="text-2xl font-bold ${fpColor}">${falsePositive}%</p>
                </div>
            </div>
        </div>
        ${additionalInfo}
    `;

    return section;
}

/**
 * Render AI Analysis Insights section matching downloadable report.
 * Combines key findings with favorable/mitigating factors.
 * @param {Object} decision - Decision object
 * @returns {HTMLElement} Analysis insights section
 */
function renderAnalysisInsights(decision) {
    const section = document.createElement('section');
    section.className = 'bg-white rounded-lg shadow-md p-6';

    const findings = decision.key_findings || [];
    const favorable = decision.favorable_indicators || [];
    const mitigating = decision.risk_mitigating_factors || [];

    // Key findings with numbered badges
    const findingsHtml = findings.map((finding, i) => `
        <li class="flex items-start">
            <span class="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-800 rounded-full flex items-center justify-center text-xs font-bold mr-3">${i + 1}</span>
            <span>${escapeHtml(finding)}</span>
        </li>
    `).join('');

    // Favorable indicators with warning icons
    const favorableHtml = favorable.map(item => `
        <li class="flex items-start">
            <svg class="w-4 h-4 text-red-500 mr-2 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
            </svg>
            <span class="text-gray-700">${escapeHtml(item)}</span>
        </li>
    `).join('');

    // Risk mitigating factors with checkmark icons
    const mitigatingHtml = mitigating.map(item => `
        <li class="flex items-start">
            <svg class="w-4 h-4 text-green-500 mr-2 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
            </svg>
            <span class="text-gray-700">${escapeHtml(item)}</span>
        </li>
    `).join('');

    section.innerHTML = `
        <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
            <svg class="w-5 h-5 mr-2 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path>
            </svg>
            AI Analysis Insights
        </h2>

        <!-- Key Findings -->
        <div class="mb-6">
            <h3 class="text-sm font-medium text-gray-700 mb-3">Key Findings</h3>
            <ol class="space-y-3 text-sm">
                ${findingsHtml}
            </ol>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Favorable Indicators -->
            <div class="bg-red-50 rounded-lg p-4">
                <h3 class="text-sm font-medium text-red-800 mb-3 flex items-center">
                    <svg class="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                    </svg>
                    Favorable Indicators (Suggesting Genuine)
                </h3>
                <ul class="space-y-2 text-sm">
                    ${favorableHtml}
                </ul>
            </div>

            <!-- Risk Mitigating Factors -->
            <div class="bg-green-50 rounded-lg p-4">
                <h3 class="text-sm font-medium text-green-800 mb-3 flex items-center">
                    <svg class="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                    </svg>
                    Risk Mitigating Factors (Suggesting False Positive)
                </h3>
                <ul class="space-y-2 text-sm">
                    ${mitigatingHtml}
                </ul>
            </div>
        </div>
    `;

    return section;
}

/**
 * Render original SMARTS alert section for insider trading.
 * @param {Object} alertSummary - Parsed alert data
 * @returns {HTMLElement} Original alert section
 */
function renderOriginalAlertSection(alertSummary) {
    const section = document.createElement('section');
    section.className = 'bg-white rounded-lg shadow-md p-6';

    const sideColor = alertSummary.side === 'BUY' ? 'text-green-600' : 'text-red-600';

    // Format currency
    const formatCurrency = (value) => {
        const num = parseFloat(value) || 0;
        return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };

    // Format number
    const formatNumber = (value) => {
        const num = parseInt(value) || 0;
        return num.toLocaleString('en-US');
    };

    // Related event section
    const relatedEventHtml = alertSummary.related_event_type ? `
        <div class="mt-4 pt-4 border-t border-gray-200">
            <h4 class="text-sm font-medium text-gray-700 mb-3">Related Event</h4>
            <div class="bg-yellow-50 border border-yellow-200 rounded-md p-3">
                <p class="text-sm"><span class="font-medium">Event:</span> ${escapeHtml(alertSummary.related_event_type)}</p>
                <p class="text-sm"><span class="font-medium">Date:</span> ${escapeHtml(alertSummary.related_event_date || '')}</p>
                <p class="text-sm mt-1">${escapeHtml(alertSummary.related_event_description || '')}</p>
            </div>
        </div>
    ` : '';

    section.innerHTML = `
        <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
            <svg class="w-5 h-5 mr-2 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
            </svg>
            Original SMARTS Alert
        </h2>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Alert Metadata -->
            <div>
                <h4 class="text-sm font-medium text-gray-700 mb-3">Alert Information</h4>
                <div class="space-y-2 text-sm">
                    <p><span class="text-gray-500">Alert Type:</span> <span class="font-medium">${escapeHtml(alertSummary.alert_type || 'N/A')}</span></p>
                    <p><span class="text-gray-500">Rule Violated:</span> <span class="font-mono bg-red-50 text-red-700 px-2 py-0.5 rounded">${escapeHtml(alertSummary.rule_violated || 'N/A')}</span></p>
                    <p><span class="text-gray-500">Generated:</span> <span class="font-medium">${escapeHtml(alertSummary.generated_timestamp || 'N/A')}</span></p>
                </div>
            </div>

            <!-- Trader Info -->
            <div>
                <h4 class="text-sm font-medium text-gray-700 mb-3">Trader Information</h4>
                <div class="space-y-2 text-sm">
                    <p><span class="text-gray-500">Trader ID:</span> <span class="font-mono">${escapeHtml(alertSummary.trader_id || 'N/A')}</span></p>
                    <p><span class="text-gray-500">Name:</span> <span class="font-medium">${escapeHtml(alertSummary.trader_name || 'N/A')}</span></p>
                    <p><span class="text-gray-500">Department:</span> <span class="font-medium">${escapeHtml(alertSummary.trader_department || 'N/A')}</span></p>
                </div>
            </div>
        </div>

        <!-- Trade Details -->
        <div class="mt-6 pt-4 border-t border-gray-200">
            <h4 class="text-sm font-medium text-gray-700 mb-3">Suspicious Trade Details</h4>
            <div class="bg-gray-50 rounded-lg p-4">
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                    <div>
                        <p class="text-xs text-gray-500 uppercase">Symbol</p>
                        <p class="text-lg font-bold text-gray-900">${escapeHtml(alertSummary.symbol || 'N/A')}</p>
                    </div>
                    <div>
                        <p class="text-xs text-gray-500 uppercase">Side</p>
                        <p class="text-lg font-bold ${sideColor}">${escapeHtml(alertSummary.side || 'N/A')}</p>
                    </div>
                    <div>
                        <p class="text-xs text-gray-500 uppercase">Quantity</p>
                        <p class="text-lg font-bold text-gray-900">${formatNumber(alertSummary.quantity)}</p>
                    </div>
                    <div>
                        <p class="text-xs text-gray-500 uppercase">Price</p>
                        <p class="text-lg font-bold text-gray-900">${formatCurrency(alertSummary.price)}</p>
                    </div>
                </div>
                <div class="mt-4 pt-4 border-t border-gray-200 grid grid-cols-2 gap-4 text-center">
                    <div>
                        <p class="text-xs text-gray-500 uppercase">Total Value</p>
                        <p class="text-xl font-bold text-blue-600">${formatCurrency(alertSummary.total_value)}</p>
                    </div>
                    <div>
                        <p class="text-xs text-gray-500 uppercase">Trade Date</p>
                        <p class="text-lg font-medium text-gray-700">${escapeHtml(alertSummary.trade_date || 'N/A')}</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Anomaly Indicators -->
        <div class="mt-6 pt-4 border-t border-gray-200">
            <h4 class="text-sm font-medium text-gray-700 mb-3">SMARTS Anomaly Indicators</h4>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div class="bg-red-50 rounded-lg p-3 text-center">
                    <p class="text-xs text-gray-500 uppercase">Anomaly Score</p>
                    <p class="text-2xl font-bold text-red-600">${alertSummary.anomaly_score || 0}</p>
                </div>
                <div class="bg-orange-50 rounded-lg p-3 text-center">
                    <p class="text-xs text-gray-500 uppercase">Confidence</p>
                    <p class="text-lg font-bold text-orange-600">${escapeHtml(alertSummary.confidence_level || 'N/A')}</p>
                </div>
                <div class="bg-purple-50 rounded-lg p-3 text-center">
                    <p class="text-xs text-gray-500 uppercase">Est. Profit</p>
                    <p class="text-lg font-bold text-purple-600">${formatCurrency(alertSummary.estimated_profit)}</p>
                </div>
                <div class="bg-blue-50 rounded-lg p-3">
                    <p class="text-xs text-gray-500 uppercase">Temporal Proximity</p>
                    <p class="text-sm font-medium text-blue-700">${escapeHtml(alertSummary.temporal_proximity || 'N/A')}</p>
                </div>
            </div>
        </div>

        ${relatedEventHtml}
    `;

    return section;
}

/**
 * Render wash trade alert section with flagged trades.
 * @param {Object} alertSummary - Parsed wash trade alert data
 * @returns {HTMLElement} Wash trade alert section
 */
function renderWashTradeAlertSection(alertSummary) {
    const section = document.createElement('section');
    section.className = 'bg-white rounded-lg shadow-md p-6';

    // Build trades HTML
    const trades = alertSummary.trades || [];
    const tradesHtml = trades.map(trade => {
        const sideColor = trade.Side === 'BUY' ? 'text-green-600' : 'text-red-600';
        return `
            <div class="bg-gray-50 rounded-lg p-4 mb-3">
                <div class="flex justify-between items-start mb-2">
                    <span class="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium">
                        Trade ${escapeHtml(trade.sequence || '?')}
                    </span>
                    <span class="text-sm text-gray-500">${escapeHtml(trade.TradeTime || '')}</span>
                </div>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div>
                        <p class="text-gray-500 text-xs">Account</p>
                        <p class="font-medium">${escapeHtml(trade.AccountID || '')}</p>
                        <p class="text-xs text-gray-400">${escapeHtml(trade.AccountName || '')}</p>
                    </div>
                    <div>
                        <p class="text-gray-500 text-xs">Side / Symbol</p>
                        <p class="font-medium ${sideColor}">${escapeHtml(trade.Side || '')}</p>
                        <p class="text-xs">${escapeHtml(trade.Symbol || '')}</p>
                    </div>
                    <div>
                        <p class="text-gray-500 text-xs">Quantity / Price</p>
                        <p class="font-medium">${escapeHtml(trade.Quantity || '')}</p>
                        <p class="text-xs">$${escapeHtml(trade.Price || '')}</p>
                    </div>
                    <div>
                        <p class="text-gray-500 text-xs">Counterparty</p>
                        <p class="font-medium">${escapeHtml(trade.CounterpartyAccount || 'MARKET')}</p>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    // Build wash indicators HTML
    const indicators = alertSummary.wash_indicators || {};
    const indicatorsHtml = Object.entries(indicators).map(([key, value]) => `
        <div class="bg-gray-50 px-3 py-2 rounded">
            <p class="text-xs text-gray-500">${escapeHtml(key)}</p>
            <p class="font-medium text-sm">${escapeHtml(value || 'N/A')}</p>
        </div>
    `).join('');

    section.innerHTML = `
        <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
            <svg class="w-5 h-5 mr-2 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
            </svg>
            Flagged Trades
        </h2>

        ${tradesHtml}

        <h3 class="text-md font-medium text-gray-800 mt-6 mb-3">Wash Trade Indicators</h3>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            ${indicatorsHtml}
        </div>
    `;

    return section;
}

/**
 * Render relationship network section with Cytoscape graph for wash trade.
 * Matches the downloadable report format with legend and controls.
 * @param {Object} network - Relationship network data
 * @returns {HTMLElement} Relationship network section
 */
function renderRelationshipNetworkSection(network) {
    const section = document.createElement('section');
    section.className = 'bg-white rounded-lg shadow-md p-6';

    const patternType = network.pattern_type || 'NO_PATTERN';
    const patternConfidence = network.pattern_confidence || 0;
    const patternDescription = network.pattern_description || '';

    section.innerHTML = `
        <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
            <svg class="w-5 h-5 mr-2 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
            </svg>
            Relationship Network
        </h2>

        <!-- Graph Controls -->
        <div class="flex justify-end mb-2">
            <button id="cy-fit-btn"
                    class="px-3 py-1 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-md transition-colors flex items-center gap-1">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path>
                </svg>
                Fit to View
            </button>
        </div>

        <!-- Graph Container -->
        <div id="cytoscape-container"
             style="width: 100%; height: 450px; border: 1px solid #E5E7EB; border-radius: 8px; background: #F9FAFB;">
        </div>

        <!-- Legend -->
        <div class="mt-4 flex flex-wrap justify-center gap-6 text-sm">
            <div class="flex items-center">
                <div class="w-4 h-4 rounded-full mr-2" style="background-color: #EF4444;"></div>
                <span class="text-gray-700">Flagged Account</span>
            </div>
            <div class="flex items-center">
                <div class="w-4 h-4 rounded-full mr-2" style="background-color: #3B82F6;"></div>
                <span class="text-gray-700">Related Account</span>
            </div>
            <div class="flex items-center">
                <div class="w-4 h-4 rounded mr-2" style="background-color: #8B5CF6;"></div>
                <span class="text-gray-700">Beneficial Owner</span>
            </div>
            <div class="flex items-center">
                <div class="w-8 h-0.5 mr-2" style="background-color: #EF4444;"></div>
                <span class="text-gray-700">Suspicious Trade</span>
            </div>
            <div class="flex items-center">
                <div class="w-8 h-0.5 mr-2 border-t-2 border-dashed" style="border-color: #8B5CF6;"></div>
                <span class="text-gray-700">Ownership Link</span>
            </div>
        </div>

        <!-- Instructions -->
        <div class="mt-3 text-center text-xs text-gray-500">
            <span class="mr-4">🖱️ Click node to highlight connections</span>
            <span class="mr-4">📍 Drag to pan</span>
            <span>🔍 Scroll to zoom</span>
        </div>

        <!-- Pattern Description -->
        <div class="mt-4 p-4 bg-gray-50 rounded-lg">
            <p class="text-sm text-gray-700">
                <span class="font-medium">Pattern:</span>
                ${escapeHtml(patternDescription)}
            </p>
            <p class="text-sm text-gray-500 mt-1">
                <span class="font-medium">Confidence:</span> ${patternConfidence}%
            </p>
        </div>
    `;

    return section;
}

/**
 * Render insider trading specific sections matching downloadable report.
 * @param {Object} decision - Decision object
 * @returns {HTMLElement} IT sections container
 */
function renderInsiderTradingSections(decision) {
    const container = document.createElement('div');
    container.className = 'space-y-6';

    // Trader baseline analysis - matching 3-column layout from downloadable report
    if (decision.trader_baseline_analysis) {
        const baseline = decision.trader_baseline_analysis;
        const baselineSection = document.createElement('section');
        baselineSection.className = 'bg-white rounded-lg shadow-md p-6';
        baselineSection.innerHTML = `
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
                </svg>
                Trader Baseline Analysis
            </h2>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-1">Typical Volume</p>
                    <p class="text-sm text-gray-800">${escapeHtml(baseline.typical_volume || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-1">Typical Sectors</p>
                    <p class="text-sm text-gray-800">${escapeHtml(baseline.typical_sectors || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-1">Trading Frequency</p>
                    <p class="text-sm text-gray-800">${escapeHtml(baseline.typical_frequency || 'N/A')}</p>
                </div>
            </div>

            <div class="bg-amber-50 border border-amber-200 rounded-lg p-4">
                <p class="text-xs text-amber-700 uppercase font-medium mb-1">Deviation Assessment</p>
                <p class="text-sm text-amber-900">${escapeHtml(baseline.deviation_assessment || 'N/A')}</p>
            </div>
        `;
        container.appendChild(baselineSection);
    }

    // Market context - matching downloadable report layout
    if (decision.market_context) {
        const context = decision.market_context;
        const contextSection = document.createElement('section');
        contextSection.className = 'bg-white rounded-lg shadow-md p-6';
        contextSection.innerHTML = `
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-teal-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"></path>
                </svg>
                Market Context
            </h2>

            <div class="space-y-4">
                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-2">News Timeline</p>
                    <p class="text-sm text-gray-800">${escapeHtml(context.news_timeline || 'N/A')}</p>
                </div>

                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-2">Volatility Assessment</p>
                    <p class="text-sm text-gray-800">${escapeHtml(context.volatility_assessment || 'N/A')}</p>
                </div>

                <div class="bg-gray-50 rounded-lg p-4">
                    <p class="text-xs text-gray-500 uppercase font-medium mb-2">Peer Activity Summary</p>
                    <p class="text-sm text-gray-800">${escapeHtml(context.peer_activity_summary || 'N/A')}</p>
                </div>
            </div>
        `;
        container.appendChild(contextSection);
    }

    return container;
}

/**
 * Render wash trade specific sections matching downloadable report.
 * @param {Object} decision - Decision object
 * @returns {HTMLElement} WT sections container
 */
function renderWashTradeSections(decision) {
    const container = document.createElement('div');
    container.className = 'space-y-6';

    // Timing patterns - matching downloadable report layout
    if (decision.timing_patterns) {
        const timing = decision.timing_patterns;
        const timingSection = document.createElement('section');
        timingSection.className = 'bg-white rounded-lg shadow-md p-6';

        const preArrangedColor = timing.is_pre_arranged ? 'text-red-600' : 'text-green-600';

        timingSection.innerHTML = `
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                Timing Analysis
            </h2>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Time Delta</p>
                    <p class="text-xl font-bold text-gray-900">${escapeHtml(timing.time_delta_description || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Market Phase</p>
                    <p class="text-lg font-medium text-gray-700">${escapeHtml((timing.market_phase || '').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()))}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Liquidity</p>
                    <p class="text-lg font-medium text-gray-700">${escapeHtml((timing.liquidity_assessment || '').replace(/\b\w/g, l => l.toUpperCase()))}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Pre-Arranged</p>
                    <p class="text-lg font-bold ${preArrangedColor}">
                        ${timing.is_pre_arranged ? 'Yes' : 'No'} (${timing.pre_arrangement_confidence || 0}%)
                    </p>
                </div>
            </div>

            <div class="bg-amber-50 border border-amber-200 rounded-lg p-4">
                <p class="text-sm text-amber-900">${escapeHtml(timing.timing_analysis || '')}</p>
            </div>
        `;
        container.appendChild(timingSection);
    }

    // Counterparty analysis - matching downloadable report layout (side by side)
    if (decision.counterparty_pattern) {
        const cp = decision.counterparty_pattern;
        const cpSection = document.createElement('section');
        cpSection.className = 'bg-white rounded-lg shadow-md p-6';

        // Trade flow visualization
        const flowHtml = (cp.trade_flow || []).map(trade => {
            const sideColor = trade.side === 'BUY' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800';
            return `
                <div class="flex items-center">
                    <span class="w-8 h-8 rounded-full bg-blue-500 text-white flex items-center justify-center text-sm font-bold">
                        ${trade.sequence_number}
                    </span>
                    <div class="ml-3">
                        <p class="font-medium">${escapeHtml(trade.account_id)}</p>
                        <p class="text-xs">
                            <span class="px-2 py-0.5 rounded ${sideColor}">${trade.side}</span>
                            ${(trade.quantity || 0).toLocaleString()} @ $${(trade.price || 0).toFixed(2)}
                        </p>
                    </div>
                </div>
            `;
        }).join('');

        cpSection.innerHTML = `
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-teal-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"></path>
                </svg>
                Trade Flow Analysis
            </h2>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                    <h3 class="text-sm font-medium text-gray-700 mb-3">Trade Flow Sequence</h3>
                    <div class="space-y-4">
                        ${flowHtml}
                    </div>
                </div>

                <div>
                    <h3 class="text-sm font-medium text-gray-700 mb-3">Pattern Analysis</h3>
                    <div class="space-y-3">
                        <div class="flex justify-between items-center p-2 bg-gray-50 rounded">
                            <span class="text-sm text-gray-600">Circular Pattern</span>
                            <span class="font-medium ${cp.is_circular ? 'text-red-600' : 'text-green-600'}">
                                ${cp.is_circular ? 'Detected' : 'Not Detected'}
                            </span>
                        </div>
                        <div class="flex justify-between items-center p-2 bg-gray-50 rounded">
                            <span class="text-sm text-gray-600">Offsetting Trades</span>
                            <span class="font-medium ${cp.is_offsetting ? 'text-red-600' : 'text-green-600'}">
                                ${cp.is_offsetting ? 'Yes' : 'No'}
                            </span>
                        </div>
                        <div class="flex justify-between items-center p-2 bg-gray-50 rounded">
                            <span class="text-sm text-gray-600">Same Beneficial Owner</span>
                            <span class="font-medium ${cp.same_beneficial_owner ? 'text-red-600' : 'text-green-600'}">
                                ${cp.same_beneficial_owner ? 'Yes' : 'No'}
                            </span>
                        </div>
                        <div class="flex justify-between items-center p-2 bg-gray-50 rounded">
                            <span class="text-sm text-gray-600">Economic Purpose</span>
                            <span class="font-medium ${cp.economic_purpose_identified ? 'text-green-600' : 'text-red-600'}">
                                ${cp.economic_purpose_identified ? 'Identified' : 'Not Identified'}
                            </span>
                        </div>
                    </div>
                    ${cp.economic_purpose_description ? `
                        <div class="mt-3 p-3 bg-green-50 rounded">
                            <p class="text-sm text-green-800">${escapeHtml(cp.economic_purpose_description)}</p>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
        container.appendChild(cpSection);
    }

    // Historical patterns - matching downloadable report layout
    if (decision.historical_patterns) {
        const hp = decision.historical_patterns;
        const hpSection = document.createElement('section');
        hpSection.className = 'bg-white rounded-lg shadow-md p-6';

        const trendColors = {
            'increasing': 'text-red-600',
            'stable': 'text-yellow-600',
            'decreasing': 'text-green-600',
            'new': 'text-blue-600',
        };
        const trendColor = trendColors[hp.pattern_trend] || 'text-gray-600';
        const riskColor = hp.pattern_count >= 3 ? 'text-red-600' : hp.pattern_count >= 1 ? 'text-yellow-600' : 'text-green-600';
        const riskLevel = hp.pattern_count >= 3 ? 'High' : hp.pattern_count >= 1 ? 'Medium' : 'Low';

        hpSection.innerHTML = `
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
                </svg>
                Historical Pattern Analysis
            </h2>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Similar Patterns</p>
                    <p class="text-2xl font-bold text-gray-900">${hp.pattern_count || 0}</p>
                    <p class="text-xs text-gray-500">in last ${hp.time_window_days || 0} days</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Frequency</p>
                    <p class="text-lg font-medium text-gray-700">${escapeHtml(hp.average_frequency || 'N/A')}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Trend</p>
                    <p class="text-lg font-bold ${trendColor}">${escapeHtml((hp.pattern_trend || 'N/A').replace(/\b\w/g, l => l.toUpperCase()))}</p>
                </div>
                <div class="bg-gray-50 rounded-lg p-4 text-center">
                    <p class="text-xs text-gray-500 uppercase">Risk Level</p>
                    <p class="text-lg font-bold ${riskColor}">${riskLevel}</p>
                </div>
            </div>

            <div class="bg-gray-50 rounded-lg p-4">
                <p class="text-sm text-gray-700">${escapeHtml(hp.historical_analysis || '')}</p>
            </div>
        `;
        container.appendChild(hpSection);
    }

    // Regulatory flags - matching downloadable report with APAC note
    if (decision.regulatory_flags && decision.regulatory_flags.length > 0) {
        const regSection = document.createElement('section');
        regSection.className = 'bg-white rounded-lg shadow-md p-6';

        const flagsHtml = decision.regulatory_flags.map(flag => `
            <div class="flex items-start p-3 bg-red-50 rounded-lg">
                <svg class="w-5 h-5 text-red-500 mr-2 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                </svg>
                <span class="text-sm text-red-800">${escapeHtml(flag)}</span>
            </div>
        `).join('');

        regSection.innerHTML = `
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg class="w-5 h-5 mr-2 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                </svg>
                Regulatory Considerations (APAC Framework)
            </h2>

            <div class="space-y-3">
                ${flagsHtml}
            </div>

            <div class="mt-4 p-4 bg-blue-50 rounded-lg">
                <p class="text-sm text-blue-800">
                    <span class="font-medium">Note:</span> This analysis applies APAC regulatory standards including
                    Singapore MAS SFA, Hong Kong SFC SFO, Australia ASIC Corporations Act, and Japan FSA FIEA.
                </p>
            </div>
        `;
        container.appendChild(regSection);
    }

    return container;
}

/**
 * Render reasoning narrative section matching downloadable report.
 * Includes similar precedent in footer.
 * @param {Object} decision - Decision object
 * @returns {HTMLElement} Reasoning section
 */
function renderReasoningSection(decision) {
    const section = document.createElement('section');
    section.className = 'bg-white rounded-lg shadow-md p-6';

    // Split narrative into paragraphs for better formatting
    const narrative = decision.reasoning_narrative || 'No reasoning provided.';
    const paragraphsHtml = narrative.split('\n\n')
        .filter(p => p.trim())
        .map(p => `<p class="text-gray-700 leading-relaxed mb-4">${escapeHtml(p)}</p>`)
        .join('');

    // Similar precedent section
    const precedentHtml = decision.similar_precedent ? `
        <div class="mt-4 pt-4 border-t border-gray-200">
            <p class="text-sm text-gray-600">
                <span class="font-medium">Similar Precedent:</span>
                ${escapeHtml(decision.similar_precedent)}
            </p>
        </div>
    ` : '';

    section.innerHTML = `
        <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
            <svg class="w-5 h-5 mr-2 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
            </svg>
            Detailed Reasoning
        </h2>

        <div class="prose prose-sm max-w-none">
            ${paragraphsHtml}
        </div>

        ${precedentHtml}
    `;

    return section;
}

/**
 * Render data gaps section matching downloadable report.
 * @param {Array} dataGaps - Array of data gap strings
 * @returns {HTMLElement} Data gaps section
 */
function renderDataGapsSection(dataGaps) {
    const section = document.createElement('section');
    section.className = 'bg-white rounded-lg shadow-md p-6';

    const gapsHtml = dataGaps.map(gap => `
        <li class="flex items-start">
            <svg class="w-4 h-4 text-gray-400 mr-2 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"></path>
            </svg>
            <span class="text-gray-600">${escapeHtml(gap)}</span>
        </li>
    `).join('');

    section.innerHTML = `
        <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
            <svg class="w-5 h-5 mr-2 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
            </svg>
            Data Gaps &amp; Recommended Additional Investigation
        </h2>

        <p class="text-sm text-gray-600 mb-3">The following data would improve the analysis:</p>
        <ul class="space-y-2 text-sm">
            ${gapsHtml}
        </ul>
    `;

    return section;
}

/**
 * Render report footer matching downloadable report.
 * @param {string} alertType - Alert type
 * @returns {HTMLElement} Footer element
 */
function renderReportFooter(alertType) {
    const footer = document.createElement('footer');
    footer.className = 'text-center py-6 border-t border-gray-200';

    const isWashTrade = alertType === 'wash_trade' || alertType === 'WASH_TRADE';
    const analyzerName = isWashTrade ? 'SMARTS Wash Trade Analyzer' : 'SMARTS Alert False Positive Analyzer';
    const subtitle = isWashTrade
        ? 'AI-Powered Compliance Analysis | APAC Regulatory Framework | For Internal Use Only'
        : 'AI-Powered Compliance Analysis | For Internal Use Only';

    footer.innerHTML = `
        <p class="text-sm text-gray-500">
            Generated by <span class="font-medium">${analyzerName}</span>
        </p>
        <p class="text-xs text-gray-400 mt-1">
            ${subtitle}
        </p>
    `;

    return footer;
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
 * Matches the downloadable report format with owner nodes, tooltips, and highlighting.
 * @param {Object} network - Relationship network data
 */
function initCytoscapeGraph(network) {
    const container = document.getElementById('cytoscape-container');
    if (!container) {
        console.error('Cytoscape container not found');
        return;
    }

    console.log('Initializing Cytoscape graph');

    const cytoNodes = [];
    const cytoEdges = [];
    const uniqueOwners = {};

    // Map account nodes to Cytoscape format
    (network.nodes || []).forEach(node => {
        const shortLabel = node.account_id.length > 6 ? node.account_id.slice(-6) : node.account_id;
        cytoNodes.push({
            data: {
                id: node.account_id,
                label: shortLabel,
                fullId: node.account_id,
                nodeType: 'account',
                owner: node.beneficial_owner_name,
                ownerId: node.beneficial_owner_id,
                relationship: node.relationship_type,
                flagged: node.is_flagged,
            },
        });

        // Collect unique owners
        if (node.beneficial_owner_id && !uniqueOwners[node.beneficial_owner_id]) {
            uniqueOwners[node.beneficial_owner_id] = node.beneficial_owner_name;
        }
    });

    // Add beneficial owner nodes
    Object.entries(uniqueOwners).forEach(([ownerId, ownerName]) => {
        const displayName = ownerName && ownerName.length > 12 ? ownerName.slice(0, 12) + '...' : ownerName;
        cytoNodes.push({
            data: {
                id: ownerId,
                label: displayName || ownerId,
                fullName: ownerName,
                nodeType: 'owner',
            },
        });
    });

    // Map trade edges to Cytoscape format
    (network.edges || []).forEach((edge, idx) => {
        if (edge.edge_type === 'trade') {
            cytoEdges.push({
                data: {
                    id: `edge-trade-${idx}`,
                    source: edge.from_account,
                    target: edge.to_account,
                    edgeType: 'trade',
                    details: edge.trade_details || '',
                    suspicious: edge.is_suspicious,
                },
            });
        }
    });

    // Add ownership edges (from accounts to beneficial owners)
    (network.nodes || []).forEach((node, idx) => {
        if (node.beneficial_owner_id) {
            cytoEdges.push({
                data: {
                    id: `edge-ownership-${idx}`,
                    source: node.account_id,
                    target: node.beneficial_owner_id,
                    edgeType: 'ownership',
                    details: `Owned by ${node.beneficial_owner_name}`,
                    suspicious: false,
                },
            });
        }
    });

    // Initialize Cytoscape with styles matching downloadable report
    const cy = cytoscape({
        container: container,
        elements: { nodes: cytoNodes, edges: cytoEdges },
        style: [
            // Account nodes (circles)
            {
                selector: 'node[nodeType="account"]',
                style: {
                    'shape': 'ellipse',
                    'width': 50,
                    'height': 50,
                    'background-color': '#3B82F6',
                    'border-width': 2,
                    'border-color': '#ffffff',
                    'label': 'data(label)',
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'font-size': '10px',
                    'font-weight': '500',
                    'color': '#ffffff',
                },
            },
            // Flagged account nodes (red)
            {
                selector: 'node[nodeType="account"][?flagged]',
                style: {
                    'background-color': '#EF4444',
                },
            },
            // Beneficial owner nodes (rounded rectangles)
            {
                selector: 'node[nodeType="owner"]',
                style: {
                    'shape': 'round-rectangle',
                    'width': 80,
                    'height': 40,
                    'background-color': '#8B5CF6',
                    'border-width': 2,
                    'border-color': '#ffffff',
                    'label': 'data(label)',
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'font-size': '10px',
                    'font-weight': '500',
                    'color': '#ffffff',
                },
            },
            // Trade edges (solid with arrows)
            {
                selector: 'edge[edgeType="trade"]',
                style: {
                    'width': 2,
                    'line-color': '#9CA3AF',
                    'target-arrow-color': '#9CA3AF',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'arrow-scale': 1.2,
                },
            },
            // Suspicious trade edges (red, thicker)
            {
                selector: 'edge[edgeType="trade"][?suspicious]',
                style: {
                    'width': 3,
                    'line-color': '#EF4444',
                    'target-arrow-color': '#EF4444',
                },
            },
            // Ownership edges (dashed purple)
            {
                selector: 'edge[edgeType="ownership"]',
                style: {
                    'width': 1,
                    'line-color': '#8B5CF6',
                    'line-style': 'dashed',
                    'opacity': 0.5,
                    'curve-style': 'bezier',
                },
            },
            // Highlighted state
            {
                selector: '.highlighted',
                style: {
                    'border-color': '#FCD34D',
                    'border-width': 4,
                    'z-index': 999,
                },
            },
            // Faded state
            {
                selector: '.faded',
                style: {
                    'opacity': 0.25,
                },
            },
        ],
        layout: {
            name: 'cose',
            animate: true,
            animationDuration: 500,
            fit: true,
            padding: 50,
            nodeRepulsion: 8000,
            nodeOverlap: 20,
            idealEdgeLength: 100,
            edgeElasticity: 100,
            nestingFactor: 1.2,
            gravity: 0.25,
            numIter: 1000,
            initialTemp: 200,
            coolingFactor: 0.95,
            minTemp: 1.0,
        },
        minZoom: 0.3,
        maxZoom: 3,
        wheelSensitivity: 0.3,
    });

    // Fit graph to container
    cy.fit(50);

    // Fit button handler
    const fitBtn = document.getElementById('cy-fit-btn');
    if (fitBtn) {
        fitBtn.addEventListener('click', function() {
            cy.fit(50);
            cy.elements().removeClass('highlighted faded');
        });
    }

    // Click to highlight connected elements
    cy.on('tap', 'node', function(e) {
        const node = e.target;

        // Reset all elements
        cy.elements().removeClass('highlighted faded');

        // Highlight clicked node and its neighbors
        const neighborhood = node.neighborhood().add(node);
        neighborhood.addClass('highlighted');
        cy.elements().difference(neighborhood).addClass('faded');

        // Show info toast
        const data = node.data();
        if (data.nodeType === 'account') {
            showToast(`Account: ${data.fullId}\nOwner: ${data.owner}\nType: ${data.relationship}${data.flagged ? '\n⚠️ Flagged Account' : ''}`, 'info');
        } else if (data.nodeType === 'owner') {
            showToast(`Beneficial Owner: ${data.fullName || data.label}`, 'info');
        }
    });

    // Click on background to reset
    cy.on('tap', function(e) {
        if (e.target === cy) {
            cy.elements().removeClass('highlighted faded');
        }
    });

    console.log('Cytoscape graph initialized with', cytoNodes.length, 'nodes and', cytoEdges.length, 'edges');

    // Store reference for potential external access
    window.cyGraph = cy;
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
