"""Lifecycle management for the currently loaded network."""

from __future__ import annotations

from pathlib import Path

from domain import Network
from loader import load_network


class NoNetworkLoadedError(RuntimeError):
    """Raised when an operation requires a network before the first load."""


class NetworkSession:
    """Hold and atomically replace the network active during one execution."""

    __slots__ = ("__network",)

    def __init__(self) -> None:
        self.__network: Network | None = None

    def load(
        self,
        devices_path: str | Path,
        connections_path: str | Path,
        events_path: str | Path,
    ) -> Network:
        candidate = load_network(devices_path, connections_path, events_path)
        self.__network = candidate
        return candidate

    def require_network(self) -> Network:
        if self.__network is None:
            raise NoNetworkLoadedError("No network has been loaded in this session.")
        return self.__network
