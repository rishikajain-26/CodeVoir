from __future__ import annotations

import re
from typing import Any

from app.learning_agent.services.source_store import get_chunks_for_docs, save_generated_output
from app.learning_agent.services.vector_store import search_chunks, source_summaries
from app.services.llm_service import llm_service

GENERATION_PROMPTS = {
    "summary": "Create a high-quality source-grounded study summary for interview preparation. Use this exact markdown structure: ## Core Idea, ## Key Takeaways, ## How It Works, ## Source Example, ## Interview Answer, ## Common Mistakes, ## Quick Revision. Requirements: explain the actual concept from the selected source, not generic background; include 5-7 specific takeaways that preserve source terminology; make the example concrete and tied to the source; include why the concept matters, when to use it, and one limitation or tradeoff; write in clear student-friendly language with enough depth for an interview answer.",
    "notes": "Create polished source-grounded summary notes for interview preparation. Use this exact markdown structure: ## Core Idea, ## Key Takeaways, ## How It Works, ## Source Example, ## Interview Answer, ## Common Mistakes, ## Quick Revision. Requirements: extract the most important ideas from the selected source; avoid vague filler; include 5-7 practical takeaways, one concrete example, one tradeoff or mistake, and a concise interview-ready answer. Keep it accurate, structured, and revision-friendly.",
    "cheatsheet": "Create a compact visual cheatsheet. Prefer markdown tables with columns: Concept, Meaning, Example, Interview Tip. Keep rows concise.",
    "flashcards": "Create 5-8 polished active recall flashcards from the strongest key highlights in the source context or supplied summary. Use this exact repeated format only: Q: question text on one line, A: answer text on the next line. Every question must test a concrete highlight, definition, tradeoff, example, edge case, or interview-worthy insight that appears in the source. Every answer must be source-grounded, concise, complete, and useful for revision. Avoid generic questions like 'What is key point 1?' or answers that merely restate the question.",
    "interview_questions": "Generate beginner, intermediate, advanced, and project-based interview questions. Use headings and for each question include: Ideal Answer, Follow-up, and What the interviewer tests.",
    "revision_plan": "Create a practical 3-day visual revision plan with Day 1, Day 2, Day 3 headings, tasks, flashcard practice, mock interview tasks, and success checkpoints.",
    "project_pitch": "If repository/project content exists, create a 60-second project pitch, 2-minute technical explanation, architecture walkthrough, challenges, and likely interviewer questions. Use clean headings and bullets.",
    "flowchart": "Create a clean single-column vertical flowchart. Output only a section titled ## Flowchart with ordered or indented bullets. Do not include Mermaid, code fences, diagrams-as-code, or multiple columns. Keep each node short, source-grounded, and ordered from foundation to advanced details.",
    "mindmap": "Create a clean single-column vertical flowchart. Output only a section titled ## Flowchart with ordered or indented bullets. Do not include Mermaid, code fences, diagrams-as-code, or multiple columns. Keep each node short, source-grounded, and ordered from foundation to advanced details.",
    "weak_answer_rewrite": "Rewrite the weak answer into a strong interview answer. Include: score out of 100, what is weak, improved answer, why it is stronger, and a 3-line practice tip.",
    "source_mock_interview": "Create a source-grounded mock interview from the selected material. Generate exactly 6 questions unless asked otherwise. For each question include: Question, Expected Points, Follow-up, and What It Tests. Use clear markdown headings.",
    "skill_gap_heatmap": "Create a visual skill-gap heatmap for a student. Use exactly this markdown structure: ## Skill Gap Heatmap, then lines like React: 78/100 - reason, DSA: 62/100 - reason, Communication: 70/100 - reason, System Design: 55/100 - reason, Projects: 82/100 - reason. Then add ## Priority Fixes and ## Next 48 Hours.",
    "first_impression_simulator": "Simulate what a judge, interviewer, or evaluator understands in the first 10 seconds from the selected sources/project. Include: first impression, wow factor, red flags, strongest proof, missing proof, improved project positioning, and a crisp evaluator-friendly summary.",
    "opportunity_kit": "Create a complete opportunity application kit. Include: application pitch, project positioning, resume keywords, likely screening questions, 3-day prep plan, and a short submission checklist. Keep it ethical and user-controlled.",
    "judge_demo_kit": "Create a hackathon judge demo kit for this product/project. Include: 20-second opening, problem statement, live demo script, wow moments, architecture explanation, monetization angle, impact metrics, and closing line.",
    "architecture_map": "Create a project architecture map from the selected source/repository. Use this exact markdown structure: ## Architecture Map, ## Layers, then lines like Frontend: role -> connects to API Layer, Backend API: role -> connects to Services, AI/RAG Service: role -> connects to Vector Store, Database: role -> connects to Persistence. Add ## Critical Flows with 3 numbered flows and ## Scalability Notes.",
    "interview_replay_timeline": "Create a live interview replay timeline from the available interview/source context. Use this exact markdown structure: ## Interview Replay Timeline, then timestamp lines like 00:00 - Strong - Opening clarity, 01:20 - Weak - Missing production tradeoff, 02:40 - Improved - Better example. Add ## Turning Points and ## Next Practice Loop.",
    "evidence_coverage_meter": "Create a colorful evidence coverage report for the selected source answer. Use exactly these score lines: Evidence Coverage: 84/100 - reason, Source Relevance: 91/100 - reason, Completeness: 72/100 - reason, Freshness: 76/100 - reason, Confidence: 88/100 - reason. Then add ## Missing Context and ## Trust Notes.",
    "knowledge_graph": "Create a knowledge graph from the source material. Use this exact markdown structure: ## Knowledge Graph, then relationship lines like React -> Reconciliation: compares UI trees, Keys -> Reconciliation: stabilizes list identity, useMemo -> Performance: avoids recalculation. Add ## Most Important Links and ## Interview Angles.",
    "answer_studio": "Create an answer studio output for improving an interview response. Include: ## Before, ## After, ## Score Improvement with lines Clarity: 72/100 - reason, Technical Depth: 80/100 - reason, Production Reasoning: 68/100 - reason, Confidence: 84/100 - reason, and ## Practice Loop. If no answer is provided, create a template using source context.",
}


