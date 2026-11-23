"""Pure validators for the Network Graph Analyzer domain."""

from __future__ import annotations

import ipaddress
import re


DEVICE_ID_PATTERN = re.compile(r"(?:Router|Switch|PC|Server)[1-9][0-9]*")
IPV4_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]{0,2})(?:\.(?:0|[1-9][0-9]{0,2})){3}"
)
HEALTH_EVENTS_PATTERN = re.compile(r"[RT]+")

ALLOWED_DEVICE_TYPES = frozenset({"Router", "Switch", "PC", "Server"})
ALLOWED_CONNECTIONS = frozenset(
    {
        frozenset({"Router"}),
        frozenset({"Router", "Switch"}),
        frozenset({"Switch"}),
        frozenset({"Switch", "PC"}),
        frozenset({"Switch", "Server"}),
    }
)
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


def validate_device_id(device_id: str) -> str:
    """Return a valid device identifier or raise ``ValueError``."""
    if not isinstance(device_id, str) or DEVICE_ID_PATTERN.fullmatch(device_id) is None:
        raise ValueError(
            "Invalid device ID. Expected Router, Switch, PC, or Server followed "
            "by a positive integer without leading zeros."
        )
    return device_id


def infer_device_type(device_id: str) -> str:
    """Infer the device type from a validated identifier."""
    validated_id = validate_device_id(device_id)
    match = re.fullmatch(r"(Router|Switch|PC|Server)[1-9][0-9]*", validated_id)
    assert match is not None
    return match.group(1)


def validate_ipv4(ip: str) -> str:
    """Return a permitted private IPv4 address or raise ``ValueError``."""
    if not isinstance(ip, str) or IPV4_PATTERN.fullmatch(ip) is None:
        raise ValueError("Invalid IPv4 address format or leading zero in an octet.")

    try:
        address = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError as exc:
        raise ValueError("IPv4 octets must be between 0 and 255.") from exc

    if not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError("IPv4 address must belong to an allowed private range.")
    if not 1 <= int(ip.rsplit(".", 1)[1]) <= 254:
        raise ValueError("The final IPv4 octet must be between 1 and 254.")
    return ip


def validate_health_events(events: str) -> str:
    """Return a non-empty R/T sequence or raise ``ValueError``."""
    if not isinstance(events, str) or HEALTH_EVENTS_PATTERN.fullmatch(events) is None:
        raise ValueError("Health events must be a non-empty sequence containing only R and T.")
    return events


def are_types_compatible(first_type: str, second_type: str) -> bool:
    """Return whether two device types may have a physical connection."""
    if first_type not in ALLOWED_DEVICE_TYPES or second_type not in ALLOWED_DEVICE_TYPES:
        raise ValueError("Unknown device type.")
    return frozenset({first_type, second_type}) in ALLOWED_CONNECTIONS
