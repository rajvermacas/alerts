"""Cytoscape.js network visualization for Wash Trade reports.

This module handles the interactive graph generation for relationship network
diagrams in wash trade analysis reports using the Cytoscape.js library.
"""

import html
import json
import logging
from typing import Dict, List, Any

from alerts.models.wash_trade import (
    RelationshipNetwork,
    RelationshipNode,
    RelationshipEdge,
)

logger = logging.getLogger(__name__)


# Color scheme matching Tailwind CSS theme
GRAPH_COLORS = {
    "flagged_node": "#EF4444",      # Red - directly involved in flagged trades
    "normal_node": "#3B82F6",       # Blue - related account
    "beneficial_owner": "#8B5CF6",   # Purple - beneficial owner node
    "suspicious_edge": "#EF4444",    # Red - suspicious trade flow
    "normal_edge": "#9CA3AF",        # Gray - normal trade flow
    "ownership_edge": "#8B5CF6",     # Purple - dashed ownership links
    "highlight": "#FCD34D",          # Yellow - highlight on hover/click
}


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return html.escape(str(text)) if text else ""


def _convert_nodes_to_cytoscape(
    nodes: List[RelationshipNode]
) -> List[Dict[str, Any]]:
    """Convert RelationshipNode objects to Cytoscape node format.

    Args:
        nodes: List of relationship nodes

    Returns:
        List of Cytoscape node data dictionaries
    """
    logger.debug(f"Converting {len(nodes)} nodes to Cytoscape format")

    cyto_nodes = []
    unique_owners: Dict[str, str] = {}  # owner_id -> owner_name

    # Add account nodes
    for node in nodes:
        cyto_nodes.append({
            "data": {
                "id": node.account_id,
                "label": node.account_id[-6:] if len(node.account_id) > 6 else node.account_id,
                "fullId": node.account_id,
                "type": "account",
                "owner": node.beneficial_owner_name,
                "ownerId": node.beneficial_owner_id,
                "relationship": node.relationship_type,
                "flagged": node.is_flagged,
            }
        })

        # Collect unique owners
        if node.beneficial_owner_id not in unique_owners:
            unique_owners[node.beneficial_owner_id] = node.beneficial_owner_name

    # Add beneficial owner nodes
    for owner_id, owner_name in unique_owners.items():
        display_name = owner_name[:12] + "..." if len(owner_name) > 12 else owner_name
        cyto_nodes.append({
            "data": {
                "id": owner_id,
                "label": display_name,
                "fullName": owner_name,
                "type": "owner",
            }
        })

    logger.debug(f"Created {len(cyto_nodes)} Cytoscape nodes ({len(unique_owners)} owners)")
    return cyto_nodes


def _convert_edges_to_cytoscape(
    edges: List[RelationshipEdge],
    nodes: List[RelationshipNode]
) -> List[Dict[str, Any]]:
    """Convert RelationshipEdge objects to Cytoscape edge format.

    Args:
        edges: List of relationship edges
        nodes: List of relationship nodes (for ownership edges)

    Returns:
        List of Cytoscape edge data dictionaries
    """
    logger.debug(f"Converting {len(edges)} edges to Cytoscape format")

    cyto_edges = []

    # Add trade edges
    for i, edge in enumerate(edges):
        if edge.edge_type == "trade":
            cyto_edges.append({
                "data": {
                    "id": f"edge-trade-{i}",
                    "source": edge.from_account,
                    "target": edge.to_account,
                    "type": "trade",
                    "details": edge.trade_details or "",
                    "suspicious": edge.is_suspicious,
                }
            })

    # Add ownership edges (from accounts to beneficial owners)
    for i, node in enumerate(nodes):
        cyto_edges.append({
            "data": {
                "id": f"edge-ownership-{i}",
                "source": node.account_id,
                "target": node.beneficial_owner_id,
                "type": "ownership",
                "details": f"Owned by {node.beneficial_owner_name}",
                "suspicious": False,
            }
        })

    logger.debug(f"Created {len(cyto_edges)} Cytoscape edges")
    return cyto_edges


