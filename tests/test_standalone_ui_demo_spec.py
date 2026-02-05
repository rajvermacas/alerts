import json
from pathlib import Path


def _require_key(obj: dict, key: str, *, path: str) -> object:
    if key not in obj:
        raise KeyError(f"missing required key: {path}.{key}")
    return obj[key]


def _require_str(value: object, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{path} must be a non-empty string")
    return value


def _require_bool(value: object, *, path: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{path} must be a boolean")
    return value


def _require_number(value: object, *, path: str) -> float:
    if not isinstance(value, (int, float)):
        raise TypeError(f"{path} must be a number")
    return float(value)


def test_demo_json_pattern_graph_schema() -> None:
    demo_path = Path(__file__).resolve().parents[1] / "standalone_ui" / "data" / "demo.json"
    if not demo_path.exists():
        raise FileNotFoundError(f"missing demo spec: {demo_path}")

    spec = json.loads(demo_path.read_text(encoding="utf-8"))
    analysis_cards = _require_key(spec, "analysisCards", path="$")
    if not isinstance(analysis_cards, dict) or not analysis_cards:
        raise TypeError("$.analysisCards must be a non-empty object")

    trader_history = _require_key(analysis_cards, "traderHistoryAnalysis", path="$.analysisCards")
    if not isinstance(trader_history, dict):
        raise TypeError("$.analysisCards.traderHistoryAnalysis must be an object")

    pattern_graph = _require_key(trader_history, "patternGraph", path="$.analysisCards.traderHistoryAnalysis")
    if not isinstance(pattern_graph, dict):
        raise TypeError("$.analysisCards.traderHistoryAnalysis.patternGraph must be an object")

    nodes = _require_key(pattern_graph, "nodes", path="$.analysisCards.traderHistoryAnalysis.patternGraph")
    if not isinstance(nodes, list) or not nodes:
        raise TypeError("$.analysisCards.traderHistoryAnalysis.patternGraph.nodes must be a non-empty array")

    edges = _require_key(pattern_graph, "edges", path="$.analysisCards.traderHistoryAnalysis.patternGraph")
    if not isinstance(edges, list) or not edges:
        raise TypeError("$.analysisCards.traderHistoryAnalysis.patternGraph.edges must be a non-empty array")

    trader_nodes = 0
    for idx, node_obj in enumerate(nodes):
        path = f"$.analysisCards.traderHistoryAnalysis.patternGraph.nodes[{idx}]"
        if not isinstance(node_obj, dict):
            raise TypeError(f"{path} must be an object")

        _require_str(_require_key(node_obj, "id", path=path), path=f"{path}.id")
        _require_str(_require_key(node_obj, "label", path=path), path=f"{path}.label")
        node_type = _require_str(_require_key(node_obj, "type", path=path), path=f"{path}.type")
        size = _require_str(_require_key(node_obj, "size", path=path), path=f"{path}.size")
        if size not in {"small", "medium", "large"}:
            raise ValueError(f"{path}.size must be one of: small, medium, large")

        _require_bool(_require_key(node_obj, "isAnomaly", path=path), path=f"{path}.isAnomaly")
        _require_bool(_require_key(node_obj, "isBaseline", path=path), path=f"{path}.isBaseline")

        volume = _require_number(_require_key(node_obj, "volume", path=path), path=f"{path}.volume")
        if volume < 0:
            raise ValueError(f"{path}.volume must be >= 0")

        if node_type == "trader":
            trader_nodes += 1

    if trader_nodes != 1:
        raise ValueError(
            "$.analysisCards.traderHistoryAnalysis.patternGraph must contain exactly 1 trader node"
        )

    for idx, edge_obj in enumerate(edges):
        path = f"$.analysisCards.traderHistoryAnalysis.patternGraph.edges[{idx}]"
        if not isinstance(edge_obj, dict):
            raise TypeError(f"{path} must be an object")

        _require_str(_require_key(edge_obj, "id", path=path), path=f"{path}.id")
        _require_str(_require_key(edge_obj, "source", path=path), path=f"{path}.source")
        _require_str(_require_key(edge_obj, "target", path=path), path=f"{path}.target")
        _require_str(_require_key(edge_obj, "label", path=path), path=f"{path}.label")

        weight = _require_number(_require_key(edge_obj, "weight", path=path), path=f"{path}.weight")
        if weight <= 0:
            raise ValueError(f"{path}.weight must be > 0")

        _require_bool(_require_key(edge_obj, "isAnomaly", path=path), path=f"{path}.isAnomaly")

