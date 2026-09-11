from typing import Dict, List, Optional

import chromadb

from app.config import settings
from app.services.embeddings import embed_query, embed_texts


class VectorStore:
    def __init__(self, persist_dir: str | None = None):
        self._client = chromadb.PersistentClient(path=persist_dir or settings.chroma_persist_dir)

    def _collection(self, name: str):
        # Embeddings are normalized, so cosine distance maps cleanly to a 0-1
        # similarity score used for the relevance threshold in query().
        return self._client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

    def add_chunks(self, collection: str, document_id: str, chunks: List[Dict]) -> int:
        col = self._collection(collection)
        texts = [c["text"] for c in chunks]
        embeddings = embed_texts(texts)
        ids = [f"{document_id}::{i}" for i in range(len(chunks))]
        metadatas = [
            {"document_id": document_id, "page": c.get("page", 0), "chunk_index": i}
            for i, c in enumerate(chunks)
        ]
        col.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
        return len(chunks)

    def query(
        self, collection: str, question: str, top_k: int = 5, min_similarity: Optional[float] = None
    ) -> List[Dict]:
        col = self._collection(collection)
        if col.count() == 0:
            return []

        threshold = settings.retrieval_min_similarity if min_similarity is None else min_similarity
        query_embedding = embed_query(question)
        result = col.query(query_embeddings=[query_embedding], n_results=min(top_k, col.count()))

        matches = []
        for doc, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            similarity = max(0.0, 1 - dist)
            if similarity >= threshold:
                matches.append({"text": doc, "metadata": meta, "similarity": similarity})
        return matches

    def get_document_chunks(self, collection: str, document_id: str, limit: int = 12) -> List[Dict]:
        """Return chunks for generation, preserving their original order."""
        col = self._collection(collection)
        result = col.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
            limit=limit,
        )
        chunks = [
            {"text": doc, "metadata": meta}
            for doc, meta in zip(result["documents"], result["metadatas"])
        ]
        return sorted(chunks, key=lambda item: item["metadata"].get("chunk_index", 0))

    def get_collection_chunks(self, collection: str, limit: int = 12) -> List[Dict]:
        """Arbitrary chunks from across the whole collection, for generation requests
        with no topic/document filter (a similarity search against an empty topic
        string isn't meaningful, so this bypasses the relevance threshold entirely)."""
        col = self._collection(collection)
        if col.count() == 0:
            return []
        result = col.get(include=["documents", "metadatas"], limit=limit)
        return [{"text": doc, "metadata": meta} for doc, meta in zip(result["documents"], result["metadatas"])]

    def delete_document(self, collection: str, document_id: str) -> None:
        self._collection(collection).delete(where={"document_id": document_id})

    def delete_collection(self, collection: str) -> None:
        self._client.delete_collection(name=collection)


vector_store = VectorStore()
