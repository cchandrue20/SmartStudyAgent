import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agents.content_agent import generate_content
from app.agents.ingestion_agent import DEFAULT_COLLECTION, ask_question, delete_material, ingest_pdf, ingest_text
from app.agents.progress_agent import dashboard_summary, record_attempt, record_flashcard_review, study_plan
from app.config import settings
from app.services.content_store import content_store
from app.services.materials_store import materials_store

app = FastAPI(title="Smart Study Generator Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


class NotesRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    source_name: str = "pasted-notes"
    collection: str = DEFAULT_COLLECTION


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    collection: str = DEFAULT_COLLECTION
    top_k: int = Field(default=5, ge=1, le=12)


class GenerateRequest(BaseModel):
    content_type: str
    collection: str = DEFAULT_COLLECTION
    document_id: str | None = None
    topic: str = ""
    count: int = Field(default=5, ge=1, le=15)


class QuizAttemptRequest(BaseModel):
    student_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    answers: list[int]
    correct_answers: list[int]


class FlashcardReviewRequest(BaseModel):
    student_id: str = Field(min_length=1)
    card_key: str = Field(min_length=1)
    known: bool


def _http_error(exc: Exception) -> HTTPException:
    return HTTPException(422 if isinstance(exc, ValueError) else 503, str(exc))


@app.post("/api/materials/pdf", status_code=201)
async def ingest_pdf_endpoint(file: UploadFile = File(...), collection: str = Form(DEFAULT_COLLECTION)):
    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")
    suffix = Path(file.filename or "document.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        return ingest_pdf(tmp_path, collection=collection, source_name=file.filename)
    except Exception as exc:
        raise _http_error(exc) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/api/materials/notes", status_code=201)
async def ingest_notes_endpoint(payload: NotesRequest):
    try:
        return ingest_text(payload.text, payload.source_name, payload.collection)
    except Exception as exc:
        raise _http_error(exc) from exc


@app.post("/api/study/ask")
async def ask_endpoint(payload: AskRequest):
    try:
        return ask_question(payload.question, payload.collection, payload.top_k)
    except Exception as exc:
        raise _http_error(exc) from exc


@app.post("/api/study/generate")
async def generate_endpoint(payload: GenerateRequest):
    try:
        return generate_content(**payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@app.get("/api/materials")
async def list_materials_endpoint(collection: str | None = None):
    return {"materials": materials_store.list(collection)}


@app.get("/api/materials/collections")
async def list_collections_endpoint():
    return {"collections": materials_store.collections()}


@app.delete("/api/materials/{document_id}")
async def delete_material_endpoint(document_id: str):
    try:
        return delete_material(document_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@app.get("/api/study/generated")
async def list_generated_endpoint(collection: str = DEFAULT_COLLECTION, content_type: str | None = None):
    return {"items": content_store.list(collection, content_type)}


@app.post("/api/progress/attempts", status_code=201)
async def record_attempt_endpoint(payload: QuizAttemptRequest):
    try:
        return record_attempt(**payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@app.post("/api/progress/flashcards", status_code=201)
async def record_flashcard_review_endpoint(payload: FlashcardReviewRequest):
    try:
        return record_flashcard_review(**payload.model_dump())
    except Exception as exc:
        raise _http_error(exc) from exc


@app.get("/api/progress/{student_id}/plan")
async def plan_endpoint(student_id: str):
    return study_plan(student_id)


@app.get("/api/progress/{student_id}/summary")
async def summary_endpoint(student_id: str):
    return dashboard_summary(student_id)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "smart-study-generator"}
