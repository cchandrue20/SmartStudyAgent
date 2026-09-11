import io
import re
from typing import Dict, List

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from pypdf import PdfReader

from app.config import settings

pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

# Common watermark/boilerplate lines injected by document-sharing sites (Studocu etc.)
# that are technically "extractable text" but carry no study content. Left in, these
# dominate retrieval on scanned notes where the real content never made it into the
# text layer at all.
_BOILERPLATE_PATTERNS = [
    re.compile(r"Downloaded by .+\(.+@.+\)", re.IGNORECASE),
    re.compile(r"lOMoARcPSD\s*\|?\s*\d+"),
    re.compile(r"Scan to open on Studocu", re.IGNORECASE),
    re.compile(r"Studocu is not sponsored or endorsed by any college or university", re.IGNORECASE),
]

# A page that has less than this many characters left after stripping boilerplate is
# treated as having no real content in its text layer, and falls back to OCR.
MIN_PAGE_CHARS = 40
OCR_DPI = 250


def _strip_boilerplate(text: str) -> str:
    lines = text.split("\n")
    kept = [line for line in lines if not any(pattern.search(line) for pattern in _BOILERPLATE_PATTERNS)]
    return "\n".join(kept).strip()


def _ocr_page(doc: "fitz.Document", page_index: int) -> str:
    """Render one PDF page to an image and run Tesseract on it. This is the fallback
    for scanned/image-only pages (e.g. phone-scanned notes) that have no text layer
    at all — pypdf's extract_text() returns nothing useful for these."""
    try:
        pixmap = doc[page_index].get_pixmap(dpi=OCR_DPI)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image)
    except Exception as exc:
        print(f"OCR failed on page {page_index + 1}: {exc}")
        return ""


def extract_pages(file_path: str) -> List[Dict]:
    reader = PdfReader(file_path)
    pages = []
    ocr_doc = None
    try:
        for i, page in enumerate(reader.pages):
            cleaned = _strip_boilerplate((page.extract_text() or "").strip())
            if len(cleaned) < MIN_PAGE_CHARS:
                if ocr_doc is None:
                    ocr_doc = fitz.open(file_path)
                ocr_text = _strip_boilerplate(_ocr_page(ocr_doc, i).strip())
                if len(ocr_text) > len(cleaned):
                    cleaned = ocr_text
            if len(cleaned) >= MIN_PAGE_CHARS:
                pages.append({"page": i + 1, "text": cleaned})
    finally:
        if ocr_doc is not None:
            ocr_doc.close()
    return pages


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> List[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    raw_chunks: List[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 1 <= chunk_size:
            current = f"{current}\n{para}".strip()
            continue

        if current:
            raw_chunks.append(current)

        if len(para) <= chunk_size:
            current = para
        else:
            start = 0
            while start < len(para):
                end = start + chunk_size
                raw_chunks.append(para[start:end])
                start = end - overlap
            current = ""

    if current:
        raw_chunks.append(current)

    if overlap and len(raw_chunks) > 1:
        overlapped = [raw_chunks[0]]
        for i in range(1, len(raw_chunks)):
            prev_tail = raw_chunks[i - 1][-overlap:]
            overlapped.append(f"{prev_tail}\n{raw_chunks[i]}")
        return overlapped

    return raw_chunks


def load_and_chunk_pdf(file_path: str, chunk_size: int = 1200, overlap: int = 150) -> List[Dict]:
    pages = extract_pages(file_path)
    chunks: List[Dict] = []
    for page in pages:
        for chunk in chunk_text(page["text"], chunk_size, overlap):
            chunks.append({"text": chunk, "page": page["page"]})
    return chunks
