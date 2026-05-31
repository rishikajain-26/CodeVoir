from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from html import unescape
from html.parser import HTMLParser
from typing import Any

MIN_READABLE_TEXT_CHARS = 240


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip_stack: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "canvas", "noscript", "nav", "footer", "header", "aside", "form", "button", "select"}:
            self.skip_stack.append(tag)
        if tag in {"p", "div", "section", "article", "h1", "h2", "h3", "li", "br", "pre", "code"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.skip_stack and self.skip_stack[-1] == tag:
            self.skip_stack.pop()
        if tag in {"p", "section", "article", "li", "pre"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_stack and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        raw = unescape(" ".join(self.parts))
        raw = re.sub(r"\s*\n\s*", "\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return _clean_extracted_text(raw)


def load_url(url: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    original_url = normalize_url(url)
    url = normalize_url(url)
    if not re.match(r"^https?://", url, re.I):
        raise ValueError("Only http and https URLs are supported.")
    if is_github_url(url):
        raise ValueError("GitHub repository URLs should be added from the GitHub tab so CodeVoir indexes repository files instead of the GitHub web page.")
    try:
        html, content_type, fetched_url = _fetch_url_html(url)
    except ValueError:
        raise
    except Exception as exc:
        text = _unreachable_url_fallback_text(url, exc)
        return (
            [{"text": text, "url": original_url, "resolved_url": url, "source": url}],
            {"url": original_url, "resolved_url": url, "title": url, "content_type": "", "fetch_warning": str(exc)},
        )
    title = _extract_title(html) or url

    # Prefer trafilatura if the developer has installed it; otherwise stdlib parser.
    text = ""
    try:
        import trafilatura

        text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True) or ""
    except Exception:
        text = ""
    if not text:
        parser = _TextExtractor()
        parser.feed(html)
        text = parser.text()
    text = _clean_extracted_text(text)
    if len(text.strip()) < MIN_READABLE_TEXT_CHARS:
        devdocs_source = _extract_devdocs_source_url(html)
        if devdocs_source and devdocs_source != fetched_url and devdocs_source != original_url:
            items, metadata = load_url(devdocs_source)
            resolved_url = metadata.get("resolved_url") or metadata.get("url") or devdocs_source
            for item in items:
                item["url"] = original_url
                item["resolved_url"] = resolved_url
            return items, {
                **metadata,
                "url": original_url,
                "resolved_url": resolved_url,
                "source": metadata.get("title") or title,
            }
        text = _metadata_fallback_text(title, html, fetched_url)
    return ([{"text": text, "url": original_url, "resolved_url": fetched_url, "source": title}], {"url": original_url, "resolved_url": fetched_url, "title": title, "content_type": content_type})


def normalize_url(url: str) -> str:
    value = _extract_first_url(url)
    if value and not re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
        value = f"https://{value}"
    value = re.sub(r"^(https?://share\.google/[^/?#]+)/$", r"\1", value, flags=re.I)
    return value


def _extract_first_url(value: str) -> str:
    value = (value or "").strip()
    match = re.search(r"(https?://[^\s<>()]+|(?:share\.google|www\.[^\s<>()]+|[a-z0-9.-]+\.[a-z]{2,})(?:/[^\s<>()]*)?)", value, re.I)
    if match:
        return match.group(1).rstrip('.,;:!?)"\'')
    return value


def is_google_app_share_url(url: str) -> bool:
    return bool(re.match(r"^https?://share\.google(?:/|$)", normalize_url(url), re.I))


def is_github_url(url: str) -> bool:
    return bool(re.match(r"^https?://(?:www\.)?github\.com/", normalize_url(url), re.I))


def _fetch_url_html(url: str) -> tuple[str, str, str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; CodeVoirLearningAgent/1.0; +https://codevoir.local)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.7",
    })
    try:
        with urllib.request.urlopen(req, timeout=16) as response:
            content_type = response.headers.get("content-type", "")
            raw = response.read(2_000_000)
            fetched_url = response.geturl()
    except urllib.error.HTTPError as exc:
        raw = exc.read(2_000_000)
        if raw:
            return raw.decode("utf-8", errors="ignore"), exc.headers.get("content-type", ""), exc.geturl()
        raise ValueError(f"This URL returned HTTP {exc.code}. Try a public article page or paste the content as notes.") from exc
    return raw.decode("utf-8", errors="ignore"), content_type, fetched_url


def _extract_devdocs_source_url(html: str) -> str:
    match = re.search(r'<body[^>]*\bdata-doc="([^"]+)"', html, re.I | re.S)
    if not match:
        return ""
    try:
        doc = json.loads(unescape(match.group(1)))
    except (TypeError, json.JSONDecodeError):
        return ""
    home = doc.get("links", {}).get("home", "")
    return home if re.match(r"^https?://", home, re.I) else ""


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not match:
        return ""
    return re.sub(r"\s+", " ", unescape(match.group(1))).strip()


def _extract_meta_description(html: str) -> str:
    match = re.search(r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)["\']', html, re.I | re.S)
    if not match:
        match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:description|og:description)["\']', html, re.I | re.S)
    return re.sub(r"\s+", " ", unescape(match.group(1))).strip() if match else ""


def _metadata_fallback_text(title: str, html: str, url: str) -> str:
    description = _extract_meta_description(html)
    parts = [f"Page title: {title or url}"]
    if description:
        parts.append(f"Page description: {description}")
    parts.append(
        "Readable page body text was limited. Use this source for high-level page metadata, "
        "or paste the page text directly for deeper notes, flashcards, and flowcharts."
    )
    parts.append(f"Source URL: {url}")
    return "\n\n".join(parts)


def _unreachable_url_fallback_text(url: str, exc: Exception) -> str:
    reason = str(exc).replace("\n", " ").strip() or exc.__class__.__name__
    return (
        f"Source URL: {url}\n\n"
        "The server could not fetch readable page content from this URL during indexing. "
        "This can happen when a site blocks automated requests, requires JavaScript, requires a login, "
        "or the current machine has no outbound network access.\n\n"
        f"Fetch detail: {reason}\n\n"
        "For full summaries, flashcards, and flowcharts, paste the page text into Notes, upload a PDF, "
        "or use a public documentation/article URL that allows server-side fetching."
    )


def _clean_extracted_text(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(
        r"(Resetting focus:|You signed in with another tab or window\.|You signed out in another tab or window\.|"
        r"You switched accounts on another tab or window\.|Reload to refresh your session\.|Dismiss alert|"
        r"Skip to content|Navigation Menu|Toggle navigation|Sign in|Appearance settings|Search or jump to|"
        r"\{\{\s*message\s*\}\})",
        " ",
        text,
        flags=re.I,
    )
    lines = []
    for line in re.split(r"(?<=[.!?])\s+|\n+", text):
        line = re.sub(r"\s+", " ", line).strip(" -\t")
        if len(line) < 24:
            continue
        if re.search(r"^(sign in|sign up|skip to|navigation|toggle|reload|dismiss|search)\b", line, re.I):
            continue
        lines.append(line)
    return "\n\n".join(lines).strip()
