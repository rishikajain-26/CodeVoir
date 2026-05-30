from pathlib import Path
import io
import sys
from types import SimpleNamespace
from uuid import uuid4
import zipfile

sys.modules.setdefault("litellm", SimpleNamespace(completion=lambda *args, **kwargs: None))

from app.learning_agent.services import chunker, source_store
from app.learning_agent.services import generator
from app.learning_agent.services.generator import _fallback_generation
from app.learning_agent.loaders.github_loader import _extract_archive_items, _notebook_to_text, normalize_github_repo_url, parse_repo_url
from app.learning_agent.loaders import url_loader
from app.learning_agent.loaders.url_loader import _extract_devdocs_source_url, is_google_app_share_url, normalize_url
from app.learning_agent.services.rag_engine import _fallback_answer
from app.learning_agent.services.vector_store import search_chunks


def _point_store_at(tmp_path: Path) -> None:
    source_store.BASE_DIR = tmp_path
    source_store.DOCS_DIR = tmp_path / "documents"
    source_store.CHUNKS_DIR = tmp_path / "chunks"
    source_store.OUTPUTS_DIR = tmp_path / "outputs"
    for directory in (source_store.DOCS_DIR, source_store.CHUNKS_DIR, source_store.OUTPUTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def test_create_document_uses_default_title_in_document_and_chunks(tmp_path):
    _point_store_at(tmp_path)

    doc = source_store.create_document(
        title="",
        source_type="url",
        raw_items=[{"text": "FastAPI dependency injection is useful for shared services.", "url": "https://example.com/fastapi"}],
        user_id="alice",
        metadata={"url": "https://example.com/fastapi"},
    )
    chunks = source_store.get_chunks(doc["doc_id"])

    assert doc["title"] == "https://example.com/fastapi"
    assert chunks
    assert chunks[0]["metadata"]["title"] == doc["title"]


def test_get_chunks_for_docs_filters_explicit_ids_by_user(tmp_path):
    _point_store_at(tmp_path)
    alice_doc = source_store.create_document(
        title="Alice notes",
        source_type="text",
        raw_items=[{"text": "Alice private dynamic programming notes."}],
        user_id="alice",
    )
    bob_doc = source_store.create_document(
        title="Bob notes",
        source_type="text",
        raw_items=[{"text": "Bob graph traversal notes."}],
        user_id="bob",
    )

    chunks = source_store.get_chunks_for_docs([alice_doc["doc_id"], bob_doc["doc_id"]], user_id="alice")

    assert {chunk["doc_id"] for chunk in chunks} == {alice_doc["doc_id"]}


def test_search_chunks_respects_user_filter_for_selected_ids(tmp_path):
    _point_store_at(tmp_path)
    alice_doc = source_store.create_document(
        title="Alice notes",
        source_type="text",
        raw_items=[{"text": "React reconciliation uses keys to preserve list identity."}],
        user_id="alice",
    )
    bob_doc = source_store.create_document(
        title="Bob notes",
        source_type="text",
        raw_items=[{"text": "Kubernetes probes check service health."}],
        user_id="bob",
    )

    results = search_chunks("kubernetes probes", doc_ids=[alice_doc["doc_id"], bob_doc["doc_id"]], user_id="alice")

    assert results
    assert {result["doc_id"] for result in results} == {alice_doc["doc_id"]}


def test_chunk_text_clamps_overlap_to_prevent_non_progress():
    chunks = chunker.chunk_text("abcdefghijklmnopqrstuvwxyz", chunk_size=10, overlap=100)

    assert chunks
    assert chunks[-1].endswith("z")


def test_delete_document_removes_document_and_chunks(tmp_path):
    _point_store_at(tmp_path)
    doc = source_store.create_document(
        title="Delete me",
        source_type="text",
        raw_items=[{"text": "This temporary source should be deleted cleanly."}],
        user_id="alice",
    )

    assert source_store.delete_document(doc["doc_id"], user_id="alice")
    assert source_store.get_document(doc["doc_id"]) is None
    assert source_store.get_chunks(doc["doc_id"]) == []


def test_url_normalization_accepts_plain_domains():
    assert normalize_url("example.com/page") == "https://example.com/page"
    assert normalize_url(" http://example.com ") == "http://example.com"


def test_url_normalization_extracts_share_links_from_pasted_titles():
    assert normalize_url("JavaScript documentation — DevDocs https://share.google/1WN6R5snLunFJSFY5/") == "https://share.google/1WN6R5snLunFJSFY5"
    assert normalize_url("share.google/1WN6R5snLunFJSFY5/") == "https://share.google/1WN6R5snLunFJSFY5"


def test_google_app_share_url_detection_accepts_plain_and_https_urls():
    assert is_google_app_share_url("share.google/1WN6R5snLunFJSFY5")
    assert is_google_app_share_url("https://share.google/1WN6R5snLunFJSFY5")
    assert not is_google_app_share_url("https://google.com/search?q=javascript")


def test_devdocs_source_url_is_extracted_from_data_doc():
    html = (
        '<body data-doc="{&quot;links&quot;:{'
        '&quot;home&quot;:&quot;https://developer.mozilla.org/en-US/docs/Web/JavaScript&quot;'
        '}}"></body>'
    )

    assert _extract_devdocs_source_url(html) == "https://developer.mozilla.org/en-US/docs/Web/JavaScript"


def test_url_loader_falls_back_when_fetch_is_blocked():
    original_fetch = url_loader._fetch_url_html
    url_loader._fetch_url_html = lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("network blocked"))
    try:
        items, metadata = url_loader.load_url("https://blocked.example/page")
    finally:
        url_loader._fetch_url_html = original_fetch

    assert metadata["url"] == "https://blocked.example/page"
    assert items
    assert "could not fetch readable page content" in items[0]["text"]


