"""Matplotlib rendering for evaluator-produced network visualizations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.automata import HealthState
from language.evaluator import Visualization

if TYPE_CHECKING:
    from matplotlib.figure import Figure


STATE_COLORS = {
    HealthState.NORMAL: "#2E8B57",
    HealthState.WARNING: "#F4D03F",
    HealthState.FAILURE: "#D64541",
}
LAYOUT_SEED = 42


class VisualizationDependencyError(RuntimeError):
    """Raised when optional graph-rendering dependencies are unavailable."""


def _load_dependencies():
    try:
        import matplotlib.pyplot as plt
        import networkx as nx
        from matplotlib.patches import Patch
    except ImportError as exc:
        raise VisualizationDependencyError(
            "La visualización requiere Matplotlib y NetworkX."
        ) from exc
    return nx, plt, Patch


def build_figure(data: Visualization) -> Figure:
    """Build a deterministic undirected graph figure from an immutable snapshot."""
    if not isinstance(data, Visualization):
        raise TypeError("data must be a Visualization result.")

    nx, plt, patch_type = _load_dependencies()
    graph = nx.Graph()
    graph.add_nodes_from(device.device_id for device in data.devices)
    graph.add_edges_from(
        (connection.first, connection.second) for connection in data.connections
    )
    positions = nx.spring_layout(graph, seed=LAYOUT_SEED)

    figure, axes = plt.subplots(figsize=(10, 7))
    node_colors = [STATE_COLORS[device.health] for device in data.devices]
    nx.draw_networkx_edges(graph, positions, ax=axes, width=1.5, edge_color="#6B7280")
    nx.draw_networkx_nodes(
        graph,
        positions,
        ax=axes,
        node_color=node_colors,
        node_size=1_500,
        edgecolors="#1F2937",
        linewidths=1.0,
    )
    nx.draw_networkx_labels(graph, positions, ax=axes, font_size=9)

    legend = [
        patch_type(facecolor=color, edgecolor="#1F2937", label=state.value)
        for state, color in STATE_COLORS.items()
    ]
    axes.legend(handles=legend, title="Diagnóstico", loc="best")
    axes.set_title("Network Graph Analyzer — Topología física y salud")
    axes.set_axis_off()
    figure.tight_layout()
    return figure


def show_figure(figure: Figure) -> None:
    """Display a previously built figure without blocking the console loop."""
    _, plt, _ = _load_dependencies()
    plt.figure(figure.number)
    plt.show(block=False)


def save_figure(figure: Figure, path: str | Path, *, dpi: int = 150) -> Path:
    """Save a previously built figure as a PNG and return its resolved path."""
    destination = Path(path)
    figure.savefig(destination, format="png", dpi=dpi, bbox_inches="tight")
    return destination.resolve()
