"""Read-only graph analysis for physical and operational network views."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from domain import Network


class GraphMode(str, Enum):
    """Supported views of the network topology."""

    FISICA = "FISICA"
    OPERATIVA = "OPERATIVA"


@dataclass(frozen=True, slots=True)
class Route:
    """An immutable path whose hop count is derived from its nodes."""

    path: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.path, tuple) or not self.path:
            raise ValueError("A route must contain a non-empty tuple of device IDs.")
        if any(not isinstance(device_id, str) for device_id in self.path):
            raise ValueError("Every route node must be a device ID string.")

    @property
    def hops(self) -> int:
        return len(self.path) - 1


def _require_mode(mode: GraphMode) -> GraphMode:
    if not isinstance(mode, GraphMode):
        raise ValueError("Unknown graph mode. Use GraphMode.FISICA or GraphMode.OPERATIVA.")
    return mode


def _is_in_view(network: Network, device_id: str, mode: GraphMode) -> bool:
    return mode is GraphMode.FISICA or network.get_device(device_id).operational


def _reconstruct_route(
    parents: dict[str, str | None], destination: str
) -> Route:
    reversed_path: list[str] = []
    current: str | None = destination
    while current is not None:
        reversed_path.append(current)
        current = parents[current]
    return Route(tuple(reversed(reversed_path)))


def _shortest_path_where(
    network: Network,
    origin: str,
    destination: str,
    can_visit: Callable[[str], bool],
) -> Route | None:
    """Run the shared deterministic BFS under a node-admission predicate."""
    if origin == destination:
        return Route((origin,))

    parents: dict[str, str | None] = {origin: None}
    pending: deque[str] = deque([origin])

    while pending:
        current = pending.popleft()
        for neighbor in sorted(network.neighbors(current)):
            if neighbor in parents or not can_visit(neighbor):
                continue
            parents[neighbor] = current
            if neighbor == destination:
                return _reconstruct_route(parents, destination)
            pending.append(neighbor)
    return None


def shortest_path(
    network: Network,
    origin: str,
    destination: str,
    mode: GraphMode,
) -> Route | None:
    """Return a deterministic minimum-hop route, or ``None`` when absent."""
    selected_mode = _require_mode(mode)
    origin_device = network.get_device(origin)
    destination_device = network.get_device(destination)

    if selected_mode is GraphMode.OPERATIVA and (
        not origin_device.operational or not destination_device.operational
    ):
        return None
    return _shortest_path_where(
        network,
        origin,
        destination,
        lambda device_id: _is_in_view(network, device_id, selected_mode),
    )


def shortest_path_with_operational_intermediates(
    network: Network,
    origin: str,
    destination: str,
) -> Route | None:
    """Find a path whose internal nodes are operational, ignoring endpoint health."""
    network.get_device(origin)
    network.get_device(destination)
    return _shortest_path_where(
        network,
        origin,
        destination,
        lambda device_id: (
            device_id == destination or network.get_device(device_id).operational
        ),
    )


def is_connected(
    network: Network,
    origin: str,
    destination: str,
    mode: GraphMode,
) -> bool:
    """Return whether a route exists in the selected graph view."""
    return shortest_path(network, origin, destination, mode) is not None


def degree(network: Network, device_id: str, mode: GraphMode) -> int | None:
    """Return physical/operational degree, or ``None`` outside the operational graph."""
    selected_mode = _require_mode(mode)
    device = network.get_device(device_id)
    neighbors = network.neighbors(device_id)

    if selected_mode is GraphMode.FISICA:
        return len(neighbors)
    if not device.operational:
        return None
    return sum(network.get_device(neighbor).operational for neighbor in neighbors)


def isolated_nodes(network: Network, mode: GraphMode) -> tuple[str, ...]:
    """Return isolated device IDs in deterministic order."""
    selected_mode = _require_mode(mode)
    return tuple(
        device_id
        for device_id in sorted(network.devices)
        if _is_in_view(network, device_id, selected_mode)
        and degree(network, device_id, selected_mode) == 0
    )


def connected_components(
    network: Network, mode: GraphMode
) -> tuple[tuple[str, ...], ...]:
    """Return all connected components without modifying or caching the network."""
    selected_mode = _require_mode(mode)
    available = {
        device_id
        for device_id in network.devices
        if _is_in_view(network, device_id, selected_mode)
    }
    visited: set[str] = set()
    components: list[tuple[str, ...]] = []

    for start in sorted(available):
        if start in visited:
            continue
        visited.add(start)
        pending: deque[str] = deque([start])
        component: list[str] = []

        while pending:
            current = pending.popleft()
            component.append(current)
            for neighbor in sorted(network.neighbors(current)):
                if neighbor in available and neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)

        components.append(tuple(sorted(component)))

    return tuple(components)
