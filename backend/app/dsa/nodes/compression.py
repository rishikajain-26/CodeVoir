from __future__ import annotations

from app.dsa.llm_text import generate_text
from app.dsa.state import DSAState
from app.utils.logger import logger

_COMPRESS_AFTER = 7   # compress once we accumulate more than this many turns
_KEEP_RECENT = 4      # always keep this many recent turns verbatim

_SYS = """You are a concise technical note-taker for a DSA interview session.

Summarize the provided turns into 3-5 sentences covering:
- What algorithm/approach the candidate tried and whether it was correct
- Key mistakes or misunderstandings
- Behavioural signals (confidence level, hint usage)
- Current open questions from the interviewer

If an existing summary is provided, merge it with the new turns (do NOT repeat facts
already in the summary). Write in past tense. Plain text only."""


async def memory_compressor(state: DSAState) -> dict:
    """Compress old turns into a rolling summary when memory grows large.

    Keeps the last KEEP_RECENT turns verbatim; older turns are summarised and
    discarded to keep the context window lean.
    """
    turns = state.memory.turns
    if len(turns) <= _COMPRESS_AFTER:
        return {}

    to_compress = turns[:-_KEEP_RECENT]
    keep = turns[-_KEEP_RECENT:]

    excerpts = [
        f"Turn {r.turn}: {r.explanation_excerpt[:280]}"
        for r in to_compress
    ]
    ctx = {
        "existing_summary": state.memory.rolling_summary or "",
        "turns_to_compress": excerpts,
        "known_weak_areas": state.memory.known_weak_areas,
    }
    summary = await generate_text(_SYS, str(ctx), temperature=0.2, max_tokens=250)
    if not summary:
        return {}

    logger.info(
        "MemoryCompressor: compressed %d turns into rolling summary (%d chars)",
        len(to_compress), len(summary),
    )
    new_memory = state.memory.model_copy(
        update={
            "turns": keep,
            "rolling_summary": summary.strip(),
        }
    )
    return {"memory": new_memory}
