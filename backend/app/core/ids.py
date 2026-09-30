"""Time-ordered UUID generation (RFC 9562 UUIDv7).

Architecture v2 decision D4: newly created rows get UUIDv7 instead of UUIDv4.
Random UUIDv4 values scatter across B-tree indexes; at 100M+ rows that
fragments indexes and lowers write locality. UUIDv7 embeds a 48-bit
millisecond timestamp in the high bits, so new rows land near the end of the
index while staying globally unique and generatable without a central
counter.

Existing UUIDv4 rows are NOT renumbered. Both versions are valid UUIDs and
coexist in the same column, so this is purely a change of default.
See docs/architecture-v2.md §4.

The standard library only gained ``uuid.uuid7()`` in Python 3.14 and the
running image is Python 3.12, so this module provides the generator instead
of adding a dependency.
"""

from __future__ import annotations

import secrets
import time
import uuid

__all__ = ["uuid7"]


def uuid7() -> uuid.UUID:
    """Return a new RFC 9562 UUIDv7.

    Layout (128 bits)::

        bits 127..80  48-bit Unix timestamp in milliseconds
        bits  79..76  version (0b0111)
        bits  75..64  rand_a (12 random bits)
        bits  63..62  variant (0b10)
        bits  61..0   rand_b (62 random bits)

    Ordering is millisecond-granular: values created in the same millisecond
    are not ordered relative to each other. That is sufficient for the index
    locality this exists for, and it keeps the generator stateless and
    thread-safe.
    """

    unix_ts_ms = time.time_ns() // 1_000_000
    rand = secrets.randbits(74)

    value = (unix_ts_ms & 0xFFFF_FFFF_FFFF) << 80
    value |= 0x7 << 76
    value |= (rand >> 62) << 64
    value |= 0x2 << 62
    value |= rand & ((1 << 62) - 1)

    return uuid.UUID(int=value)
