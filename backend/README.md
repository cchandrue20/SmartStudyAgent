# Smart Study Generator — Backend

FastAPI backend for the deterministic three-agent study pipeline. The frontend selects the endpoint (rather than asking an LLM to route): material ingestion and Q&A, content generation, or progress planning.

## Start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the generated API reference.

### OCR

Scanned/image-only PDF pages (no text layer) are run through Tesseract OCR automatically during ingestion. Install the engine once with `winget install --id UB-Mannheim.TesseractOCR -e`, or set `TESSERACT_CMD` in `.env` if it's installed somewhere other than the default `C:\Program Files\Tesseract-OCR\tesseract.exe`. If Tesseract isn't found, pages with no text layer are simply skipped rather than the request failing.

## Frontend API map

| UI action | API endpoint |
| --- | --- |
| Upload a PDF | `POST /api/materials/pdf` (multipart: `file`, optional `collection`) |
| Save pasted notes | `POST /api/materials/notes` |
| List indexed documents | `GET /api/materials?collection=...` |
| List subject/course collections | `GET /api/materials/collections` |
| Delete a document | `DELETE /api/materials/{document_id}` |
| Ask material Q&A | `POST /api/study/ask` |
| Generate summary, flashcards, or quiz | `POST /api/study/generate` |
| List previously generated study aids | `GET /api/study/generated?collection=...&content_type=...` |
| Submit a completed quiz | `POST /api/progress/attempts` |
| Mark a flashcard known / still learning | `POST /api/progress/flashcards` |
| Load study plan / weak topics | `GET /api/progress/{student_id}/plan` |
| Load live dashboard metrics | `GET /api/progress/{student_id}/summary` |

The quiz response includes answer indexes in `correct_answer`; keep them client-side until submission, then send the student's `answers` and `correct_answers` arrays to score the attempt.

## Storage

- **ChromaDB** (local, `CHROMA_PERSIST_DIR`) — chunk embeddings, one collection per subject/course, cosine similarity with a configurable relevance floor (`RETRIEVAL_MIN_SIMILARITY`).
- **MongoDB Atlas** (`MONGODB_URI`) — quiz attempts, flashcard reviews, material metadata, and generated content. Each falls back independently to in-memory storage for local development if `MONGODB_URI` is unset or unreachable, so the app still runs without it — just without persistence across restarts.

## Content caching

`POST /api/study/generate` hashes its inputs (collection, content type, document/topic, count) and checks MongoDB before calling an LLM. An identical request replays the saved result (`cached: true` in the response) instead of generating again — this is what lets a demo re-run safely without burning free-tier rate limits, and lets a student revisit a study set instead of regenerating it.