def generate_material(
    *,
    generation_type: str,
    doc_ids: list[str],
    user_id: str,
    weak_topics: list[str] | None = None,
    extra_context: str = "",
) -> dict[str, Any]:
    weak_topics = weak_topics or []
    query = " ".join(weak_topics) or extra_context or generation_type.replace("_", " ")
    results = search_chunks(query, doc_ids=doc_ids, user_id=user_id, top_k=10)
    if generation_type in {"summary", "notes", "project_pitch", "architecture_map", "judge_demo_kit", "flowchart", "mindmap"}:
        results = _overview_first_chunks(doc_ids, user_id) or results
    elif generation_type == "flashcards":
        results = get_chunks_for_docs(doc_ids, user_id) or results
    sources = source_summaries(results)
    context = _context_from_results(results)
    if not context and not extra_context and not weak_topics:
        output = "Upload or select a source first, then I can generate this material from your documents."
        return {"output": output, "sources": []}
    if generation_type == "flashcards":
        output = _source_locked_flashcards(results, weak_topics, extra_context)
        save_generated_output(user_id, generation_type, output, doc_ids, sources)
        return {"output": output, "sources": sources}

    instruction = GENERATION_PROMPTS.get(generation_type, GENERATION_PROMPTS["notes"])
    system_prompt = "You are CodeVoir's AI Learning Agent. Generate practical, source-grounded interview preparation material."
    user_payload = f"""
Task:
{instruction}

Weak topics, if any:
{', '.join(weak_topics) if weak_topics else 'None provided'}

Extra context:
{extra_context or 'None'}

Source context:
{context or 'No indexed context available; use only the supplied weak topics and extra context.'}

Rules:
- Be concrete and useful for students preparing for interviews.
- Do not claim a source says something unless it appears in source context.
- Use markdown formatting.
""".strip()
    fallback = _fallback_generation(generation_type, weak_topics, results, extra_context)
    output = llm_service.generate(system_prompt, user_payload, fallback=fallback, temperature=0.42, max_tokens=1200)
    save_generated_output(user_id, generation_type, output, doc_ids, sources)
    return {"output": output, "sources": sources}


