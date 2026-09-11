"""Material metadata repository (uploaded PDFs / pasted notes), with an
in-memory development fallback so the app still runs without MongoDB."""
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.config import settings


class MaterialsStore:
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
                print(f"MongoDB unavailable; using temporary in-memory materials store ({exc}).")

    def save(self, record: Dict) -> Dict:
        record = {**record, "created_at": datetime.now(timezone.utc).isoformat()}
        if self._db is not None:
            self._db.materials.insert_one(record.copy())
        else:
            self._memory[record["document_id"]] = record
        return record

    def list(self, collection: Optional[str] = None) -> List[Dict]:
        if self._db is not None:
            query = {"collection": collection} if collection else {}
            return list(self._db.materials.find(query, {"_id": 0}).sort("created_at", -1))
        items = list(self._memory.values())
        if collection:
            items = [item for item in items if item["collection"] == collection]
        return sorted(items, key=lambda item: item["created_at"], reverse=True)

    def get(self, document_id: str) -> Optional[Dict]:
        if self._db is not None:
            return self._db.materials.find_one({"document_id": document_id}, {"_id": 0})
        return self._memory.get(document_id)

    def delete(self, document_id: str) -> bool:
        if self._db is not None:
            return self._db.materials.delete_one({"document_id": document_id}).deleted_count > 0
        return self._memory.pop(document_id, None) is not None

    def collections(self) -> List[str]:
        if self._db is not None:
            return sorted(self._db.materials.distinct("collection"))
        return sorted({item["collection"] for item in self._memory.values()})


materials_store = MaterialsStore()
