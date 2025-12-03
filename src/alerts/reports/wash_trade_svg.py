"""SVG network visualization for Wash Trade reports.

This module handles the SVG generation for relationship network
diagrams in wash trade analysis reports.
"""

import logging
import math
from typing import Dict, List, Tuple

from alerts.models.wash_trade import (
    RelationshipNetwork,
    RelationshipNode,
    RelationshipEdge,
)

logger = logging.getLogger(__name__)


# SVG colors for nodes and edges
SVG_COLORS = {
    "flagged_node": "#EF4444",  # Red
    "normal_node": "#3B82F6",   # Blue
    "beneficial_owner": "#8B5CF6",  # Purple
    "suspicious_edge": "#EF4444",  # Red
    "normal_edge": "#9CA3AF",   # Gray
    "ownership_edge": "#8B5CF6",  # Purple dashed
}


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    import html
    return html.escape(str(text)) if text else ""


def generate_svg_edges(
    edges: List[RelationshipEdge],
    positions: Dict[str, Tuple[float, float]]
) -> str:
    """Generate SVG edge elements for trade flows.

    Args:
        edges: List of relationship edges
        positions: Dictionary mapping account IDs to (x, y) positions

    Returns:
        SVG elements string for edges
    """
    svg_parts = []

    for edge in edges:
        if edge.edge_type != "trade":
            continue

        if edge.from_account not in positions or edge.to_account not in positions:
            continue

        x1, y1 = positions[edge.from_account]
        x2, y2 = positions[edge.to_account]

        color = SVG_COLORS["suspicious_edge"] if edge.is_suspicious else SVG_COLORS["normal_edge"]
        stroke_width = 3 if edge.is_suspicious else 2

        # Add arrow marker
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2

        svg_parts.append(f"""
            <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"
                  stroke="{color}" stroke-width="{stroke_width}"
                  marker-end="url(#arrowhead-{'red' if edge.is_suspicious else 'gray'})"/>
            <text x="{mid_x}" y="{mid_y - 10}" text-anchor="middle"
                  class="text-xs fill-gray-600">{escape_html(edge.trade_details or '')}</text>
        """)

    # Add arrow marker definitions
    markers = """
        <defs>
            <marker id="arrowhead-red" markerWidth="10" markerHeight="7"
                    refX="9" refY="3.5" orient="auto">
                <polygon points="0 0, 10 3.5, 0 7" fill="#EF4444"/>
            </marker>
            <marker id="arrowhead-gray" markerWidth="10" markerHeight="7"
                    refX="9" refY="3.5" orient="auto">
                <polygon points="0 0, 10 3.5, 0 7" fill="#9CA3AF"/>
            </marker>
        </defs>
    """

    return markers + "\n".join(svg_parts)


def generate_svg_ownership_edges(
    nodes: List[RelationshipNode],
    account_positions: Dict[str, Tuple[float, float]],
    owner_positions: Dict[str, Tuple[float, float]]
) -> str:
    """Generate SVG dashed edges for ownership relationships.

    Args:
        nodes: List of relationship nodes
        account_positions: Dictionary mapping account IDs to (x, y) positions
        owner_positions: Dictionary mapping owner IDs to (x, y) positions

    Returns:
        SVG elements string for ownership edges
    """
    svg_parts = []

    for node in nodes:
        if node.account_id not in account_positions:
            continue
        if node.beneficial_owner_id not in owner_positions:
            continue

        x1, y1 = account_positions[node.account_id]
        x2, y2 = owner_positions[node.beneficial_owner_id]

        svg_parts.append(f"""
            <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"
                  stroke="{SVG_COLORS['ownership_edge']}"
                  stroke-width="1" stroke-dasharray="5,5" opacity="0.5"/>
        """)

    return "\n".join(svg_parts)


def generate_svg_nodes(
    nodes: List[RelationshipNode],
    positions: Dict[str, Tuple[float, float]]
) -> str:
    """Generate SVG node elements for accounts.

    Args:
        nodes: List of relationship nodes
        positions: Dictionary mapping account IDs to (x, y) positions

    Returns:
        SVG elements string for account nodes
    """
    svg_parts = []

    for node in nodes:
        if node.account_id not in positions:
            continue

        x, y = positions[node.account_id]
        color = SVG_COLORS["flagged_node"] if node.is_flagged else SVG_COLORS["normal_node"]

        svg_parts.append(f"""
            <circle cx="{x}" cy="{y}" r="25" fill="{color}" stroke="white" stroke-width="2"/>
            <text x="{x}" y="{y + 4}" text-anchor="middle" class="text-xs fill-white font-medium">
                {escape_html(node.account_id[-6:])}
            </text>
            <text x="{x}" y="{y + 45}" text-anchor="middle" class="text-xs fill-gray-600">
                {escape_html(node.relationship_type)}
            </text>
        """)

    return "\n".join(svg_parts)


