"""Phone normalization for matching inbound senders against User.phone.

Reduces any representation (Evolution JID, +55 formatting, bare DDD+number) to a
canonical digits-only Brazilian number: ``55`` + DDD + number. Known limitation:
the Brazilian mobile 9th digit can make two representations of the same line
differ; handled on the common case only.
"""

from __future__ import annotations

import re

_DIGITS = re.compile(r"\D")


def normalize_phone(raw: str | None) -> str:
    if not raw:
        return ""
    local = raw.split("@", 1)[0]
    digits = _DIGITS.sub("", local)
    if not digits:
        return ""
    # Bare DDD + number (10 or 11 digits) -> assume Brazil country code.
    if len(digits) in (10, 11):
        digits = "55" + digits
    return digits
