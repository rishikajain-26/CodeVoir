"""
LLM-based resume analyzer: extracts CGPA, college year, skills, interests, branch,
projects, and work experience.  Falls back to regex when no LLM key is configured.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Reference year for college-year calculation
_REF_YEAR = 2026

_SYSTEM = (
    "You are an expert resume parser for engineering students. "
    "Extract structured data with high precision. "
    "Scan EVERY section: Education, Skills, Projects, Experience, "
    "Certifications, Coursework, Achievements. "
    "Return ONLY valid JSON — no markdown fences, no prose."
)

_PROMPT_TMPL = """\
Parse the resume below. Extract ALL requested fields by reading every section carefully.

Return ONLY valid JSON with these exact keys:

{{
  "cgpa": <float on a 10-point scale, or null.
           If given as X/4  → multiply by 2.5.
           If percentage    → divide by 10.
           If X/10 or plain decimal 6–10 → use as-is.>,

  "graduation_year": <4-digit integer: the FINAL/END year of the degree.
                      If the resume shows "2022–2026", use 2026.
                      If it says "Expected May 2027", use 2027.
                      Null if not found.>,

  "college_year": <integer 1–4: current year of study calculated as
                   4 – (graduation_year – {ref_year}).
                   E.g. grad 2026 → 4th year; grad 2027 → 3rd; grad 2028 → 2nd; grad 2029 → 1st.
                   If graduation_year is null, infer from context (e.g. "2nd year student") or null.>,

  "branch": <exact one of: "computer science" | "information technology" |
             "electronics" | "electrical" | "mechanical" | "civil" |
             "chemical" | "data science" | "artificial intelligence" |
             or other branch in lowercase | null>,

  "education_level": <"b.tech" | "b.e." | "m.tech" | "bca" | "mca" |
                      "b.sc" | "m.sc" | "ph.d" | or other lowercase | null>,

  "skills": [<ALL technical skills found ANYWHERE in the resume as lowercase strings.
              Include: programming languages, frameworks, libraries, tools,
              databases, cloud platforms, protocols, OS, DevOps tools,
              ML/AI frameworks, testing frameworks.
              Do NOT miss skills mentioned only in project or experience descriptions.>],

  "interests": [<infer domain interests from project topics, courses taken,
                 experience domains, and skill clusters.
                 Use ONLY these categories (include multiple if relevant):
                 "machine learning", "web development", "data science",
                 "mobile development", "cloud computing", "blockchain",
                 "cybersecurity", "game development", "competitive programming",
                 "open source", "embedded systems", "robotics",
                 "natural language processing", "computer vision",
                 "quantitative finance", "devops", "database engineering",
                 "system design", "ui/ux design">],

  "projects": [
    {{
      "title": <project name as written in resume>,
      "tech":  [<technologies/tools used, lowercase>],
      "domain": <one-line inferred domain e.g. "NLP chatbot", "e-commerce web app">
    }}
  ],

  "experience": [
    {{
      "role":    <job or internship title>,
      "company": <company name>,
      "domain":  <work domain e.g. "backend development", "data engineering">
    }}
  ]
}}

Reference year for college_year calculation: {ref_year}

IMPORTANT RULES:
- skills must be COMPREHENSIVE — include every technology name you see, even once.
- interests must be INFERRED — if someone built an "image classifier using CNN", add "machine learning" and "computer vision".
- graduation_year must be the END year (not start year) of the degree program.
- Return empty lists [] not null for skills/interests/projects/experience.

