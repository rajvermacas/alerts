import { createLogger } from './logger.js';

const logger = createLogger('spec_loader');

function fail(path, msg) {
    throw new Error(`spec.${path}: ${msg}`);
}

function assertOptionalString(value, path) {
    if (value === undefined) {
        return undefined;
    }
    return assertString(value, path);
}

function assertObject(value, path) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        fail(path, 'expected object');
    }
    return value;
}

function assertArray(value, path) {
    if (!Array.isArray(value)) {
        fail(path, 'expected array');
    }
    return value;
}

function assertString(value, path) {
    if (typeof value !== 'string' || value.trim().length === 0) {
        fail(path, 'expected non-empty string');
    }
    return value;
}

function assertNumber(value, path) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        fail(path, 'expected number');
    }
    return value;
}

function assertEnum(value, path, allowed) {
    const str = assertString(value, path);
    if (!allowed.includes(str)) {
        fail(path, `expected one of: ${allowed.join(', ')}`);
    }
    return str;
}

function assertNonNegativeNumber(value, path) {
    const num = assertNumber(value, path);
    if (num < 0) {
        fail(path, 'must be >= 0');
    }
    return num;
}

function assertIsoTimestamp(value, path) {
    const ts = assertString(value, path);
    const date = new Date(ts);
    if (Number.isNaN(date.getTime())) {
        fail(path, 'expected ISO timestamp string');
    }
    return ts;
}

function validateExecutionFlow(spec) {
    const flow = assertObject(spec.executionFlow, 'executionFlow');

    const nodes = assertArray(flow.nodes, 'executionFlow.nodes');
    const edges = assertArray(flow.edges, 'executionFlow.edges');

    const allowedKinds = ['start', 'step', 'service', 'evaluation', 'complete'];
    const nodeIds = new Set();

    nodes.forEach((n, i) => {
        const node = assertObject(n, `executionFlow.nodes[${i}]`);
        const id = assertString(node.id, `executionFlow.nodes[${i}].id`);
        if (nodeIds.has(id)) {
            fail(`executionFlow.nodes[${i}].id`, `duplicate id '${id}'`);
        }
        nodeIds.add(id);
        assertString(node.label, `executionFlow.nodes[${i}].label`);
        assertEnum(node.kind, `executionFlow.nodes[${i}].kind`, allowedKinds);
    });

    const edgeIds = new Set();
    edges.forEach((e, i) => {
        const edge = assertObject(e, `executionFlow.edges[${i}]`);
        const id = assertString(edge.id, `executionFlow.edges[${i}].id`);
        if (edgeIds.has(id)) {
            fail(`executionFlow.edges[${i}].id`, `duplicate id '${id}'`);
        }
        edgeIds.add(id);

        const source = assertString(edge.source, `executionFlow.edges[${i}].source`);
        const target = assertString(edge.target, `executionFlow.edges[${i}].target`);
        if (!nodeIds.has(source)) {
            fail(`executionFlow.edges[${i}].source`, `unknown node id '${source}'`);
        }
        if (!nodeIds.has(target)) {
            fail(`executionFlow.edges[${i}].target`, `unknown node id '${target}'`);
        }
    });

    return flow;
}

function validateDagUpdates(value, path) {
    if (value === undefined) {
        return undefined;
    }

    const updates = assertArray(value, path);
    const allowedStates = ['pending', 'active', 'completed', 'error'];
    updates.forEach((u, i) => {
        const update = assertObject(u, `${path}[${i}]`);
        assertString(update.nodeId, `${path}[${i}].nodeId`);
        assertEnum(update.state, `${path}[${i}].state`, allowedStates);
    });
    return updates;
}

function validateTimelineEvent(event, index) {
    const base = `timeline.events[${index}]`;
    const obj = assertObject(event, base);

    assertNonNegativeNumber(obj.delayMs, `${base}.delayMs`);
    assertString(obj.type, `${base}.type`);
    assertIsoTimestamp(obj.timestamp, `${base}.timestamp`);
    assertString(obj.message, `${base}.message`);
    assertString(obj.icon, `${base}.icon`);
    assertString(obj.color, `${base}.color`);

    if (obj.durationSeconds !== undefined) {
        assertNumber(obj.durationSeconds, `${base}.durationSeconds`);
    }
    if (obj.outputSummary !== undefined) {
        assertString(obj.outputSummary, `${base}.outputSummary`);
    }
    if (obj.toolName !== undefined) {
        assertString(obj.toolName, `${base}.toolName`);
    }
    if (obj.agentName !== undefined) {
        assertString(obj.agentName, `${base}.agentName`);
    }
    obj.dagNodeId = assertOptionalString(obj.dagNodeId, `${base}.dagNodeId`);
    obj.dagUpdates = validateDagUpdates(obj.dagUpdates, `${base}.dagUpdates`);

    return obj;
}

