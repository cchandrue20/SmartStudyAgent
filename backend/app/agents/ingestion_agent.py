import uuid
from pathlib import Path
from typing import Dict

from app.services.llm import answer_with_context
from app.services.materials_store import materials_store
from app.services.pdf_loader import chunk_text, load_and_chunk_pdf
from app.services.vector_store import vector_store

DEFAULT_COLLECTION = "study_material"


def ingest_pdf(file_path: str, collection: str = DEFAULT_COLLECTION, source_name: str | None = None) -> Dict:
    document_id = str(uuid.uuid4())
    chunks = load_and_chunk_pdf(file_path)
    if not chunks:
        raise ValueError(
            "No usable text could be found in this PDF, even after OCR. It may be blank, "
            "corrupted, or too low-quality to read — try a clearer scan or paste the notes instead."
        )
    count = vector_store.add_chunks(collection, document_id, chunks)
    source = source_name or Path(file_path).name
    material = materials_store.save(
        {
            "document_id": document_id,
            "source": source,
            "collection": collection,
            "chunk_count": count,
            "source_type": "pdf",
        }
    )
    return {
        "document_id": document_id,
        "chunks_ingested": count,
        "source": source,
        "collection": collection,
        "created_at": material["created_at"],
    }


def ingest_text(text: str, source_name: str = "pasted-notes", collection: str = DEFAULT_COLLECTION) -> Dict:
    """Ingest pasted notes using the same local embedding pipeline as PDFs."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Notes cannot be empty.")
    document_id = str(uuid.uuid4())
    chunks = [{"text": chunk, "page": 0} for chunk in chunk_text(cleaned)]
    count = vector_store.add_chunks(collection, document_id, chunks)
    material = materials_store.save(
        {
            "document_id": document_id,
            "source": source_name,
            "collection": collection,
            "chunk_count": count,
            "source_type": "notes",
        }
    )
    return {
        "document_id": document_id,
        "chunks_ingested": count,
        "source": source_name,
        "collection": collection,
        "created_at": material["created_at"],
    }


def delete_material(document_id: str) -> Dict:
    material = materials_store.get(document_id)
    if not material:
        raise ValueError("No material found with that document_id.")
    vector_store.delete_document(material["collection"], document_id)
    materials_store.delete(document_id)
    return {"deleted": document_id}


def ask_question(question: str, collection: str = DEFAULT_COLLECTION, top_k: int = 5) -> Dict:
    matches = vector_store.query(collection, question, top_k=top_k)
    if not matches:
        return {
            "answer": "I couldn't find anything relevant enough in your uploaded material to "
            "answer this confidently. Try rephrasing, or upload material that covers this topic.",
            "sources": [],
        }

    answer = answer_with_context(question, matches)
    sources = []
    for match in matches:
        material = materials_store.get(match["metadata"].get("document_id"))
        sources.append(
            {
                "document_id": match["metadata"].get("document_id"),
                "source": material["source"] if material else "Unknown",
                "page": match["metadata"].get("page"),
                "excerpt": match["text"][:220].strip(),
                "relevance": round(match["similarity"], 3),
            }
        )
    return {"answer": answer, "sources": sources}
