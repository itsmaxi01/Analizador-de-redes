"""Core entities for the Network Graph Analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from automata import HealthState, process_health
from validators import (
    are_types_compatible,
    infer_device_type,
    validate_device_id,
    validate_health_events,
    validate_ipv4,
)


class DomainError(Exception):
    """Base class for errors involving network-wide domain rules."""


class DeviceNotFoundError(DomainError):
    """Raised when an operation references an unknown device."""


class DuplicateError(DomainError):
    """Raised when an ID, IP, or physical connection already exists."""


class IncompatibleConnectionError(DomainError):
    """Raised when two device types cannot be connected."""


class CardinalityError(DomainError):
    """Raised when a PC or Server would exceed one connection."""


class ConnectionNotFoundError(DomainError):
    """Raised when attempting to remove a connection that does not exist."""


class Device:
    """A device whose identity, address, and health are protected properties."""

    __slots__ = ("__id", "__type", "__ip", "__health")

    def __init__(self, device_id: str, ip: str, initial_events: str) -> None:
        self.__id = validate_device_id(device_id)
        self.__type = infer_device_type(device_id)
        self.__ip = validate_ipv4(ip)
        events = validate_health_events(initial_events)
        self.__health = process_health(HealthState.NORMAL, events)

    @property
    def id(self) -> str:
        return self.__id

    @property
    def type(self) -> str:
        return self.__type

    @property
    def ip(self) -> str:
        return self.__ip

    @property
    def health(self) -> HealthState:
        return self.__health

    @property
    def operational(self) -> bool:
        return self.__health.operational

    def _update_ip(self, new_ip: str) -> None:
        """Update an already network-authorized address."""
        self.__ip = validate_ipv4(new_ip)

    def _record_health_events(self, events: str) -> HealthState:
        """Process an already network-authorized health sequence."""
        validated_events = validate_health_events(events)
        new_state = process_health(self.__health, validated_events)
        self.__health = new_state
        return new_state


@dataclass(frozen=True, slots=True, init=False)
class Connection:
    """A canonical, undirected physical link between two device IDs."""

    first: str
    second: str

    def __init__(self, first: str, second: str) -> None:
        valid_first = validate_device_id(first)
        valid_second = validate_device_id(second)
        if valid_first == valid_second:
            raise ValueError("A device cannot be connected to itself.")
        canonical_first, canonical_second = sorted((valid_first, valid_second))
        object.__setattr__(self, "first", canonical_first)
        object.__setattr__(self, "second", canonical_second)

    @property
    def endpoints(self) -> frozenset[str]:
        return frozenset((self.first, self.second))


class Network:
    """Current infrastructure and the sole public coordinator of mutations."""

    def __init__(self) -> None:
        self.__devices: dict[str, Device] = {}
        self.__adjacency: dict[str, set[str]] = {}

    @property
    def devices(self) -> Mapping[str, Device]:
        return MappingProxyType(dict(self.__devices))

    @property
    def adjacency(self) -> Mapping[str, frozenset[str]]:
        snapshot = {
            device_id: frozenset(neighbors)
            for device_id, neighbors in self.__adjacency.items()
        }
        return MappingProxyType(snapshot)

    @property
    def connections(self) -> frozenset[Connection]:
        return frozenset(
            Connection(device_id, neighbor)
            for device_id, neighbors in self.__adjacency.items()
            for neighbor in neighbors
            if device_id < neighbor
        )

    def get_device(self, device_id: str) -> Device:
        validate_device_id(device_id)
        try:
            return self.__devices[device_id]
        except KeyError as exc:
            raise DeviceNotFoundError(f"Device {device_id!r} does not exist.") from exc

    def neighbors(self, device_id: str) -> frozenset[str]:
        self.get_device(device_id)
        return frozenset(self.__adjacency[device_id])

    def register_device(
        self, device_id: str, ip: str, initial_events: str
    ) -> Device:
        candidate = Device(device_id, ip, initial_events)
        if candidate.id in self.__devices:
            raise DuplicateError(f"Device ID {candidate.id!r} is already registered.")
        if any(device.ip == candidate.ip for device in self.__devices.values()):
            raise DuplicateError(f"IPv4 address {candidate.ip!r} is already assigned.")

        self.__devices[candidate.id] = candidate
        self.__adjacency[candidate.id] = set()
        return candidate

    def change_ip(self, device_id: str, new_ip: str) -> None:
        device = self.get_device(device_id)
        validated_ip = validate_ipv4(new_ip)
        if validated_ip == device.ip:
            raise DuplicateError("The new IPv4 address is the device's current address.")
        if any(other.ip == validated_ip for other in self.__devices.values()):
            raise DuplicateError(f"IPv4 address {validated_ip!r} is already assigned.")
        device._update_ip(validated_ip)

    def connect(self, first_id: str, second_id: str) -> Connection:
        connection = Connection(first_id, second_id)
        first = self.get_device(connection.first)
        second = self.get_device(connection.second)

        if second.id in self.__adjacency[first.id]:
            raise DuplicateError("The physical connection already exists.")
        if not are_types_compatible(first.type, second.type):
            raise IncompatibleConnectionError(
                f"Connections between {first.type} and {second.type} are not allowed."
            )
        for device in (first, second):
            if device.type in {"PC", "Server"} and self.__adjacency[device.id]:
                raise CardinalityError(
                    f"{device.type} device {device.id!r} already has its maximum connection."
                )

        self.__adjacency[first.id].add(second.id)
        self.__adjacency[second.id].add(first.id)
        return connection

    def disconnect(self, first_id: str, second_id: str) -> Connection:
        connection = Connection(first_id, second_id)
        first = self.get_device(connection.first)
        second = self.get_device(connection.second)
        if second.id not in self.__adjacency[first.id]:
            raise ConnectionNotFoundError("The physical connection does not exist.")

        self.__adjacency[first.id].remove(second.id)
        self.__adjacency[second.id].remove(first.id)
        return connection

    def register_health(self, device_id: str, events: str) -> HealthState:
        device = self.get_device(device_id)
        validated_events = validate_health_events(events)
        return device._record_health_events(validated_events)
