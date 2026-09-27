"""Snowflake connection helper. Reads standard SNOWFLAKE_* env vars; only imported when Snowflake is configured."""

from __future__ import annotations

import os
from typing import Any


def connect() -> Any:
    import snowflake.connector

    params = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "role": os.environ.get("SNOWFLAKE_ROLE", "KEEPLINE_APP"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "KEEPLINE_WH"),
        "database": os.environ.get("SNOWFLAKE_DATABASE", "KEEPLINE"),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", "CORE"),
    }
    if pw := os.environ.get("SNOWFLAKE_PASSWORD"):
        params["password"] = pw
    elif key := os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        params["private_key_file"] = key
    else:
        params["authenticator"] = os.environ.get("SNOWFLAKE_AUTHENTICATOR", "externalbrowser")
    return snowflake.connector.connect(**params)
