from __future__ import annotations

import base64
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from xml.etree import ElementTree
from typing import Any

ALLOWED_EXTENSIONS = {
    ".md", ".txt", ".json", ".yaml", ".yml",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".css", ".html", ".sql", ".csv", ".ipynb", ".docx", ".rst", ".toml", ".ini", ".cfg",
    ".sh", ".ps1", ".bat", ".mjs", ".cjs", ".vue", ".svelte", ".go", ".rs", ".rb", ".php",
    ".kt", ".gradle", ".xml",
}
ALLOWED_FILENAMES = {"readme", "license", "dockerfile", "makefile", "procfile"}
BLOCKED_PARTS = {"node_modules", "dist", "build", ".git", "coverage", "__pycache__", ".next", "venv", ".venv", ".pytest_cache", ".mypy_cache"}
PRIORITY_NAMES = {"README.md", "package.json", "requirements.txt", "pyproject.toml", "main.py", "App.jsx", "App.tsx"}
MAX_ARCHIVE_BYTES = 35_000_000
MAX_FILE_BYTES = 2_000_000
ARCHIVE_BRANCH_CANDIDATES = ("main", "master")


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    value = normalize_github_repo_url(repo_url)
    match = re.search(r"github\.com[:/]([^/]+)/([^/#?]+)", value)
    if not match:
        raise ValueError("Please provide a valid GitHub repository URL.")
    return match.group(1), match.group(2).replace(".git", "")


def normalize_github_repo_url(repo_url: str) -> str:
    value = (repo_url or "").strip()
    ssh_match = re.search(r"git@github\.com:([^/\s]+)/([^/\s#?]+)", value, re.I)
    if ssh_match:
        repo = ssh_match.group(2).rstrip("/").removesuffix(".git")
        return f"https://github.com/{ssh_match.group(1)}/{repo}"
    match = re.search(r"https?://github\.com/[^/\s<>()]+/[^/\s<>()#?]+", value, re.I)
    if not match:
        match = re.search(r"github\.com/[^/\s<>()]+/[^/\s<>()#?]+", value, re.I)
    if not match:
        return value
    url = match.group(0).rstrip('.,;:!?)"\'/')
    if not re.match(r"^https?://", url, re.I):
        url = f"https://{url}"
    return url


def load_github_repo(repo_url: str, *, max_files: int = 28) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    owner, repo = parse_repo_url(repo_url)
    canonical_url = f"https://github.com/{owner}/{repo}"
    repo_metadata = _get_repo_metadata(owner, repo)
    overview = _repo_overview_item(repo_metadata, canonical_url, owner, repo)
    archive_items, archive_branch = _load_from_archive(owner, repo, max_files=max_files)
    if archive_items:
        items = [
            {"text": text, "file_path": path, "source": canonical_url, "repo": f"{owner}/{repo}"}
            for path, text in archive_items
        ]
        if overview:
            items.insert(0, overview)
        return items, {
            "repo": f"{owner}/{repo}",
            "repo_url": canonical_url,
            "description": repo_metadata.get("description") or "",
            "homepage": repo_metadata.get("homepage") or "",
            "topics": repo_metadata.get("topics") or [],
            "language": repo_metadata.get("language") or "",
            "files_indexed": len(items),
            "branch": archive_branch,
            "loader": "archive",
        }

    tree = _get_tree(owner, repo)
    candidates = [item for item in tree if item.get("type") == "blob" and _should_read(item.get("path", ""))]
    candidates.sort(key=lambda item: _priority(item.get("path", "")))
    items: list[dict[str, Any]] = []
    for item in candidates[:max_files]:
        path = item.get("path", "")
        try:
            text = _read_file(owner, repo, path)
        except Exception:
            continue
        if not text.strip():
            continue
        if len(text) > 24000:
            text = text[:24000] + "\n\n[File truncated for indexing.]"
        items.append({"text": text, "file_path": path, "source": canonical_url, "repo": f"{owner}/{repo}"})
    if not items:
        raise ValueError("No readable source files were found in this repository. The repo may be empty, private, binary-only, or unsupported by the file filters.")
    if overview:
        items.insert(0, overview)
    return items, {
        "repo": f"{owner}/{repo}",
        "repo_url": canonical_url,
        "description": repo_metadata.get("description") or "",
        "homepage": repo_metadata.get("homepage") or "",
        "topics": repo_metadata.get("topics") or [],
        "language": repo_metadata.get("language") or "",
        "files_indexed": len(items),
        "loader": "api",
    }


def _get_repo_metadata(owner: str, repo: str) -> dict[str, Any]:
    try:
        data = _request_json(f"https://api.github.com/repos/{owner}/{repo}")
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "full_name": data.get("full_name") or f"{owner}/{repo}",
        "description": data.get("description") or "",
        "homepage": data.get("homepage") or "",
        "topics": data.get("topics") or [],
        "language": data.get("language") or "",
        "default_branch": data.get("default_branch") or "",
        "stars": data.get("stargazers_count") or 0,
        "forks": data.get("forks_count") or 0,
    }