function validateGraphs(spec) {
    if (spec.graphs === undefined) {
        return;
    }

    const graphs = assertObject(spec.graphs, 'graphs');
    if (graphs.relationshipNetwork === undefined) {
        return;
    }

    const rn = assertObject(graphs.relationshipNetwork, 'graphs.relationshipNetwork');
    assertString(rn.title, 'graphs.relationshipNetwork.title');
    assertString(rn.patternType, 'graphs.relationshipNetwork.patternType');
    assertNumber(rn.patternConfidence, 'graphs.relationshipNetwork.patternConfidence');
    assertString(rn.patternDescription, 'graphs.relationshipNetwork.patternDescription');

    const nodes = assertArray(rn.nodes, 'graphs.relationshipNetwork.nodes');
    nodes.forEach((n, i) => {
        const node = assertObject(n, `graphs.relationshipNetwork.nodes[${i}]`);
        assertString(node.id, `graphs.relationshipNetwork.nodes[${i}].id`);
        assertString(node.owner, `graphs.relationshipNetwork.nodes[${i}].owner`);
        assertString(node.type, `graphs.relationshipNetwork.nodes[${i}].type`);
        if (typeof node.flagged !== 'boolean') {
            fail(`graphs.relationshipNetwork.nodes[${i}].flagged`, 'expected boolean');
        }
    });

    const edges = assertArray(rn.edges, 'graphs.relationshipNetwork.edges');
    edges.forEach((e, i) => {
        const edge = assertObject(e, `graphs.relationshipNetwork.edges[${i}]`);
        assertString(edge.id, `graphs.relationshipNetwork.edges[${i}].id`);
        assertString(edge.source, `graphs.relationshipNetwork.edges[${i}].source`);
        assertString(edge.target, `graphs.relationshipNetwork.edges[${i}].target`);
        assertString(edge.type, `graphs.relationshipNetwork.edges[${i}].type`);
        assertString(edge.label, `graphs.relationshipNetwork.edges[${i}].label`);
        if (typeof edge.suspicious !== 'boolean') {
            fail(`graphs.relationshipNetwork.edges[${i}].suspicious`, 'expected boolean');
        }
    });
}

export function validateSpec(spec) {
    const root = assertObject(spec, '');

    const page = assertObject(root.page, 'page');
    assertString(page.appTitle, 'page.appTitle');
    assertString(page.pageTitle, 'page.pageTitle');
    assertString(page.subtitle, 'page.subtitle');

    root.executionFlow = validateExecutionFlow(root);

    const timeline = assertObject(root.timeline, 'timeline');
    const events = assertArray(timeline.events, 'timeline.events');
    events.forEach((evt, idx) => validateTimelineEvent(evt, idx));

    const cards = assertObject(root.cards, 'cards');
    Object.keys(cards).forEach((key) => assertString(key, `cards['${key}'] (key)`));

    validateGraphs(root);

    logger.info('validated spec', {
        events: root.timeline.events.length,
        cards: Object.keys(root.cards).length,
        executionNodes: root.executionFlow.nodes.length,
        executionEdges: root.executionFlow.edges.length,
        hasRelationshipNetwork: Boolean(root.graphs?.relationshipNetwork),
    });

    return root;
}

export async function loadSpecFromDom() {
    const src = document.body?.dataset?.specSrc;
    if (!src) {
        throw new Error('spec_loader: missing required body[data-spec-src]');
    }

    logger.info('loading spec', { src });

    const res = await fetch(src, { cache: 'no-store' });
    if (!res.ok) {
        throw new Error(`spec_loader: fetch failed (${res.status}) for ${src}`);
    }

    const json = await res.json();
    return validateSpec(json);
}
