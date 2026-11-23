from copy import deepcopy

import matplotlib

matplotlib.use("Agg", force=True)

from matplotlib.collections import LineCollection, PathCollection
from matplotlib.colors import to_hex
from matplotlib import pyplot as plt

from core.automata import HealthState
from core.domain import Connection
from language.evaluator import DeviceView, Visualization
from main import run_cli
from visualization import (
    STATE_COLORS,
    VisualizationDependencyError,
    build_figure,
    save_figure,
)


def sample_visualization() -> Visualization:
    return Visualization(
        devices=(
            DeviceView("PC1", "PC", "10.0.0.3", HealthState.NORMAL, True),
            DeviceView("Router1", "Router", "10.0.0.1", HealthState.FAILURE, False),
            DeviceView("Server1", "Server", "10.0.0.4", HealthState.NORMAL, True),
            DeviceView("Switch1", "Switch", "10.0.0.2", HealthState.WARNING, True),
        ),
        connections=(
            Connection("PC1", "Switch1"),
            Connection("Router1", "Switch1"),
        ),
    )


def graph_collections(figure):
    axes = figure.axes[0]
    nodes = next(
        collection
        for collection in axes.collections
        if isinstance(collection, PathCollection)
    )
    edges = next(
        collection
        for collection in axes.collections
        if isinstance(collection, LineCollection)
    )
    return axes, nodes, edges


def test_figure_contains_all_nodes_edges_and_isolated_devices():
    figure = build_figure(sample_visualization())
    axes, nodes, edges = graph_collections(figure)
    assert len(nodes.get_offsets()) == 4
    assert len(edges.get_segments()) == 2
    assert {text.get_text() for text in axes.texts} == {
        "PC1", "Router1", "Server1", "Switch1"
    }
    assert axes.get_title() == "Network Graph Analyzer — Topología física y salud"
    assert {text.get_text() for text in axes.get_legend().get_texts()} == {
        "NORMAL", "WARNING", "FAILURE"
    }
    plt.close(figure)


def test_node_colors_match_all_health_states_and_failure_edges_remain_visible():
    figure = build_figure(sample_visualization())
    _, nodes, edges = graph_collections(figure)
    colors = {to_hex(color, keep_alpha=False) for color in nodes.get_facecolors()}
    assert colors == {color.lower() for color in STATE_COLORS.values()}
    assert len(edges.get_segments()) == 2
    plt.close(figure)


def test_layout_is_deterministic():
    first = build_figure(sample_visualization())
    second = build_figure(sample_visualization())
    first_positions = {text.get_text(): text.get_position() for text in first.axes[0].texts}
    second_positions = {text.get_text(): text.get_position() for text in second.axes[0].texts}
    assert first_positions == second_positions
    plt.close(first)
    plt.close(second)


def test_save_png_and_build_do_not_mutate_snapshot(tmp_path):
    data = sample_visualization()
    before = deepcopy(data)
    figure = build_figure(data)
    output = save_figure(figure, tmp_path / "network.png")
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert data == before
    plt.close(figure)


def test_cli_visualizar_passes_evaluator_snapshot_to_renderer():
    instructions = iter(("CARGAR()", "VISUALIZAR()", "SALIR"))
    output: list[str] = []
    received: list[Visualization] = []
    run_cli(lambda _: next(instructions), output.append, received.append)
    assert len(received) == 1
    assert len(received[0].devices) == 7
    assert len(received[0].connections) == 6
    assert output[-2] == "Visualización preparada: 7 dispositivos, 6 conexiones."


def test_missing_visualization_dependencies_do_not_end_cli_session():
    instructions = iter(("CARGAR()", "VISUALIZAR()", "OPERATIVO(PC1)", "SALIR"))
    output: list[str] = []

    def unavailable(_):
        raise VisualizationDependencyError("dependencias ausentes")

    run_cli(lambda _: next(instructions), output.append, unavailable)
    assert "Error de visualización: dependencias ausentes" in output
    assert "Verdadero" in output
    assert output[-1] == "Hasta luego."