def _generate_cytoscape_styles() -> str:
    """Generate Cytoscape.js stylesheet as JSON string.

    Returns:
        JSON string of Cytoscape styles
    """
    styles = [
        # Account nodes (circles)
        {
            "selector": "node[type='account']",
            "style": {
                "shape": "ellipse",
                "width": 50,
                "height": 50,
                "background-color": GRAPH_COLORS["normal_node"],
                "border-width": 2,
                "border-color": "#ffffff",
                "label": "data(label)",
                "text-valign": "center",
                "text-halign": "center",
                "font-size": "10px",
                "font-weight": "500",
                "color": "#ffffff",
                "text-outline-width": 0,
            }
        },
        # Flagged account nodes (red)
        {
            "selector": "node[type='account'][?flagged]",
            "style": {
                "background-color": GRAPH_COLORS["flagged_node"],
            }
        },
        # Beneficial owner nodes (rounded rectangles)
        {
            "selector": "node[type='owner']",
            "style": {
                "shape": "round-rectangle",
                "width": 80,
                "height": 40,
                "background-color": GRAPH_COLORS["beneficial_owner"],
                "border-width": 2,
                "border-color": "#ffffff",
                "label": "data(label)",
                "text-valign": "center",
                "text-halign": "center",
                "font-size": "10px",
                "font-weight": "500",
                "color": "#ffffff",
                "text-outline-width": 0,
            }
        },
        # Trade edges (solid with arrows)
        {
            "selector": "edge[type='trade']",
            "style": {
                "width": 2,
                "line-color": GRAPH_COLORS["normal_edge"],
                "target-arrow-color": GRAPH_COLORS["normal_edge"],
                "target-arrow-shape": "triangle",
                "curve-style": "bezier",
                "arrow-scale": 1.2,
            }
        },
        # Suspicious trade edges (red, thicker)
        {
            "selector": "edge[type='trade'][?suspicious]",
            "style": {
                "width": 3,
                "line-color": GRAPH_COLORS["suspicious_edge"],
                "target-arrow-color": GRAPH_COLORS["suspicious_edge"],
            }
        },
        # Ownership edges (dashed purple)
        {
            "selector": "edge[type='ownership']",
            "style": {
                "width": 1,
                "line-color": GRAPH_COLORS["ownership_edge"],
                "line-style": "dashed",
                "line-dash-pattern": [6, 3],
                "opacity": 0.5,
                "curve-style": "bezier",
            }
        },
        # Highlighted state (on hover/select)
        {
            "selector": ".highlighted",
            "style": {
                "border-color": GRAPH_COLORS["highlight"],
                "border-width": 4,
                "z-index": 999,
            }
        },
        # Faded state (neighbors not selected)
        {
            "selector": ".faded",
            "style": {
                "opacity": 0.25,
            }
        },
    ]

    return json.dumps(styles)


def _generate_cytoscape_layout() -> str:
    """Generate Cytoscape.js layout configuration.

    Returns:
        JSON string of layout configuration
    """
    layout = {
        "name": "cose",
        "animate": True,
        "animationDuration": 500,
        "fit": True,
        "padding": 50,
        "nodeRepulsion": 8000,
        "nodeOverlap": 20,
        "idealEdgeLength": 100,
        "edgeElasticity": 100,
        "nestingFactor": 1.2,
        "gravity": 0.25,
        "numIter": 1000,
        "initialTemp": 200,
        "coolingFactor": 0.95,
        "minTemp": 1.0,
    }

    return json.dumps(layout)


