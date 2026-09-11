"""MongoDB-backed progress repository with an in-memory development fallback."""
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from app.config import settings


class ProgressStore:
    def __init__(self):
        self._memory: Dict[str, List[Dict]] = defaultdict(list)
        self._flashcards: Dict[str, Dict] = {}
        self._db = None
        if settings.mongodb_uri:
            try:
                from pymongo import MongoClient

                client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)
                client.admin.command("ping")
                self._db = client[settings.mongodb_database]
            except Exception as exc:
                print(f"MongoDB unavailable; using temporary in-memory progress store ({exc}).")

    def save_attempt(self, attempt: Dict) -> Dict:
        record = {**attempt, "created_at": datetime.now(timezone.utc).isoformat()}
        if self._db is not None:
            self._db.quiz_attempts.insert_one(record.copy())
        else:
            self._memory[record["student_id"]].append(record)
        return record

    def attempts_for(self, student_id: str) -> List[Dict]:
        if self._db is not None:
            return list(self._db.quiz_attempts.find({"student_id": student_id}, {"_id": 0}).sort("created_at", -1))
        return list(reversed(self._memory[student_id]))

    def save_flashcard_review(self, record: Dict) -> Dict:
        record = {**record, "created_at": datetime.now(timezone.utc).isoformat()}
        if self._db is not None:
            self._db.flashcard_reviews.update_one(
                {"student_id": record["student_id"], "card_key": record["card_key"]},
                {"$set": record},
                upsert=True,
            )
        else:
            self._flashcards[f"{record['student_id']}::{record['card_key']}"] = record
        return record

    def flashcard_reviews_for(self, student_id: str) -> List[Dict]:
        if self._db is not None:
            return list(self._db.flashcard_reviews.find({"student_id": student_id}, {"_id": 0}))
        return [v for k, v in self._flashcards.items() if k.startswith(f"{student_id}::")]


progress_store = ProgressStore()
