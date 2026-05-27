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


def is_offline() -> bool:
    """True when the most recent reply-generating LLM call failed."""
    with _lock:
        return not bool(_state["ok"])


def get_health() -> dict[str, object]:
    with _lock:
        return dict(_state)
