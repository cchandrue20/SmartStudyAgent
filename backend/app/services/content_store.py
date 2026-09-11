"""Persists generated study aids (summaries/flashcards/quizzes) so students can
revisit them instead of regenerating, and so the same request replays the saved
result instead of calling the LLM again — the cache that protects a live demo
from free-tier rate limits, built from the same persistence the feature needs."""
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.config import settings


def cache_key(collection: str, content_type: str, document_id: Optional[str], topic: str, count: int) -> str:
    raw = f"{collection}|{content_type}|{document_id or ''}|{topic.strip().lower()}|{count}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class ContentStore:
    def __init__(self):
        self._memory: Dict[str, Dict] = {}
        self._db = None
        if settings.mongodb_uri:
            try:
                from pymongo import MongoClient

                client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)
                client.admin.command("ping")
                self._db = client[settings.mongodb_database]
            except Exception as exc:
                print(f"MongoDB unavailable; using temporary in-memory content store ({exc}).")

    def get_by_key(self, key: str) -> Optional[Dict]:
        if self._db is not None:
            return self._db.generated_content.find_one({"cache_key": key}, {"_id": 0})
        return self._memory.get(key)

    def save(self, key: str, record: Dict) -> Dict:
        record = {
            **record,
            "content_id": str(uuid.uuid4()),
            "cache_key": key,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if self._db is not None:
            self._db.generated_content.insert_one(record.copy())
        else:
            self._memory[key] = record
        return record

    def list(self, collection: Optional[str] = None, content_type: Optional[str] = None) -> List[Dict]:
        if self._db is not None:
            query = {}
            if collection:
                query["collection"] = collection
            if content_type:
                query["content_type"] = content_type
            return list(self._db.generated_content.find(query, {"_id": 0}).sort("created_at", -1))
        items = list(self._memory.values())
        if collection:
            items = [item for item in items if item["collection"] == collection]
        if content_type:
            items = [item for item in items if item["content_type"] == content_type]
        return sorted(items, key=lambda item: item["created_at"], reverse=True)


content_store = ContentStore()
