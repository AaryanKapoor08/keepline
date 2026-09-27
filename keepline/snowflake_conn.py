"""Snowflake connection helper.

Reads standard ``SNOWFLAKE_*`` env vars (``keepline.config`` loads a gitignored ``.env`` first). Prefers key-pair
auth (no MFA prompts for scripts); falls back to password, then browser SSO. Only imported when Snowflake is used.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import keepline.config  # noqa: F401 -- side effect: loads .env


def connect(*, database: str | None = None, schema: str | None = None) -> Any:
    import snowflake.connector

    params: dict[str, Any] = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "role": os.environ.get("SNOWFLAKE_ROLE", "KEEPLINE_ADMIN"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "KEEPLINE_WH"),
    }
    # Database/schema are optional so the very first deploy (which creates them) can connect.
    if db := database or os.environ.get("SNOWFLAKE_DATABASE"):
        params["database"] = db
    if sc := schema or os.environ.get("SNOWFLAKE_SCHEMA"):
        params["schema"] = sc

    if key := os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        params["private_key_file"] = str(Path(key).expanduser())
    elif pw := os.environ.get("SNOWFLAKE_PASSWORD"):
        params["password"] = pw
    else:
        params["authenticator"] = os.environ.get("SNOWFLAKE_AUTHENTICATOR", "externalbrowser")
    return snowflake.connector.connect(**params)
