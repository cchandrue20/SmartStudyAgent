"""Content generation agent: creates revision aids from retrieved student material."""
import json
from typing import Dict, List

from app.services.content_store import cache_key, content_store
from app.services.llm import generate_structured_content
from app.services.vector_store import vector_store


def _context(chunks: List[Dict]) -> str:
    return "\n\n".join(f"[Page {c['metadata'].get('page', '?')}]\n{c['text']}" for c in chunks)


def generate_content(content_type: str, collection: str, document_id: str | None = None, topic: str = "", count: int = 5) -> Dict:
    if content_type not in {"summary", "flashcards", "quiz"}:
        raise ValueError("content_type must be summary, flashcards, or quiz.")
    if not 1 <= count <= 15:
        raise ValueError("count must be between 1 and 15.")

    key = cache_key(collection, content_type, document_id, topic, count)
    cached = content_store.get_by_key(key)
    if cached:
        return {**cached, "cached": True}

    if document_id:
        chunks = vector_store.get_document_chunks(collection, document_id)
    elif topic.strip():
        chunks = vector_store.query(collection, topic, top_k=min(count + 3, 12))
    else:
        # No topic to match against — pull representative chunks from the whole
        # collection instead of running a (meaningless) empty-string similarity search.
        chunks = vector_store.get_collection_chunks(collection, limit=min(count + 3, 12))
    if not chunks:
        raise ValueError("No matching study material found. Upload material first or choose a valid document.")

    formats = {
        "summary": '{"title":"string","summary":"string","key_points":["string"],"topic":"string"}',
        "flashcards": '{"topic":"string","flashcards":[{"question":"string","answer":"string","source_page":1}]}',
        "quiz": '{"topic":"string","questions":[{"id":"q1","question":"string","options":["string","string","string","string"],"correct_answer":0,"explanation":"string","source_page":1}]}',
    }
    prompt = (
        f"Create exactly {count if content_type != 'summary' else 'one'} {content_type} from the material below. "
        f"Use only provided material. Return valid JSON only matching this shape: {formats[content_type]}.\n\nMaterial:\n{_context(chunks)}"
    )
    raw = generate_structured_content(prompt)
    try:
        content = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The language model returned invalid JSON. Please retry.") from exc

    result = {
        "content_type": content_type,
        "collection": collection,
        "document_id": document_id,
        "topic": topic,
        "content": content,
        "sources": sorted({c["metadata"].get("page", 0) for c in chunks}),
    }
    saved = content_store.save(key, result)
    return {**saved, "cached": False}
