"""Progress and planning agent. All scoring is deterministic; no LLM call is needed."""
from collections import defaultdict
from datetime import date
from typing import Dict, List

from app.services.progress_store import progress_store


def _study_streak(timestamps: List[str]) -> int:
    """Consecutive days (ending today, UTC) with at least one quiz attempt or flashcard review."""
    days = sorted({ts[:10] for ts in timestamps}, reverse=True)
    streak = 0
    expected = date.today()
    for day_str in days:
        day = date.fromisoformat(day_str)
        if day == expected:
            streak += 1
            expected = date.fromordinal(expected.toordinal() - 1)
        elif day < expected:
            break
    return streak


def record_attempt(student_id: str, topic: str, answers: List[int], correct_answers: List[int]) -> Dict:
    if not student_id.strip() or not topic.strip():
        raise ValueError("student_id and topic are required.")
    if not correct_answers or len(answers) != len(correct_answers):
        raise ValueError("answers and correct_answers must be non-empty arrays of equal length.")
    correct = sum(a == b for a, b in zip(answers, correct_answers))
    score = round((correct / len(correct_answers)) * 100, 1)
    return progress_store.save_attempt({
        "student_id": student_id, "topic": topic.strip(), "score": score,
        "correct": correct, "total": len(correct_answers),
    })


def study_plan(student_id: str) -> Dict:
    attempts = progress_store.attempts_for(student_id)
    if not attempts:
        return {"student_id": student_id, "weak_topics": [], "recommendations": ["Take a quiz to start building your personalised study plan."], "attempts": 0}
    scores = defaultdict(list)
    for attempt in attempts:
        scores[attempt["topic"]].append(attempt["score"])
    topic_stats = [{"topic": topic, "average_score": round(sum(values) / len(values), 1), "attempts": len(values)} for topic, values in scores.items()]
    topic_stats.sort(key=lambda item: item["average_score"])
    weak = [item for item in topic_stats if item["average_score"] < 70]
    recommendations = [f"Review {item['topic']} first: your average is {item['average_score']}%." for item in (weak or topic_stats[:1])]
    recommendations.append("Use flashcards, then retake a quiz after a focused 25-minute study session.")
    return {"student_id": student_id, "weak_topics": weak, "topic_performance": topic_stats, "recommendations": recommendations, "attempts": len(attempts)}


def record_flashcard_review(student_id: str, card_key: str, known: bool) -> Dict:
    if not student_id.strip() or not card_key.strip():
        raise ValueError("student_id and card_key are required.")
    return progress_store.save_flashcard_review(
        {"student_id": student_id, "card_key": card_key, "known": known}
    )


def dashboard_summary(student_id: str) -> Dict:
    attempts = progress_store.attempts_for(student_id)
    reviews = progress_store.flashcard_reviews_for(student_id)
    aggregate_score = round(sum(a["score"] for a in attempts) / len(attempts), 1) if attempts else 0
    mastered = sum(1 for r in reviews if r.get("known"))
    streak = _study_streak([a["created_at"] for a in attempts] + [r["created_at"] for r in reviews])
    return {
        "student_id": student_id,
        "aggregate_score": aggregate_score,
        "quizzes_completed": len(attempts),
        "flashcards_reviewed": len(reviews),
        "flashcards_mastered": mastered,
        "study_streak_days": streak,
    }