def generate_session_plan(*, session: dict[str, Any] | None, doc_ids: list[str], user_id: str) -> dict[str, Any]:
    weak_topics = _extract_weak_topics(session or {})
    extra = ""
    if session:
        extra = f"Round: {session.get('round_type')}\nCompany: {session.get('target_company')}\nRole: {session.get('job_role')}\nSummary: {session.get('summary') or session.get('report', {}).get('summary', '')}"
    return generate_material(
        generation_type="revision_plan",
        doc_ids=doc_ids,
        user_id=user_id,
        weak_topics=weak_topics,
        extra_context=extra,
    )


def generate_opportunity_prep(*, title: str, description: str, url: str, resume_profile: dict[str, Any], user_id: str) -> str:
    system_prompt = "You are CodeVoir's Opportunity Preparation Agent. Help a student prepare for a hackathon, job, internship, or competition."
    payload = {
        "opportunity_title": title,
        "description": description,
        "url": url,
        "resume_profile": resume_profile,
        "required_output": [
            "why the user matches",
            "missing skills",
            "application pitch",
            "project idea or preparation strategy",
            "likely interview/judging questions",
            "3-day preparation plan",
        ],
    }
    fallback = f"## Preparation plan for {title}\n\n- Review the opportunity requirements.\n- Match your resume skills to the listed skills.\n- Prepare a short pitch explaining why your projects fit.\n- Practice 5 technical and 3 HR questions.\n- Use CodeVoir's Learning Agent to revise any missing skills."
    return llm_service.generate(system_prompt, payload, fallback=fallback, temperature=0.45, max_tokens=950)


def generate_weak_answer_rewrite(*, question: str, answer: str, target_role: str, doc_ids: list[str], user_id: str) -> dict[str, Any]:
    query = question or answer[:240] or "weak interview answer"
    results = search_chunks(query, doc_ids=doc_ids, user_id=user_id, top_k=5)
    sources = source_summaries(results)
    context = _context_from_results(results)
    system_prompt = "You are CodeVoir's strict but helpful interview coach."
    user_payload = f"""
Rewrite and improve this weak interview answer.

Target role: {target_role or 'Not specified'}
Question: {question or 'Not provided'}
Candidate answer:
{answer}

Relevant source context:
{context or 'No source context available.'}

Return in this exact structure:
## Score
Give a score out of 100 and one-line reason.

## What is weak
Bullet points.

## Strong answer
Rewrite the answer like a confident candidate.

## Why this works
Explain why the improved version is better.

## Practice tip
Give 3 short tips.
""".strip()
    fallback = (
        "## Score\n60/100 — the answer needs clearer structure, technical depth, and evidence.\n\n"
        "## What is weak\n- It is too generic.\n- It does not explain tradeoffs or impact.\n- It lacks examples.\n\n"
        f"## Strong answer\n{answer}\n\nI would strengthen this by adding context, a technical reason, measurable impact, and one practical example.\n\n"
        "## Why this works\nIt gives the interviewer proof that you understand the decision, not just the tool name.\n\n"
        "## Practice tip\n1. Use Situation → Action → Result.\n2. Add one technical tradeoff.\n3. End with measurable impact."
    )
    output = llm_service.generate(system_prompt, user_payload, fallback=fallback, temperature=0.38, max_tokens=950)
    save_generated_output(user_id, "weak_answer_rewrite", output, doc_ids, sources)
    return {"output": output, "sources": sources}