def _generate_javascript_code(
    nodes_json: str,
    edges_json: str,
    styles_json: str,
    layout_json: str,
    container_id: str
) -> str:
    """Generate the Cytoscape.js initialization JavaScript code.

    Args:
        nodes_json: JSON string of nodes
        edges_json: JSON string of edges
        styles_json: JSON string of styles
        layout_json: JSON string of layout config
        container_id: HTML container element ID

    Returns:
        JavaScript code string
    """
    return f"""
    <script>
    (function() {{
        // Wait for Cytoscape to be available
        function initGraph() {{
            if (typeof cytoscape === 'undefined') {{
                setTimeout(initGraph, 100);
                return;
            }}

            var cy = cytoscape({{
                container: document.getElementById('{container_id}'),
                elements: {{
                    nodes: {nodes_json},
                    edges: {edges_json}
                }},
                style: {styles_json},
                layout: {layout_json},
                minZoom: 0.3,
                maxZoom: 3,
                wheelSensitivity: 0.3,
            }});

            // Create tooltip element
            var tooltip = document.createElement('div');
            tooltip.id = '{container_id}-tooltip';
            tooltip.style.cssText = 'position:absolute;background:#1F2937;color:white;padding:8px 12px;border-radius:6px;font-size:12px;pointer-events:none;z-index:1000;display:none;max-width:250px;box-shadow:0 4px 6px rgba(0,0,0,0.3);';
            document.getElementById('{container_id}').parentNode.appendChild(tooltip);

            // Hover tooltip for nodes
            cy.on('mouseover', 'node', function(e) {{
                var node = e.target;
                var data = node.data();
                var html = '';

                if (data.type === 'account') {{
                    html = '<div style="font-weight:600;margin-bottom:4px;">' + (data.fullId || data.id) + '</div>';
                    html += '<div style="color:#9CA3AF;">Type: ' + data.relationship + '</div>';
                    html += '<div style="color:#9CA3AF;">Owner: ' + data.owner + '</div>';
                    if (data.flagged) {{
                        html += '<div style="color:#EF4444;margin-top:4px;font-weight:500;">⚠ Flagged Account</div>';
                    }}
                }} else if (data.type === 'owner') {{
                    html = '<div style="font-weight:600;margin-bottom:4px;">Beneficial Owner</div>';
                    html += '<div style="color:#9CA3AF;">' + (data.fullName || data.label) + '</div>';
                }}

                tooltip.innerHTML = html;
                tooltip.style.display = 'block';
            }});

            // Hover tooltip for edges
            cy.on('mouseover', 'edge', function(e) {{
                var edge = e.target;
                var data = edge.data();
                var html = '';

                if (data.type === 'trade') {{
                    html = '<div style="font-weight:600;margin-bottom:4px;">Trade</div>';
                    html += '<div style="color:#9CA3AF;">' + data.source + ' → ' + data.target + '</div>';
                    if (data.details) {{
                        html += '<div style="margin-top:4px;">' + data.details + '</div>';
                    }}
                    if (data.suspicious) {{
                        html += '<div style="color:#EF4444;margin-top:4px;font-weight:500;">⚠ Suspicious Trade</div>';
                    }}
                }} else {{
                    html = '<div style="font-weight:600;margin-bottom:4px;">Ownership Link</div>';
                    html += '<div style="color:#9CA3AF;">' + data.details + '</div>';
                }}

                tooltip.innerHTML = html;
                tooltip.style.display = 'block';
            }});

            // Update tooltip position on mouse move
            cy.on('mousemove', function(e) {{
                if (tooltip.style.display === 'block') {{
                    var pos = e.renderedPosition || e.position;
                    var container = document.getElementById('{container_id}');
                    var rect = container.getBoundingClientRect();
                    tooltip.style.left = (rect.left + pos.x + 15) + 'px';
                    tooltip.style.top = (rect.top + pos.y + 15) + 'px';
                }}
            }});

            // Hide tooltip on mouseout
            cy.on('mouseout', 'node, edge', function() {{
                tooltip.style.display = 'none';
            }});

            // Click to highlight connected elements
            cy.on('tap', 'node', function(e) {{
                var node = e.target;

                // Reset all elements
                cy.elements().removeClass('highlighted faded');

                // Highlight clicked node and its neighbors
                var neighborhood = node.neighborhood().add(node);
                neighborhood.addClass('highlighted');
                cy.elements().difference(neighborhood).addClass('faded');
            }});

            // Click on background to reset
            cy.on('tap', function(e) {{
                if (e.target === cy) {{
                    cy.elements().removeClass('highlighted faded');
                }}
            }});

            // Fit button handler
            document.getElementById('{container_id}-fit-btn').addEventListener('click', function() {{
                cy.fit(50);
                cy.elements().removeClass('highlighted faded');
            }});

            // Store cy instance for potential external access
            window.{container_id.replace('-', '_')}_cy = cy;
        }}

        initGraph();
    }})();
    </script>
    """


