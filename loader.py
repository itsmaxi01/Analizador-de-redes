"""Atomic UTF-8 infrastructure loading through the public domain API."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from domain import (
    CardinalityError,
    DeviceNotFoundError,
    DuplicateError,
    IncompatibleConnectionError,
    Network,
)
from validators import validate_device_id, validate_health_events, validate_ipv4


class LoaderError(Exception):
    """Base class for infrastructure-loading failures."""


class SourceFileError(LoaderError):
    """Base class for failures while reading a source file."""


class SourceFileNotFoundError(SourceFileError):
    """Raised when a required source file does not exist."""


class SourceFileReadError(SourceFileError):
    """Raised when a required source file cannot be read."""


class SourceEncodingError(SourceFileError):
    """Raised when a source file is not valid UTF-8."""


class RecordError(LoaderError):
    """Base class for errors associated with one physical source line."""

    def __init__(self, path: Path, line_number: int, message: str) -> None:
        self.path = path
        self.line_number = line_number
        self.message = message
        super().__init__(f"{path.name}, línea {line_number}: {message}")


class RecordFormatError(RecordError):
    """Raised when a record has missing or additional fields."""


class RecordValidationError(RecordError):
    """Raised when an individual ID, IP, or event sequence is invalid."""


class DuplicateRecordError(RecordError):
    """Raised for duplicate IDs, IPs, or connections."""


class ReferenceRecordError(RecordError):
    """Raised when a record references an unknown device."""


class ConnectionRecordError(RecordError):
    """Raised when a connection violates a topology invariant."""


class EmptyDevicesError(LoaderError):
    """Raised when devices.txt has no non-empty records."""


class MissingEventsError(LoaderError):
    """Raised when one or more devices lack initial health events."""


@dataclass(frozen=True, slots=True)
class _DeviceRecord:
    device_id: str
    ip: str
    line_number: int


@dataclass(frozen=True, slots=True)
class _ConnectionRecord:
    first_id: str
    second_id: str
    line_number: int


def _read_utf8(path_value: str | Path) -> tuple[Path, list[str]]:
    path = Path(path_value)
    try:
        return path, path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise SourceFileNotFoundError(f"{path}: archivo inexistente") from exc
    except UnicodeDecodeError as exc:
        raise SourceEncodingError(f"{path}: codificación UTF-8 inválida") from exc
    except OSError as exc:
        raise SourceFileReadError(f"{path}: archivo ilegible: {exc}") from exc


def _records(lines: list[str]):
    for line_number, raw_line in enumerate(lines, start=1):
        if raw_line.strip():
            yield line_number, raw_line


def _split_fields(
    path: Path, line_number: int, raw_line: str, separator: str
) -> tuple[str, str]:
    fields = raw_line.split(separator)
    if len(fields) < 2:
        raise RecordFormatError(path, line_number, "registro incompleto")
    if len(fields) > 2:
        raise RecordFormatError(
            path, line_number, "cantidad incorrecta de campos; se esperaban 2"
        )
    first, second = (field.strip() for field in fields)
    if not first or not second:
        raise RecordFormatError(path, line_number, "registro incompleto")
    return first, second


def _parse_devices(path: Path, lines: list[str]) -> list[_DeviceRecord]:
    parsed: list[_DeviceRecord] = []
    seen_ids: set[str] = set()
    seen_ips: set[str] = set()

    for line_number, raw_line in _records(lines):
        device_id, ip = _split_fields(path, line_number, raw_line, ",")
        try:
            validate_device_id(device_id)
        except ValueError as exc:
            raise RecordValidationError(
                path, line_number, f"ID inválido {device_id!r}: {exc}"
            ) from exc
        try:
            validate_ipv4(ip)
        except ValueError as exc:
            raise RecordValidationError(
                path, line_number, f"IP inválida {ip!r}: {exc}"
            ) from exc
        if device_id in seen_ids:
            raise DuplicateRecordError(
                path, line_number, f"ID duplicado {device_id!r}"
            )
        if ip in seen_ips:
            raise DuplicateRecordError(path, line_number, f"IP duplicada {ip!r}")
        seen_ids.add(device_id)
        seen_ips.add(ip)
        parsed.append(_DeviceRecord(device_id, ip, line_number))

    if not parsed:
        raise EmptyDevicesError(f"{path.name}: archivo de dispositivos vacío")
    return parsed


def _parse_connections(
    path: Path, lines: list[str], device_ids: set[str]
) -> list[_ConnectionRecord]:
    parsed: list[_ConnectionRecord] = []
    for line_number, raw_line in _records(lines):
        first_id, second_id = _split_fields(path, line_number, raw_line, ",")
        for device_id in (first_id, second_id):
            try:
                validate_device_id(device_id)
            except ValueError as exc:
                raise RecordValidationError(
                    path, line_number, f"ID inválido {device_id!r}: {exc}"
                ) from exc
            if device_id not in device_ids:
                raise ReferenceRecordError(
                    path, line_number, f"dispositivo inexistente {device_id!r}"
                )
        parsed.append(_ConnectionRecord(first_id, second_id, line_number))
    return parsed


def _parse_events(
    path: Path, lines: list[str], device_ids: set[str]
) -> dict[str, list[str]]:
    grouped: defaultdict[str, list[str]] = defaultdict(list)
    for line_number, raw_line in _records(lines):
        device_id, events = _split_fields(path, line_number, raw_line, ":")
        try:
            validate_device_id(device_id)
        except ValueError as exc:
            raise RecordValidationError(
                path, line_number, f"ID inválido {device_id!r}: {exc}"
            ) from exc
        if device_id not in device_ids:
            raise ReferenceRecordError(
                path, line_number, f"dispositivo inexistente {device_id!r}"
            )
        try:
            validate_health_events(events)
        except ValueError as exc:
            raise RecordValidationError(
                path, line_number, f"secuencia de eventos inválida {events!r}: {exc}"
            ) from exc
        grouped[device_id].append(events)

    missing = sorted(device_ids - grouped.keys())
    if missing:
        raise MissingEventsError(
            f"{path.name}: dispositivos sin eventos iniciales: {', '.join(missing)}"
        )
    return dict(grouped)


def _build_network(
    device_path: Path,
    connection_path: Path,
    devices: list[_DeviceRecord],
    connections: list[_ConnectionRecord],
    events: dict[str, list[str]],
) -> Network:
    network = Network()
    for record in devices:
        try:
            network.register_device(
                record.device_id, record.ip, "".join(events[record.device_id])
            )
        except (ValueError, DuplicateError) as exc:
            raise RecordValidationError(
                device_path, record.line_number, str(exc)
            ) from exc

    for record in connections:
        try:
            network.connect(record.first_id, record.second_id)
        except DuplicateError as exc:
            raise DuplicateRecordError(
                connection_path,
                record.line_number,
                f"conexión duplicada {record.first_id}-{record.second_id}",
            ) from exc
        except DeviceNotFoundError as exc:
            raise ReferenceRecordError(
                connection_path, record.line_number, str(exc)
            ) from exc
        except IncompatibleConnectionError as exc:
            raise ConnectionRecordError(
                connection_path,
                record.line_number,
                f"enlace incompatible {record.first_id}-{record.second_id}",
            ) from exc
        except CardinalityError as exc:
            raise ConnectionRecordError(
                connection_path,
                record.line_number,
                f"cardinalidad excedida: {exc}",
            ) from exc
        except ValueError as exc:
            raise ConnectionRecordError(
                connection_path,
                record.line_number,
                f"autoconexión no permitida {record.first_id}-{record.second_id}",
            ) from exc
    return network


def load_network(
    devices_path: str | Path,
    connections_path: str | Path,
    events_path: str | Path,
) -> Network:
    """Load and atomically return a fully valid network from three UTF-8 files."""
    device_path, device_lines = _read_utf8(devices_path)
    connection_path, connection_lines = _read_utf8(connections_path)
    event_path, event_lines = _read_utf8(events_path)

    devices = _parse_devices(device_path, device_lines)
    device_ids = {record.device_id for record in devices}
    connections = _parse_connections(connection_path, connection_lines, device_ids)
    events = _parse_events(event_path, event_lines, device_ids)
    return _build_network(
        device_path, connection_path, devices, connections, events
    )