def generate_source_mock_interview(*, doc_ids: list[str], user_id: str, difficulty: str = "medium", count: int = 6) -> dict[str, Any]:
    query = f"{difficulty} technical interview questions architecture concepts implementation tradeoffs"
    results = search_chunks(query, doc_ids=doc_ids, user_id=user_id, top_k=10)
    sources = source_summaries(results)
    context = _context_from_results(results)
    if not context:
        return {"output": "Upload or select a source first, then I can create a source-based mock interview.", "sources": []}
    system_prompt = "You are CodeVoir's source-grounded technical interviewer."
    user_payload = f"""
Create a mock interview from the selected source material.

Difficulty: {difficulty}
Number of questions: {count}

Source context:
{context}

Return in this exact format:
## Mock Interview From Source

### Q1: <question>
Expected Points:
- ...
Follow-up:
- ...
What It Tests:
- ...

Repeat until Q{count}. Keep questions grounded in the source.
""".strip()
    fallback = "## Mock Interview From Source\n\n" + "\n".join(
        f"### Q{idx}: Explain one important concept from the selected source.\nExpected Points:\n- Define the concept.\n- Explain why it matters.\n- Give one practical example.\nFollow-up:\n- How would you use this in a project?\nWhat It Tests:\n- Concept clarity and interview communication.\n"
        for idx in range(1, count + 1)
    )
    output = llm_service.generate(system_prompt, user_payload, fallback=fallback, temperature=0.44, max_tokens=1300)
    save_generated_output(user_id, "source_mock_interview", output, doc_ids, sources)
    return {"output": output, "sources": sources}


def _context_from_results(results: list[dict[str, Any]]) -> str:
    chunks = []
    for index, item in enumerate(results, start=1):
        meta = item.get("metadata") or {}
        label = meta.get("file_path") or meta.get("url") or meta.get("source") or meta.get("title") or "source"
        chunks.append(f"[Source {index}: {label}]\n{item.get('text', '')}")
    return "\n\n---\n\n".join(chunks)


def _overview_first_chunks(doc_ids: list[str], user_id: str) -> list[dict[str, Any]]:
    chunks = get_chunks_for_docs(doc_ids, user_id)
    if not chunks:
        return []

    def rank(item: dict[str, Any]) -> tuple[int, int]:
        meta = item.get("metadata") or {}
        file_path = str(meta.get("file_path") or meta.get("source") or "").lower()
        if meta.get("source_role") == "repo_overview" or "repository_overview" in file_path:
            return (0, int(meta.get("chunk_index") or 0))
        if "readme" in file_path:
            return (1, int(meta.get("chunk_index") or 0))
        if file_path.endswith(("package.json", "pyproject.toml", "requirements.txt")):
            return (2, int(meta.get("chunk_index") or 0))
        return (3, int(meta.get("chunk_index") or 0))

    return sorted(chunks, key=rank)[:12]


def _fallback_generation(generation_type: str, weak_topics: list[str], results: list[dict[str, Any]], extra_context: str) -> str:
    excerpt = (results[0].get("text") if results else extra_context) if (results or extra_context) else ""
    clean_points = _fallback_points(excerpt)
    if generation_type == "flashcards":
        return _source_locked_flashcards(results, weak_topics, extra_context)
    title = "Summary Notes" if generation_type in {"notes", "summary"} else generation_type.replace("_", " ").title()
    return (
        f"## {title}\n\n"
        + ("\n".join(f"- {point}" for point in clean_points) if clean_points else "- No clean source context was available from this URL.")
    )