def render_relationship_network_graph(
    network: RelationshipNetwork,
    escape_fn=None
) -> str:
    """Render the complete interactive Cytoscape.js relationship network.

    Args:
        network: RelationshipNetwork containing nodes and edges
        escape_fn: Optional HTML escape function (defaults to escape_html)

    Returns:
        Complete HTML section with embedded JavaScript visualization
    """
    if escape_fn is None:
        escape_fn = escape_html

    logger.info("Generating Cytoscape.js relationship network visualization")

    nodes = network.nodes
    edges = network.edges

    if not nodes:
        logger.warning("No nodes in relationship network, returning empty section")
        return ""

    # Generate unique container ID
    container_id = "cy-network"

    # Convert data to Cytoscape format
    cyto_nodes = _convert_nodes_to_cytoscape(nodes)
    cyto_edges = _convert_edges_to_cytoscape(edges, nodes)

    # Generate JSON strings
    nodes_json = json.dumps(cyto_nodes)
    edges_json = json.dumps(cyto_edges)
    styles_json = _generate_cytoscape_styles()
    layout_json = _generate_cytoscape_layout()

    # Generate JavaScript code
    js_code = _generate_javascript_code(
        nodes_json, edges_json, styles_json, layout_json, container_id
    )

    logger.info(f"Generated graph with {len(cyto_nodes)} nodes and {len(cyto_edges)} edges")

    return f"""
    <!-- Cytoscape.js CDN -->
    <script src="https://unpkg.com/cytoscape@3.29.2/dist/cytoscape.min.js"></script>

    <!-- Relationship Network Visualization -->
    <section class="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
            <svg class="w-5 h-5 mr-2 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
            </svg>
            Relationship Network
        </h2>

        <!-- Graph Controls -->
        <div class="flex justify-end mb-2">
            <button id="{container_id}-fit-btn"
                    class="px-3 py-1 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-md transition-colors flex items-center gap-1">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path>
                </svg>
                Fit to View
            </button>
        </div>

        <!-- Graph Container -->
        <div id="{container_id}"
             style="width: 100%; height: 450px; border: 1px solid #E5E7EB; border-radius: 8px; background: #F9FAFB;">
        </div>

        <!-- Legend -->
        <div class="mt-4 flex flex-wrap justify-center gap-6 text-sm">
            <div class="flex items-center">
                <div class="w-4 h-4 rounded-full mr-2" style="background-color: {GRAPH_COLORS['flagged_node']};"></div>
                <span class="text-gray-700">Flagged Account</span>
            </div>
            <div class="flex items-center">
                <div class="w-4 h-4 rounded-full mr-2" style="background-color: {GRAPH_COLORS['normal_node']};"></div>
                <span class="text-gray-700">Related Account</span>
            </div>
            <div class="flex items-center">
                <div class="w-4 h-4 rounded mr-2" style="background-color: {GRAPH_COLORS['beneficial_owner']};"></div>
                <span class="text-gray-700">Beneficial Owner</span>
            </div>
            <div class="flex items-center">
                <div class="w-8 h-0.5 mr-2" style="background-color: {GRAPH_COLORS['suspicious_edge']};"></div>
                <span class="text-gray-700">Suspicious Trade</span>
            </div>
            <div class="flex items-center">
                <div class="w-8 h-0.5 mr-2 border-t-2 border-dashed" style="border-color: {GRAPH_COLORS['ownership_edge']};"></div>
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
                {escape_fn(network.pattern_description)}
            </p>
            <p class="text-sm text-gray-500 mt-1">
                <span class="font-medium">Confidence:</span> {network.pattern_confidence}%
            </p>
        </div>
    </section>

    {js_code}
    """
