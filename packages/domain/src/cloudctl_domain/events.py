"""Identifiers, canonical hashes, and domain events."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def new_uuid7(*, timestamp_ms: int | None = None) -> uuid.UUID:
    """Create a UUIDv7 without relying on Python 3.14's uuid.uuid7."""
    unix_ms = timestamp_ms if timestamp_ms is not None else time.time_ns() // 1_000_000
    if not 0 <= unix_ms < 1 << 48:
        raise ValueError("timestamp is outside UUIDv7 range")
    random_bits = secrets.randbits(74)
    value = unix_ms << 80
    value |= 0x7 << 76
    value |= (random_bits >> 62) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return uuid.UUID(int=value)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class DomainEvent:
    tenant_id: uuid.UUID
    aggregate_type: str
    aggregate_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    id: uuid.UUID = field(default_factory=new_uuid7)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
