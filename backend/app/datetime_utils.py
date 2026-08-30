"""Timestamps stored in the DB are naive but always represent UTC (see
models.py / modules/ollama.py, which populate them via func.now() or
datetime.now(timezone.utc)). Serializing them as naive ISO strings makes
browsers interpret them as local time instead of UTC, so every API-facing
datetime field must be tagged with the UTC offset on the way out.
"""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def _as_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


UtcDatetime = Annotated[datetime, PlainSerializer(_as_utc_iso, return_type=str)]
