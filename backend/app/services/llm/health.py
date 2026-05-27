"""Central LLM health signal shared across all interview rounds.

Every reply-generating LLM entry point (DSA `generate_text`, CS/PB
`llm_service.generate`) reports success/failure here. The API surfaces it so the
frontend can show the candidate an "AI currently offline" indicator whenever the
model can't be reached and replies fall back to canned heuristics.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_state: dict[str, object] = {
    "ok": True,                 # did the most recent reply call succeed?
    "ts": 0.0,                  # epoch of the last status change
    "reason": "",               # short reason for the last failure
    "consecutive_failures": 0,  # how many failures in a row
}


def classify_failure(exc: BaseException | str | None = None, default: str = "llm_error") -> str:
    """Return a stable, UI-safe health reason from provider exceptions."""
    if exc is None:
        return default
    text = str(exc or "").lower()
    name = exc.__class__.__name__.lower() if isinstance(exc, BaseException) else ""
    if "ratelimit" in name or "rate limit" in text or "rate_limit" in text or "quota" in text:
        return "rate_limited"
    if "authentication" in name or "permission" in name or "api key" in text or "unauthorized" in text:
        return "auth_error"
    if "timeout" in name or "timed out" in text or "timeout" in text:
        return "timeout"
    if "connection" in name or "network" in text or "connection" in text:
        return "network_error"
    if isinstance(exc, str) and exc:
        return exc[:80]
    return default


def record_ok() -> None:
    with _lock:
        _state["ok"] = True
        _state["ts"] = time.time()
        _state["reason"] = ""
        _state["consecutive_failures"] = 0


def record_fail(reason: str = "") -> None:
    # "no_api_key" means the LLM is not configured — not a transient failure.
    # Don't flip to offline; let the configured check surface it separately.
    if reason in ("no_api_key", "no_provider_configured"):
        with _lock:
            _state["reason"] = reason
            _state["ts"] = time.time()
        return
    with _lock:
        _state["ok"] = False
        _state["ts"] = time.time()
        _state["reason"] = (reason or "")[:200]
        _state["consecutive_failures"] = int(_state.get("consecutive_failures", 0)) + 1


def record_exception(exc: BaseException | str, default: str = "llm_error") -> None:
    record_fail(classify_failure(exc, default))


def is_offline() -> bool:
    """True when the most recent reply-generating LLM call failed."""
    with _lock:
        return not bool(_state["ok"])


def get_health() -> dict[str, object]:
    with _lock:
        return dict(_state)