def _fallback_points(text: str) -> list[str]:
    text = re.sub(
        r"(Resetting focus:|You signed in with another tab or window\.|You signed out in another tab or window\.|"
        r"You switched accounts on another tab or window\.|Reload to refresh your session\.|Dismiss alert|"
        r"Skip to content|Navigation Menu|Toggle navigation|Sign in|Appearance settings|Search or jump to|"
        r"\{\{\s*message\s*\}\})",
        " ",
        text or "",
        flags=re.I,
    )
    sentences = re.split(r"(?<=[.!?])\s+|\n+", re.sub(r"\s+", " ", text))
    points: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip(" -\t")
        if len(sentence) < 40:
            continue
        if re.search(r"^(url|pdf|github|sign in|sign up|navigation|toggle|reload|dismiss|search)\b", sentence, re.I):
            continue
        points.append(sentence[:220])
        if len(points) == 5:
            break
    return points


def _source_locked_flashcards(results: list[dict[str, Any]], weak_topics: list[str], extra_context: str) -> str:
    points = _source_highlights(results, extra_context)
    return _fallback_flashcards(points, weak_topics)


def _source_highlights(results: list[dict[str, Any]], extra_context: str) -> list[str]:
    highlights: list[str] = []
    seen: set[str] = set()
    source_texts = [str(item.get("text", "")) for item in results if item.get("text")]
    if extra_context:
        source_texts.append(extra_context)

    for text in source_texts:
        for point in _fallback_points(text):
            key = re.sub(r"\W+", " ", point).strip().lower()[:120]
            if not key or key in seen:
                continue
            seen.add(key)
            highlights.append(point)
            if len(highlights) >= 8:
                return highlights
    return highlights


def _fallback_flashcards(points: list[str], weak_topics: list[str]) -> str:
    topics = [topic.strip() for topic in weak_topics if topic.strip()]
    seed_points = points[:8]
    if len(seed_points) < 5:
        seed_points.extend(
            f"Review {topic} by connecting the definition, why it matters, and one interview example."
            for topic in topics
        )
    if not seed_points:
        seed_points = [
            "No clean source context was available, so upload or select a source before generating flashcards.",
        ]

    cards: list[str] = []
    for index, point in enumerate(seed_points[:8], start=1):
        question = _direct_flashcard_question(point, index)
        answer = point.rstrip(".")
        cards.append(f"Q: {question}\nA: {answer}.")
    return "\n\n".join(cards)


def _direct_flashcard_question(point: str, index: int) -> str:
    cleaned = re.sub(r"[*_`#]+", "", point).strip(" -\t")
    if not cleaned:
        return f"Explain highlight {index}?"
    if ":" in cleaned:
        subject, detail = cleaned.split(":", 1)
        subject = subject.strip()
        detail_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+/#-]*", detail)
        if subject and detail_words:
            return f"How does {subject} use {' '.join(detail_words[:6]).lower()}?"
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+/#-]*", cleaned)
    if len(words) >= 6:
        subject = " ".join(words[:4])
        return f"How would you explain {subject}?"
    if len(words) >= 3:
        return f"Explain {' '.join(words[:5])}?"
    return f"Explain highlight {index}?"


def _flashcard_focus(point: str, index: int) -> str:
    cleaned = re.sub(r"[*_`#]+", "", point).strip()
    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[0]
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9+/#-]*", cleaned)
    if len(words) >= 3:
        return " ".join(words[:8]).lower()
    return f"highlight {index}"


def _extract_weak_topics(session: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    report = session.get("report") if isinstance(session.get("report"), dict) else {}
    for key in ("weak_areas", "improvement_areas", "gaps", "recommended_topics"):
        value = session.get(key) or report.get(key)
        if isinstance(value, list):
            candidates.extend(str(item) for item in value if item)
        elif isinstance(value, str):
            candidates.extend([part.strip() for part in value.split(",") if part.strip()])
    if not candidates:
        summary = session.get("summary") or report.get("summary") or ""
        # Safe generic fallback if reports do not expose structured weak areas.
        if "code" in summary.lower():
            candidates.append("code explanation and complexity analysis")
        if "communication" in summary.lower():
            candidates.append("structured interview communication")
    return candidates[:8] or ["project explanation", "core technical fundamentals", "interview communication"]