Resume:
{{resume_text}}"""

# Build the actual template string (handle the nested braces carefully)
_PROMPT_TMPL = _PROMPT_TMPL.replace("{ref_year}", str(_REF_YEAR)).replace("{{resume_text}}", "{resume_text}")


# ── LLM call ──────────────────────────────────────────────────────────────────

def _call_llm(resume_text: str) -> Optional[dict[str, Any]]:
    prompt = _PROMPT_TMPL.format(resume_text=resume_text[:6000])

    # 1. Anthropic / Claude
    try:
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            client = anthropic.Anthropic(api_key=key)
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            # Strip markdown fences if model includes them
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
    except Exception as exc:
        logger.debug("Claude resume analysis: %s", exc)

    # 2. Groq / Gemini via litellm
    try:
        import litellm

        groq_key = os.environ.get("GROQ_API_KEY", "")
        gemini_key = (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        )

        model: Optional[str] = None
        if groq_key:
            os.environ.setdefault("GROQ_API_KEY", groq_key)
            model = "groq/llama-3.3-70b-versatile"
        elif gemini_key:
            os.environ.setdefault("GEMINI_API_KEY", gemini_key)
            model = "gemini/gemini-1.5-flash"

        if model:
            resp = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2048,
                temperature=0.0,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
    except Exception as exc:
        logger.debug("LiteLLM resume analysis: %s", exc)

    return None


# ── Comprehensive skill vocabulary ────────────────────────────────────────────

_KNOWN_SKILLS = [
    # Languages
    "python", "java", "c++", "c", "javascript", "typescript", "rust", "golang", "go",
    "swift", "kotlin", "c#", "php", "ruby", "scala", "r", "matlab", "perl",
    "bash", "shell", "powershell", "dart", "lua", "haskell", "elixir", "groovy",
    "vhdl", "verilog", "assembly", "solidity",
    # Web frontend
    "react", "angular", "vue", "vuejs", "nextjs", "nuxtjs", "svelte",
    "html", "css", "sass", "scss", "tailwind", "tailwindcss", "bootstrap",
    "jquery", "redux", "webpack", "vite",
    # Web backend
    "nodejs", "node.js", "express", "django", "flask", "fastapi", "spring",
    "laravel", "rails", "asp.net", "fiber", "gin", "echo",
    # Mobile
    "react native", "flutter", "android", "ios", "xamarin",
    # ML / AI
    "tensorflow", "pytorch", "keras", "scikit-learn", "sklearn",
    "huggingface", "transformers", "opencv", "pillow", "nltk", "spacy",
    "langchain", "llamaindex", "openai", "anthropic", "gemini",
    "xgboost", "lightgbm", "catboost", "rapids",
    # Data
    "pandas", "numpy", "matplotlib", "seaborn", "plotly", "tableau",
    "power bi", "looker", "spark", "hadoop", "kafka", "airflow", "dbt",
    "luigi", "prefect",
    # Databases
    "mongodb", "postgresql", "mysql", "sqlite", "redis", "elasticsearch",
    "cassandra", "dynamodb", "firebase", "supabase", "neo4j", "influxdb",
    "clickhouse", "bigquery", "snowflake", "mssql", "mariadb",
    # Cloud / Infra
    "aws", "azure", "gcp", "google cloud", "heroku", "vercel", "netlify",
    "cloudflare", "digitalocean",
    "docker", "kubernetes", "k8s", "terraform", "ansible", "puppet", "chef",
    "jenkins", "github actions", "gitlab ci", "circleci", "travis ci",
    "prometheus", "grafana", "datadog", "elk stack", "nginx", "apache",
    # Version control / collab
    "git", "github", "gitlab", "bitbucket",
    # Testing
    "pytest", "junit", "jest", "mocha", "cypress", "selenium", "playwright",
    "postman", "insomnia",
    # APIs / Protocols
    "rest api", "graphql", "grpc", "websocket", "oauth", "jwt",
    "microservices", "kafka", "rabbitmq", "celery",
    # Blockchain
    "blockchain", "solidity", "web3", "ethereum", "hardhat", "truffle",
    # Systems / Embedded
    "linux", "unix", "rtos", "embedded c", "raspberry pi", "arduino",
    "stm32", "can bus", "i2c", "spi",
    # CS fundamentals
    "data structures", "algorithms", "system design", "oops", "oop",
    "operating systems", "computer networks", "dbms", "sql", "nosql",
]

_INTEREST_MAP = {
    "machine learning": [
        "machine learning", " ml ", "deep learning", "neural network",
        "neural net", "lstm", "transformer", "bert", "gpt", "diffusion",
        "reinforcement learning", "random forest", "decision tree",
        "classification", "regression", "clustering", "feature engineer",
    ],
    "natural language processing": [
        "nlp", "natural language", "text classification", "sentiment",
        "named entity", "ner ", "text generation", "summarization",
        "chatbot", "language model", "tokeniz", "word embedding",
    ],
    "computer vision": [
        "computer vision", "image classification", "object detection",
        "image segmentation", "cnn", "convolutional", "yolo", "opencv",
        "face recognition", "ocr",
    ],
    "data science": [
        "data science", "data analysis", "analytics", "big data",
        "data engineering", "etl", "data pipeline", "visualization",
        "tableau", "power bi", "statistical",
    ],
    "web development": [
        "web development", "frontend", "backend", "full stack", "fullstack",
        "web app", "website", "rest api", "graphql", "e-commerce", "ecommerce",
    ],
    "mobile development": [
        "android", "ios ", "mobile", "react native", "flutter",
        "app development", "mobile app",
    ],
    "cloud computing": [
        "cloud", "aws", "azure", "gcp", "google cloud", "devops",
        "infrastructure", "serverless", "microservice", "kubernetes", "docker",
    ],
    "devops": [
        "devops", "ci/cd", "continuous integration", "continuous deployment",
        "jenkins", "github actions", "terraform", "ansible", "monitoring",
        "observability",
    ],
    "blockchain": [
        "blockchain", "crypto", "web3", "solidity", "defi", "nft",
        "smart contract", "ethereum",
    ],
    "cybersecurity": [
        "security", "cybersecurity", "ethical hacking", "penetration",
        "ctf", "infosec", "vulnerability", "cryptography", "malware",
        "network security", "firewall",
    ],
    "game development": [
        "game development", "unity", "unreal", "game design", "game engine",
        "opengl", "directx", "godot",
    ],
    "competitive programming": [
        "competitive programming", "codeforces", "codechef", "leetcode",
        " cp ", "icpc", "olympiad", "competitive coding",
    ],
    "embedded systems": [
        "embedded", "firmware", "rtos", "microcontroller", "arduino",
        "raspberry pi", "iot", "internet of things", "hardware",
        "fpga", "vhdl", "verilog",
    ],
    "robotics": [
        "robotics", "robot", "ros ", "autonomous", "drone",
        "servo", "actuator", "sensor fusion",
    ],
    "quantitative finance": [
        "quantitative", "algorithmic trading", "quant", "financial model",
        "derivatives", "options", "portfolio", "risk model",
    ],
    "open source": [
        "open source", "github contribution", "foss", "pull request",
        "contributor", "maintainer",
    ],
}


# ── Regex fallback ─────────────────────────────────────────────────────────────

def _regex_analyze(text: str) -> dict[str, Any]:
    tl = text.lower()

    # ── CGPA ──
    cgpa: Optional[float] = None
    cgpa_patterns = [
        (r"(?:cgpa|cpi|sgpa|gpa)[^\d]{0,10}(\d+\.?\d*)\s*/\s*10", "x/10"),
        (r"(?:cgpa|cpi|sgpa|gpa)[^\d]{0,10}(\d+\.?\d*)\s*/\s*4", "x/4"),
        (r"(?:cgpa|cpi|sgpa|gpa)[^\d]{0,10}(\d+\.?\d*)", "bare"),
        (r"(\d+\.?\d*)\s*/\s*10(?:\s|\b)", "x/10"),
        (r"(\d+\.?\d*)\s*/\s*4(?:\s|\b)", "x/4"),
        (r"percentage[^\d]{0,10}(\d{2,3}\.?\d*)", "pct"),
    ]
    for pat, kind in cgpa_patterns:
        m = re.search(pat, tl)
        if m:
            try:
                v = float(m.group(1))
                if kind == "x/4":
                    v = v * 2.5
                elif kind == "pct":
                    v = v / 10.0
                if 0 < v <= 10:
                    cgpa = round(v, 2)
                    break
            except Exception:
                pass

    # ── Graduation year ── (take the END year of any range)
    grad_year: Optional[int] = None
    college_year: Optional[int] = None

    # Priority 1: explicit keywords
    kw_pats = [
        r"(?:graduating|graduation|expected|batch|class of|passout)[^\d]{0,20}(\d{4})",
        r"expected[^\d]{0,10}(?:graduation|completion)[^\d]{0,10}(\d{4})",
        r"(?:class|batch)\s+of\s+(\d{4})",
    ]
    for pat in kw_pats:
        m = re.search(pat, tl)
        if m:
            try:
                yr = int(m.group(1))
                if 2020 <= yr <= 2032:
                    grad_year = yr
                    break
            except Exception:
                pass

    # Priority 2: year range "XXXX - YYYY" → take YYYY
    if not grad_year:
        for m in re.finditer(r"(\d{4})\s*[-–—]\s*(\d{4})", tl):
            try:
                y1, y2 = int(m.group(1)), int(m.group(2))
                if 2020 <= y2 <= 2032 and y2 > y1:
                    grad_year = y2
                    break
            except Exception:
                pass

    # Priority 3: "XXXX - present" → start year, can infer
    if not grad_year:
        m = re.search(r"(\d{4})\s*[-–—]\s*(?:present|ongoing|current)", tl)
        if m:
            try:
                yr = int(m.group(1))
                if 2020 <= yr <= 2026:
                    # If they started in yr, 4-year program → grad yr+4
                    grad_year = yr + 4
            except Exception:
                pass

    if grad_year:
        diff = grad_year - _REF_YEAR
        college_year = max(1, min(4, 4 - diff))

    # Explicit year mention
    if not college_year:
        for pat in [
            r"(\d)(?:st|nd|rd|th)\s+year",
            r"year\s+(\d)",
            r"(\d)(?:st|nd|rd|th)\s+sem",
        ]:
            m = re.search(pat, tl)
            if m:
                try:
                    yr = int(m.group(1))
                    if 1 <= yr <= 4:
                        college_year = yr
                        break
                except Exception:
                    pass

    # ── Skills ── scan everything, deduplicate
    skills_found = []
    for s in _KNOWN_SKILLS:
        # Use word-boundary-like check for short skill names
        if len(s) <= 2:
            if re.search(r"\b" + re.escape(s) + r"\b", tl):
                skills_found.append(s)
        else:
            if s in tl:
                skills_found.append(s)
    # Deduplicate preserving order
    seen: set[str] = set()
    skills: list[str] = []
    for s in skills_found:
        if s not in seen:
            seen.add(s)
            skills.append(s)

    # ── Interests ── infer from full text
    interests = [
        interest
        for interest, keywords in _INTEREST_MAP.items()
        if any(kw in tl for kw in keywords)
    ]

    # ── Education level ──
    edu: Optional[str] = None
    for label, pats in [
        ("b.tech", [r"b\.?\s*tech", r"btech"]),
        ("b.e.", [r"b\.?\s*e\.", r"\bbe\b"]),
        ("m.tech", [r"m\.?\s*tech", r"mtech"]),
        ("bca", [r"\bbca\b"]),
        ("mca", [r"\bmca\b"]),
        ("b.sc", [r"b\.?\s*sc\b"]),
        ("m.sc", [r"m\.?\s*sc\b"]),
        ("ph.d", [r"ph\.?\s*d\b", r"\bphd\b"]),
    ]:
        if any(re.search(p, tl) for p in pats):
            edu = label
            break

    # ── Branch ──
    branch: Optional[str] = None
    for br, kws in [
        ("artificial intelligence", ["artificial intelligence", " ai & ml", "ai and ml"]),
        ("data science", ["data science and engineering", "data science"]),
        ("computer science", [
            "computer science", " cse", "cs&e", "csit",
            "information technology", " it ", "software engineering",
        ]),
        ("electronics", ["electronics", " ece", " eee", "electrical and electronics"]),
        ("electrical", ["electrical engineering", " ee "]),
        ("mechanical", ["mechanical", " mech"]),
        ("civil", ["civil engineering"]),
        ("chemical", ["chemical engineering"]),
    ]:
        if any(kw in tl for kw in kws):
            branch = br
            break

    # ── Project extraction (simple) ──
    projects: list[dict] = []
    proj_section = re.search(
        r"(?:project|projects)[^\n]*\n((?:.|\n)*?)(?:\n(?:experience|education|skill|certif|achievement|extra)|$)",
        tl, re.IGNORECASE,
    )
    if proj_section:
        # Extract any tech skills mentioned in the project section
        proj_text = proj_section.group(1)
        proj_skills = [s for s in _KNOWN_SKILLS if s in proj_text]
        if proj_skills:
            # Add any project skills not already in main skills list
            for ps in proj_skills:
                if ps not in seen:
                    seen.add(ps)
                    skills.append(ps)

    return {
        "cgpa": cgpa,
        "college_year": college_year,
        "graduation_year": grad_year,
        "skills": skills,
        "interests": interests,
        "branch": branch,
        "education_level": edu,
        "projects": projects,
        "experience": [],
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def analyze_resume(resume_text: str) -> dict[str, Any]:
    if not resume_text or len(resume_text.strip()) < 50:
        return {
            "cgpa": None, "college_year": None, "graduation_year": None,
            "skills": [], "interests": [], "branch": None,
            "education_level": None, "projects": [], "experience": [],
        }

    raw = _call_llm(resume_text) or {}
    result: dict[str, Any] = dict(raw)

    # ── Normalise skills ──
    skills_raw = result.get("skills") or []
    if isinstance(skills_raw, list):
        result["skills"] = [str(s).lower().strip() for s in skills_raw if s][:40]
    else:
        result["skills"] = []

    # ── Normalise interests ──
    ints_raw = result.get("interests") or []
    if isinstance(ints_raw, list):
        result["interests"] = [str(i).lower().strip() for i in ints_raw if i][:20]
    else:
        result["interests"] = []

    # ── Normalise CGPA ──
    try:
        v = float(result.get("cgpa") or 0)
        result["cgpa"] = round(v, 2) if 0 < v <= 10 else None
    except Exception:
        result["cgpa"] = None

    # ── Normalise college year ──
    try:
        yr = int(result.get("college_year") or 0)
        result["college_year"] = yr if 1 <= yr <= 4 else None
    except Exception:
        result["college_year"] = None

    # ── Normalise graduation year ──
    try:
        gy = int(result.get("graduation_year") or 0)
        result["graduation_year"] = gy if 2020 <= gy <= 2035 else None
    except Exception:
        result["graduation_year"] = None

    # ── If college_year missing but graduation_year present, recompute ──
    if not result["college_year"] and result["graduation_year"]:
        diff = result["graduation_year"] - _REF_YEAR
        result["college_year"] = max(1, min(4, 4 - diff))

    # ── Normalise projects & experience ──
    result["projects"] = result.get("projects") or []
    result["experience"] = result.get("experience") or []

    # ── Always run regex fallback; fill every missing / empty field ──
    fallback = _regex_analyze(resume_text)

    if not result["skills"]:
        result["skills"] = fallback["skills"]
    else:
        # Merge: add regex-found skills the LLM missed (keep LLM results primary)
        existing = {s.lower() for s in result["skills"]}
        extra = [s for s in fallback["skills"] if s not in existing]
        result["skills"] = result["skills"] + extra[:20]

    if not result["interests"]:
        result["interests"] = fallback["interests"]

    if result["cgpa"] is None:
        result["cgpa"] = fallback["cgpa"]

    if result["college_year"] is None:
        result["college_year"] = fallback["college_year"]

    if not result.get("graduation_year"):
        result["graduation_year"] = fallback["graduation_year"]

    if not result.get("branch"):
        result["branch"] = fallback["branch"]

    if not result.get("education_level"):
        result["education_level"] = fallback["education_level"]

    if not result["projects"]:
        result["projects"] = fallback["projects"]

    if not result["experience"]:
        result["experience"] = fallback["experience"]

    # Deduplicate skills preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for s in result["skills"]:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    result["skills"] = deduped[:40]

    return result