def test_github_repo_url_normalization_uses_repo_root_only():
    assert normalize_github_repo_url("Project repo: https://github.com/user/repo/blob/main/app.py") == "https://github.com/user/repo"
    assert normalize_github_repo_url("git@github.com:user/repo.git") == "https://github.com/user/repo"
    assert parse_repo_url("https://github.com/user/repo/tree/main/src") == ("user", "repo")


def test_notebook_cells_are_indexed_as_repo_content():
    raw = b'{"cells":[{"cell_type":"markdown","source":["# Project\\n","Network IDS"]},{"cell_type":"code","source":["model.fit(X_train, y_train)"]}]}'
    text = _notebook_to_text(raw)

    assert "Notebook cell 1 (markdown)" in text
    assert "Network IDS" in text
    assert "model.fit" in text


def test_github_archive_extraction_reads_repo_files():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("repo-main/README.md", "# Demo repo\nUseful project overview.")
        archive.writestr("repo-main/src/app.py", "print('hello')")
        archive.writestr("repo-main/node_modules/skip.js", "ignored")

    items = _extract_archive_items(buffer.getvalue(), max_files=5)
    paths = [path for path, _text in items]

    assert "README.md" in paths
    assert "src/app.py" in paths
    assert all("node_modules" not in path for path in paths)


def test_chat_fallback_explains_without_echoing_question_or_dumping_excerpt():
    output = _fallback_answer(
        "explain this like i am comman man",
        [{
            "text": (
                "Environmental impact Electric cars have lower environmental impacts than ICE cars, "
                "including a significant reduction of air pollution, as they do not emit exhaust pollutants. "
                "However, like ICE cars, electric cars emit particulates from tyres. "
                "Because EVs typically use regenerative braking, brake wear is much less. "
                "Battery manufacturing typically involves greater environmental costs than ICE vehicles."
            )
        }],
        "beginner",
    )

    assert "explain this like" not in output.lower()
    assert "Source-grounded excerpt" not in output
    assert "In simple words" in output
    assert "not completely impact-free" in output
    assert "Why it matters for interviews" in output


def test_flashcard_fallback_uses_source_highlights():
    results = [{
        "text": (
            "React reconciliation uses keys to preserve list identity. "
            "Dynamic programming stores overlapping subproblem results to avoid repeated work. "
            "FastAPI dependency injection shares services cleanly across routes. "
            "Binary search halves a sorted search space at every step. "
            "Indexes speed reads but add write overhead in databases."
        )
    }]

    output = _fallback_generation("flashcards", [], results, "")

    assert output.count("Q:") >= 5
    assert "What is key point" not in output
    assert "What is the key idea" not in output
    assert "React reconciliation uses keys" in output


def test_generate_flashcards_are_locked_to_selected_source(tmp_path):
    _point_store_at(tmp_path)
    doc = source_store.create_document(
        title="Interview notes",
        source_type="text",
        raw_items=[{
            "text": (
                "React reconciliation uses keys to preserve list identity. "
                "Dynamic programming stores overlapping subproblem results to avoid repeated work. "
                "FastAPI dependency injection shares services cleanly across routes. "
                "Binary search halves a sorted search space at every step. "
                "Indexes speed reads but add write overhead in databases."
            )
        }],
        user_id="alice",
    )
    original_generate = generator.llm_service.generate
    generator.llm_service.generate = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("LLM should not create flashcards"))
    try:
        result = generator.generate_material(generation_type="flashcards", doc_ids=[doc["doc_id"]], user_id="alice")
    finally:
        generator.llm_service.generate = original_generate

    output = result["output"]
    assert output.count("Q:") >= 5
    assert "What is the key idea about" not in output
    assert "How would you explain" in output
    assert "According to the selected source" not in output
    assert "React reconciliation uses keys" in output
    assert "Kubernetes" not in output


def main():
    tmp_root = Path.cwd() / ".test_tmp" / f"learning_agent_{uuid4().hex[:8]}"
    test_create_document_uses_default_title_in_document_and_chunks(tmp_root / "title")
    test_get_chunks_for_docs_filters_explicit_ids_by_user(tmp_root / "filter")
    test_search_chunks_respects_user_filter_for_selected_ids(tmp_root / "search")
    test_chunk_text_clamps_overlap_to_prevent_non_progress()
    test_delete_document_removes_document_and_chunks(tmp_root / "delete")
    test_url_normalization_accepts_plain_domains()
    test_url_normalization_extracts_share_links_from_pasted_titles()
    test_google_app_share_url_detection_accepts_plain_and_https_urls()
    test_devdocs_source_url_is_extracted_from_data_doc()
    test_url_loader_falls_back_when_fetch_is_blocked()
    test_github_repo_url_normalization_uses_repo_root_only()
    test_notebook_cells_are_indexed_as_repo_content()
    test_github_archive_extraction_reads_repo_files()
    test_chat_fallback_explains_without_echoing_question_or_dumping_excerpt()
    test_flashcard_fallback_uses_source_highlights()
    test_generate_flashcards_are_locked_to_selected_source(tmp_root / "flashcards")
    print("Learning agent checks passed")


if __name__ == "__main__":
    main()
