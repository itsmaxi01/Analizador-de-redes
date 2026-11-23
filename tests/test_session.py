from pathlib import Path

import pytest

from core.loader import RecordValidationError, SourceFileNotFoundError
from core.session import NetworkSession, NoNetworkLoadedError


def write_network(
    root: Path,
    name: str,
    devices: str,
    connections: str,
    events: str,
) -> tuple[Path, Path, Path]:
    directory = root / name
    directory.mkdir()
    paths = tuple(
        directory / filename
        for filename in ("devices.txt", "connections.txt", "events.txt")
    )
    for path, content in zip(paths, (devices, connections, events), strict=True):
        path.write_text(content, encoding="utf-8")
    return paths


def source_a(tmp_path: Path) -> tuple[Path, Path, Path]:
    return write_network(
        tmp_path,
        "a",
        "Router1,10.0.0.1\nSwitch1,10.0.0.2\n",
        "Router1,Switch1\n",
        "Router1:R\nSwitch1:R\n",
    )


def source_b(tmp_path: Path) -> tuple[Path, Path, Path]:
    return write_network(
        tmp_path,
        "b",
        "Switch2,192.168.1.2\nPC1,192.168.1.10\n",
        "Switch2,PC1\n",
        "Switch2:R\nPC1:T\n",
    )


def public_snapshot(network):
    return (
        tuple(
            (device_id, device.ip, device.health)
            for device_id, device in sorted(network.devices.items())
        ),
        network.adjacency,
        network.connections,
    )


def test_session_starts_without_network():
    session = NetworkSession()
    with pytest.raises(NoNetworkLoadedError):
        session.require_network()


def test_first_valid_load_becomes_current_network(tmp_path):
    session = NetworkSession()
    loaded = session.load(*source_a(tmp_path))
    assert session.require_network() is loaded
    assert set(loaded.devices) == {"Router1", "Switch1"}


def test_second_valid_load_replaces_instead_of_merging(tmp_path):
    session = NetworkSession()
    first = session.load(*source_a(tmp_path))
    second = session.load(*source_b(tmp_path))
    assert session.require_network() is second
    assert second is not first
    assert set(second.devices) == {"Switch2", "PC1"}
    assert "Router1" not in second.devices


def test_invalid_load_preserves_current_network_identity(tmp_path):
    session = NetworkSession()
    current = session.load(*source_a(tmp_path))
    bad = write_network(
        tmp_path,
        "bad",
        "Router2,8.8.8.8\n",
        "",
        "Router2:R\n",
    )
    with pytest.raises(RecordValidationError):
        session.load(*bad)
    assert session.require_network() is current


def test_missing_file_preserves_current_network_identity(tmp_path):
    session = NetworkSession()
    current = session.load(*source_a(tmp_path))
    with pytest.raises(SourceFileNotFoundError):
        session.load(tmp_path / "missing.txt", tmp_path / "x", tmp_path / "y")
    assert session.require_network() is current


def test_changes_after_load_apply_to_current_network(tmp_path):
    session = NetworkSession()
    current = session.load(*source_a(tmp_path))
    current.register_device("PC1", "10.0.0.3", "R")
    current.connect("Switch1", "PC1")
    assert session.require_network().neighbors("PC1") == frozenset({"Switch1"})


def test_second_load_discards_old_changes_but_does_not_mutate_old_reference(tmp_path):
    session = NetworkSession()
    old = session.load(*source_a(tmp_path))
    old.register_device("PC2", "10.0.0.3", "T")
    old.connect("Switch1", "PC2")
    old_before = public_snapshot(old)

    new = session.load(*source_b(tmp_path))
    assert session.require_network() is new
    assert "PC2" not in new.devices
    assert public_snapshot(old) == old_before


def test_sessions_are_independent(tmp_path):
    first_session = NetworkSession()
    second_session = NetworkSession()
    first = first_session.load(*source_a(tmp_path))
    second = second_session.load(*source_b(tmp_path))
    first.register_health("Switch1", "TT")
    assert first_session.require_network() is first
    assert second_session.require_network() is second
    assert set(second.devices) == {"Switch2", "PC1"}