def _repo_overview_item(metadata: dict[str, Any], canonical_url: str, owner: str, repo: str) -> dict[str, Any] | None:
    if not metadata:
        return None
    lines = [
        f"# Repository overview: {metadata.get('full_name') or f'{owner}/{repo}'}",
    ]
    if metadata.get("description"):
        lines.append(f"Description: {metadata['description']}")
    if metadata.get("language"):
        lines.append(f"Primary language: {metadata['language']}")
    if metadata.get("topics"):
        lines.append(f"Topics: {', '.join(str(topic) for topic in metadata['topics'][:12])}")
    if metadata.get("homepage"):
        lines.append(f"Homepage: {metadata['homepage']}")
    if metadata.get("default_branch"):
        lines.append(f"Default branch: {metadata['default_branch']}")
    lines.append("Use this repository overview together with the README and key source files when summarizing the project.")
    text = "\n".join(lines).strip()
    if len(text) < 80:
        return None
    return {
        "text": text,
        "file_path": "REPOSITORY_OVERVIEW.md",
        "source": canonical_url,
        "repo": f"{owner}/{repo}",
        "source_role": "repo_overview",
    }


def _load_from_archive(owner: str, repo: str, *, max_files: int) -> tuple[list[tuple[str, str]], str]:
    last_error: Exception | None = None
    for branch in ARCHIVE_BRANCH_CANDIDATES:
        try:
            raw = _download_archive(owner, repo, branch)
            return _extract_archive_items(raw, max_files=max_files), branch
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        return [], ""
    return [], ""


def _download_archive(owner: str, repo: str, branch: str) -> bytes:
    url = f"https://codeload.github.com/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/zip/refs/heads/{urllib.parse.quote(branch)}"
    req = urllib.request.Request(url, headers={"User-Agent": "CodeVoirLearningAgent/1.0", "Accept": "application/zip,*/*;q=0.7"})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read(MAX_ARCHIVE_BYTES + 1)
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("GitHub repository archive is too large to index directly.")
    return raw


def _extract_archive_items(raw: bytes, *, max_files: int) -> list[tuple[str, str]]:
    candidates: list[tuple[str, int, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for info in archive.infolist():
            if info.is_dir() or info.file_size > MAX_FILE_BYTES:
                continue
            path = _strip_archive_root(info.filename)
            if not path or not _should_read(path):
                continue
            try:
                data = archive.read(info, pwd=None)
            except RuntimeError:
                continue
            candidates.append((path, info.file_size, data))
    candidates.sort(key=lambda item: _priority(item[0]))
    items: list[tuple[str, str]] = []
    for path, _size, data in candidates:
        text = _bytes_to_text(path, data)
        if not text.strip():
            continue
        if len(text) > 24000:
            text = text[:24000] + "\n\n[File truncated for indexing.]"
        items.append((path, text))
        if len(items) >= max_files:
            break
    return items


def _request_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "CodeVoirLearningAgent/1.0", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=18) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError("GitHub repository was not found or is private.") from exc
        if exc.code == 403:
            raise ValueError("GitHub API access is currently rate-limited or blocked. Try again later or use a smaller public repository.") from exc
        raise
    except urllib.error.URLError as exc:
        raise ValueError("Could not reach GitHub. Check your internet connection and try again.") from exc


def _get_tree(owner: str, repo: str) -> list[dict[str, Any]]:
    data = _request_json(f"https://api.github.com/repos/{owner}/{repo}")
    branch = data.get("default_branch", "main")
    data = _request_json(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
    return data.get("tree", [])


def _read_file(owner: str, repo: str, path: str) -> str:
    data = _request_json(f"https://api.github.com/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}")
    if isinstance(data, list) or data.get("type") != "file":
        return ""
    if data.get("size", 0) > MAX_FILE_BYTES:
        return ""
    content = data.get("content", "")
    if data.get("encoding") == "base64":
        return _bytes_to_text(path, base64.b64decode(content))
    return ""


def _should_read(path: str) -> bool:
    lowered = path.lower()
    if any(part in lowered.split("/") for part in BLOCKED_PARTS):
        return False
    name = lowered.rsplit("/", 1)[-1]
    return name in ALLOWED_FILENAMES or any(lowered.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def _priority(path: str) -> tuple[int, int, str]:
    name = path.rsplit("/", 1)[-1]
    lowered_name = name.lower()
    if lowered_name.startswith("readme") or name in PRIORITY_NAMES:
        return (0, len(path), path)
    if path.lower().endswith((".ipynb", ".docx")):
        return (1, len(path), path)
    if path.startswith(("src/", "app/", "pages/", "routes/", "controllers/", "models/", "backend/", "frontend/src/")):
        return (1, len(path), path)
    return (2, len(path), path)


def _strip_archive_root(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    return "/".join(parts[1:]) if len(parts) > 1 else path


def _bytes_to_text(path: str, raw: bytes) -> str:
    lowered = path.lower()
    if lowered.endswith(".ipynb"):
        return _notebook_to_text(raw)
    if lowered.endswith(".docx"):
        return _docx_to_text(raw)
    if b"\x00" in raw[:4096]:
        return ""
    return raw.decode("utf-8", errors="ignore")


def _notebook_to_text(raw: bytes) -> str:
    try:
        notebook = json.loads(raw.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return raw.decode("utf-8", errors="ignore")
    parts = []
    for index, cell in enumerate(notebook.get("cells", []), start=1):
        cell_type = cell.get("cell_type", "cell")
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        source = str(source).strip()
        if source:
            parts.append(f"Notebook cell {index} ({cell_type}):\n{source}")
    return "\n\n".join(parts)


def _docx_to_text(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile):
        return ""
    root = ElementTree.fromstring(xml)
    paragraphs = []
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t")).strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)
