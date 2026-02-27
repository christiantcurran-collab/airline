from __future__ import annotations

import os
from typing import Any


def get_client() -> Any:
    """Build a Supabase client from environment configuration."""
    try:
        from supabase import create_client
    except Exception as exc:  # pragma: no cover - import path only exercised in supabase mode
        raise RuntimeError(
            "supabase package is required for FLIGHTLEDGER_STORAGE_BACKEND=supabase"
        ) from exc

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)

