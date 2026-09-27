"""LLM provider abstraction with a content-addressed disk cache.

Resolution order for ``provider="auto"``:
  1. Anthropic API (``anthropic`` SDK) if credentials resolve (ANTHROPIC_API_KEY / ``ant auth login`` profile)
  2. ``None``
Snowflake Cortex ``AI_COMPLETE`` is used only when explicitly requested (``KEEPLINE_LLM=cortex``) because it
spends credits.
  -> with no provider, ``None`` -> callers must use their deterministic fallback (every pipeline stage has one)

Every response is cached under ``data/cache/llm/<sha256>.json`` keyed by (model, system, prompt, schema), so a
demo re-run or benchmark re-run is free and works offline. ``KEEPLINE_OFFLINE=1`` means "cache hits only".
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from keepline.config import CACHE_DIR, LLM

log = logging.getLogger(__name__)
_CACHE = CACHE_DIR / "llm"


class LLMUnavailable(RuntimeError):
    """Raised when no provider can serve a request (offline + cache miss, or no credentials)."""


class LLMClient(Protocol):
    name: str

    def complete(self, prompt: str, *, system: str = "", model: str | None = None, max_tokens: int = 4000) -> str: ...

    def complete_json(
        self, prompt: str, schema: dict[str, Any], *, system: str = "", model: str | None = None, max_tokens: int = 8000
    ) -> Any: ...


def _cache_key(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _cache_get(key: str) -> Any | None:
    p = _CACHE / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))["response"]
    return None


def _cache_put(key: str, response: Any) -> None:
    _CACHE.mkdir(parents=True, exist_ok=True)
    (_CACHE / f"{key}.json").write_text(json.dumps({"response": response}, ensure_ascii=False), encoding="utf-8")


@dataclass
class AnthropicClient:
    name: str = "claude"

    def __post_init__(self) -> None:
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(max_retries=3)

    def _call(self, prompt: str, system: str, model: str, max_tokens: int, fmt: dict[str, Any] | None) -> str:
        output_config: dict[str, Any] = {"effort": "low"}  # extraction/QA are routine; keep cost down
        if fmt is not None:
            output_config["format"] = {"type": "json_schema", "schema": fmt}
        resp = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}] if system else [],
            messages=[{"role": "user", "content": prompt}],
            output_config=output_config,
        )
        if resp.stop_reason == "refusal":
            raise LLMUnavailable("model refused")
        return "".join(b.text for b in resp.content if b.type == "text")

    def complete(self, prompt: str, *, system: str = "", model: str | None = None, max_tokens: int = 4000) -> str:
        model = model or LLM.answer_model
        key = _cache_key("text", model, system, prompt)
        if (hit := _cache_get(key)) is not None:
            return hit
        if LLM.offline_only:
            raise LLMUnavailable("offline mode and cache miss")
        out = self._call(prompt, system, model, max_tokens, None)
        _cache_put(key, out)
        return out

    def complete_json(
        self, prompt: str, schema: dict[str, Any], *, system: str = "", model: str | None = None, max_tokens: int = 8000
    ) -> Any:
        model = model or LLM.extract_model
        key = _cache_key("json", model, system, prompt, schema)
        if (hit := _cache_get(key)) is not None:
            return hit
        if LLM.offline_only:
            raise LLMUnavailable("offline mode and cache miss")
        out = json.loads(self._call(prompt, system, model, max_tokens, schema))
        _cache_put(key, out)
        return out


@dataclass
class CortexClient:
    """Snowflake Cortex AI_COMPLETE via snowflake-connector-python. Same cache semantics."""

    name: str = "cortex"

    def __post_init__(self) -> None:
        from keepline.snowflake_conn import connect  # lazy: only when Snowflake is configured

        self._conn = connect()

    def _call(self, prompt: str, system: str, model: str, fmt: dict[str, Any] | None) -> str:
        full = f"{system}\n\n{prompt}" if system else prompt
        cur = self._conn.cursor()
        if fmt is None:
            cur.execute("SELECT AI_COMPLETE(%s, %s)", (model, full))
        else:
            cur.execute(
                "SELECT AI_COMPLETE(model => %s, prompt => %s, response_format => PARSE_JSON(%s))",
                (model, full, json.dumps({"type": "json", "schema": fmt})),
            )
        return str(cur.fetchone()[0])

    def complete(self, prompt: str, *, system: str = "", model: str | None = None, max_tokens: int = 4000) -> str:
        model = model or LLM.cortex_model
        key = _cache_key("text", "cortex", model, system, prompt)
        if (hit := _cache_get(key)) is not None:
            return hit
        out = self._call(prompt, system, model, None)
        _cache_put(key, out)
        return out

    def complete_json(
        self, prompt: str, schema: dict[str, Any], *, system: str = "", model: str | None = None, max_tokens: int = 8000
    ) -> Any:
        model = model or LLM.cortex_model
        key = _cache_key("json", "cortex", model, system, prompt, schema)
        if (hit := _cache_get(key)) is not None:
            return hit
        out = json.loads(self._call(prompt, system, model, schema))
        _cache_put(key, out)
        return out


def _anthropic_available() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_PROFILE"):
        return True
    return os.path.isdir(os.path.expanduser("~/.config/anthropic"))  # `ant auth login` profile


@lru_cache(maxsize=1)
def get_llm() -> LLMClient | None:
    """Return the configured LLM client, or None when running fully deterministic/offline."""
    provider = LLM.provider
    try:
        if provider in ("anthropic", "auto") and (provider == "anthropic" or _anthropic_available()):
            return AnthropicClient()
        # Cortex spends Snowflake credits, so it is opt-in only (KEEPLINE_LLM=cortex), never picked by "auto".
        if provider == "cortex":
            return CortexClient()
    except Exception as exc:  # noqa: BLE001 -- any provider init failure degrades to deterministic mode
        log.warning("LLM provider init failed (%s); falling back to deterministic pipeline", exc)
    return None
