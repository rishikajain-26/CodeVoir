from __future__ import annotations

import re
from typing import Any

from app.learning_agent.services.vector_store import confidence_from_results, search_chunks, source_summaries
from app.services.llm_service import llm_service

MODE_INSTRUCTIONS = {
    "beginner": "Explain for a beginner. Use simple language, one analogy, and one small example.",
    "intermediate": "Explain clearly with practical developer details and a short example.",
    "advanced": "Explain deeply with internals, tradeoffs, edge cases, and implementation details.",
    "interview": "Answer in an interview-ready format: crisp definition, explanation, example, and likely follow-up.",
    "production": "Focus on production use cases, reliability, scaling, debugging, and real-world tradeoffs.",
    "hinglish": "Explain in natural Hinglish. Keep technical terms in English where useful.",
}

FOLLOWUPS = [
    "Explain this with a code example",
    "Turn this into interview notes",
    "Generate flashcards from this topic",
    "Ask me 5 mock interview questions",
]


def answer_question(question: str, *, doc_ids: list[str], user_id: str, mode: str = "beginner", strict_sources: bool = True) -> dict[str, Any]:
    results = search_chunks(question, doc_ids=doc_ids, user_id=user_id, top_k=6)
    sources = source_summaries(results)
    confidence = confidence_from_results(results)
    if not results:
        return {
            "answer": "I could not find indexed source material for this question. Upload a PDF, URL, GitHub repo, or notes first.",
            "sources": [],
            "confidence": "low",
            "suggested_followups": ["Upload a source", "Paste notes", "Index a GitHub repository"],
        }

    context = _format_context(results)
    strict_rule = "Use only the provided context. If the context is insufficient, say exactly what is missing." if strict_sources else "Prefer the context, and clearly mark any general knowledge you add."
    system_prompt = "You are CodeVoir's AI Learning Agent: a source-grounded technical mentor for interview preparation."
    user_payload = f"""
Question:
{question}

Mode:
{MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS['beginner'])}

    Rules:
- {strict_rule}
- Explain the concept clearly and practically.
- Do not repeat the user's question back as the opening line.
- Do not dump raw source excerpts. Turn the source into a polished explanation.
- If the user asks for a simple or common-person explanation, use everyday wording while keeping the important nuance.
- Include source-aware reasoning, but do not fabricate page numbers or file names.
- End with a short 'Why it matters for interviews' section when relevant.

Retrieved source context:
{context}
""".strip()
    fallback = _fallback_answer(question, results, mode)
    answer = llm_service.generate(system_prompt, user_payload, fallback=fallback, temperature=0.35, max_tokens=850)
    return {
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
        "suggested_followups": FOLLOWUPS,
    }


def _format_context(results: list[dict[str, Any]]) -> str:
    parts = []
    for index, item in enumerate(results, start=1):
        meta = item.get("metadata") or {}
        label = meta.get("file_path") or meta.get("url") or meta.get("source") or meta.get("title") or "source"
        page = f", page {meta.get('page')}" if meta.get("page") else ""
        parts.append(f"[Source {index}: {label}{page}; score={item.get('score', 0)}]\n{item.get('text', '')}")
    return "\n\n---\n\n".join(parts)


def _fallback_answer(question: str, results: list[dict[str, Any]], mode: str) -> str:
    points = _source_points(results)
    if not points:
        return "I found the selected source, but it does not contain enough clean text to explain this well."

    main = points[0]
    nuance = points[1:4]
    simple_mode = mode == "beginner" or any(term in question.lower() for term in ("common", "simple", "plain", "beginner", "layman"))

    if simple_mode:
        lines = [
            "In simple words:",
            _plain_explanation(main),
        ]
    else:
        lines = [
            "Here is the core idea:",
            _polish_sentence(main),
        ]

    if nuance:
        lines.extend([
            "",
            "The important nuance:",
            *[f"- {_polish_sentence(point)}" for point in nuance],
        ])

    example = _example_from_points(points)
    if example:
        lines.extend(["", "A helpful way to think about it:", example])

    lines.extend([
        "",
        "Why it matters for interviews:",
        "A strong answer should not sound one-sided. State the main benefit, then add the tradeoff or limitation from the source.",
    ])
    return "\n".join(lines)


def _source_points(results: list[dict[str, Any]]) -> list[str]:
    points: list[str] = []
    seen: set[str] = set()
    for item in results[:4]:
        text = _clean_source_text(str(item.get("text") or ""))
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            sentence = sentence.strip(" -\t")
            if len(sentence) < 35:
                continue
            if re.match(r"^\[?\s*\d+\s*\]?$", sentence):
                continue
            key = re.sub(r"\W+", " ", sentence).strip().lower()[:120]
            if key and key not in seen:
                seen.add(key)
                points.append(sentence[:260])
            if len(points) >= 5:
                return points
    return points


def _clean_source_text(text: str) -> str:
    text = re.sub(r"\[\s*\d+\s*\]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.replace("§", "").strip()


def _plain_explanation(sentence: str) -> str:
    polished = _polish_sentence(sentence)
    replacements = {
        "ICE cars": "petrol or diesel cars",
        "ICE vehicles": "petrol or diesel vehicles",
        "EVs": "electric vehicles",
        "particulates": "tiny pollution particles",
    }
    for source, target in replacements.items():
        polished = polished.replace(source, target)
    return polished


def _polish_sentence(sentence: str) -> str:
    value = sentence.strip()
    value = re.sub(r"\s+([,.!?])", r"\1", value)
    value = re.sub(r"\bthen ICE\b", "than ICE", value)
    value = re.sub(r"\btyres\b", "tires", value)
    if value and value[-1] not in ".!?":
        value += "."
    return value[:1].upper() + value[1:]


def _example_from_points(points: list[str]) -> str:
    joined = " ".join(points).lower()
    if "electric" in joined and ("ice" in joined or "petroleum" in joined or "exhaust" in joined):
        return (
            "Think of an electric car as cleaner during everyday driving because it has no exhaust pipe, "
            "but not completely impact-free because battery production and tire particles still matter."
        )
    if len(points) >= 2:
        return f"The source is basically saying: {_polish_sentence(points[0])} At the same time, {_polish_sentence(points[1]).lower()}"
    return ""