def generate_svg_owners(
    owners: Dict[str, str],
    positions: Dict[str, Tuple[float, float]]
) -> str:
    """Generate SVG node elements for beneficial owners.

    Args:
        owners: Dictionary mapping owner IDs to owner names
        positions: Dictionary mapping owner IDs to (x, y) positions

    Returns:
        SVG elements string for owner nodes
    """
    svg_parts = []

    for owner_id, owner_name in owners.items():
        if owner_id not in positions:
            continue

        x, y = positions[owner_id]

        # Truncate name if too long
        display_name = owner_name[:10] + "..." if len(owner_name) > 10 else owner_name

        svg_parts.append(f"""
            <rect x="{x - 35}" y="{y - 20}" width="70" height="40" rx="5"
                  fill="{SVG_COLORS['beneficial_owner']}" stroke="white" stroke-width="2"/>
            <text x="{x}" y="{y + 5}" text-anchor="middle" class="text-xs fill-white font-medium">
                {escape_html(display_name)}
            </text>
        """)

    return "\n".join(svg_parts)


def render_relationship_network_svg(
    network: RelationshipNetwork,
    escape_fn=None
) -> str:
    """Render the complete SVG relationship network visualization.

    Args:
        network: RelationshipNetwork containing nodes and edges
        escape_fn: Optional HTML escape function (defaults to escape_html)

    Returns:
        Complete HTML section with SVG visualization
    """
    if escape_fn is None:
        escape_fn = escape_html

    nodes = network.nodes
    edges = network.edges

    if not nodes:
        return ""

    # Layout calculation - circular layout for account nodes
    # with beneficial owner in center
    svg_width = 600
    svg_height = 400
    center_x = svg_width / 2
    center_y = svg_height / 2
    radius = 120

    # Position account nodes in a circle
    account_positions: Dict[str, Tuple[float, float]] = {}
    owner_positions: Dict[str, Tuple[float, float]] = {}

    num_accounts = len([n for n in nodes if n.relationship_type != "beneficial_owner"])
    angle_step = 2 * math.pi / max(num_accounts, 1)

    account_idx = 0
    for node in nodes:
        if node.relationship_type == "beneficial_owner":
            owner_positions[node.account_id] = (center_x, center_y)
        else:
            angle = account_idx * angle_step - math.pi / 2
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            account_positions[node.account_id] = (x, y)
            account_idx += 1

    # Collect unique beneficial owners
    unique_owners = {}
    for node in nodes:
        if node.beneficial_owner_id not in unique_owners:
            unique_owners[node.beneficial_owner_id] = node.beneficial_owner_name

    # Position owners in inner circle
    owner_radius = 50
    num_owners = len(unique_owners)
    owner_angle_step = 2 * math.pi / max(num_owners, 1)
    owner_idx = 0
    for owner_id in unique_owners:
        angle = owner_idx * owner_angle_step - math.pi / 2
        x = center_x + owner_radius * math.cos(angle)
        y = center_y + owner_radius * math.sin(angle)
        owner_positions[owner_id] = (x, y)
        owner_idx += 1

    # Generate SVG elements
    edges_svg = generate_svg_edges(edges, account_positions)
    ownership_edges_svg = generate_svg_ownership_edges(nodes, account_positions, owner_positions)
    nodes_svg = generate_svg_nodes(nodes, account_positions)
    owners_svg = generate_svg_owners(unique_owners, owner_positions)

    return f"""
    <!-- Relationship Network Visualization -->
    <section class="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
            <svg class="w-5 h-5 mr-2 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
            </svg>
            Relationship Network
        </h2>

        <div class="flex justify-center">
            <svg width="{svg_width}" height="{svg_height}" class="border border-gray-200 rounded-lg bg-gray-50">
                <!-- Edges (trade flows) -->
                {edges_svg}
                <!-- Ownership edges -->
                {ownership_edges_svg}
                <!-- Account nodes -->
                {nodes_svg}
                <!-- Beneficial owner nodes -->
                {owners_svg}
            </svg>
        </div>

        <!-- Legend -->
        <div class="mt-4 flex flex-wrap justify-center gap-6 text-sm">
            <div class="flex items-center">
                <div class="w-4 h-4 rounded-full bg-red-500 mr-2"></div>
                <span>Flagged Account</span>
            </div>
            <div class="flex items-center">
                <div class="w-4 h-4 rounded-full bg-blue-500 mr-2"></div>
                <span>Related Account</span>
            </div>
            <div class="flex items-center">
                <div class="w-4 h-4 rounded-full bg-purple-500 mr-2"></div>
                <span>Beneficial Owner</span>
            </div>
            <div class="flex items-center">
                <div class="w-8 h-0.5 bg-red-500 mr-2"></div>
                <span>Suspicious Trade</span>
            </div>
            <div class="flex items-center">
                <div class="w-8 h-0.5 bg-gray-400 mr-2 border-dashed border-t-2"></div>
                <span>Ownership Link</span>
            </div>
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
    </section>"""
