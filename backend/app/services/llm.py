"""Provider wrapper: Groq first, with Gemini as the fallback."""
from typing import Dict, List

from google import genai
from google.genai import types
from groq import Groq

from app.config import settings

_groq_client = Groq(api_key=settings.groq_api_key) if settings.groq_api_key else None
_gemini_client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None

GROQ_MODEL = settings.groq_model
GEMINI_MODEL = settings.gemini_model
SYSTEM_PROMPT = (
    "You are a study assistant. Answer the student's question using only the "
    "provided context from their own notes/textbook. If the context does not "
    "contain the answer, say you don't have enough information instead of guessing."
)


def _build_prompt(question: str, context_chunks: List[Dict]) -> str:
    context = "\n\n".join(
        f"[Source: page {chunk['metadata'].get('page', '?')}]\n{chunk['text']}"
        for chunk in context_chunks
    )
    return f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer based only on the context above."


def _gemini_chat(prompt: str, config: types.GenerateContentConfig) -> str:
    """Use Chat API to avoid the SDK's direct automatic-function-call warning."""
    if not _gemini_client:
        raise RuntimeError("Gemini is not configured.")
    chat = _gemini_client.chats.create(model=GEMINI_MODEL, config=config)
    response = chat.send_message(prompt)
    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")
    return response.text


def _provider_failure(groq_error: Exception | None, gemini_error: Exception) -> RuntimeError:
    if groq_error:
        return RuntimeError(f"Both LLM providers failed. Groq: {groq_error}; Gemini: {gemini_error}")
    return RuntimeError(f"Gemini request failed: {gemini_error}")


def answer_with_context(question: str, context_chunks: List[Dict]) -> str:
    if not context_chunks:
        return "I couldn't find anything relevant in your uploaded material for this question."
    prompt = _build_prompt(question, context_chunks)
    groq_error = None
    if _groq_client:
        try:
            response = _groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            return response.choices[0].message.content
        except Exception as exc:
            groq_error = exc
            print(f"Groq call failed ({exc}); falling back to Gemini.")
    if _gemini_client:
        try:
            return _gemini_chat(prompt, types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0.2))
        except Exception as exc:
            print(f"Gemini call failed ({exc}).")
            raise _provider_failure(groq_error, exc) from exc
    if groq_error:
        raise RuntimeError(f"Groq request failed: {groq_error}") from groq_error
    raise RuntimeError("No LLM provider configured. Set GROQ_API_KEY or GEMINI_API_KEY.")


def generate_structured_content(prompt: str) -> str:
    """Generate valid JSON study content with a supported provider."""
    groq_error = None
    if _groq_client:
        try:
            response = _groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You generate study aids from supplied material only. Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            groq_error = exc
            print(f"Groq call failed ({exc}); falling back to Gemini.")
    if _gemini_client:
        try:
            return _gemini_chat(
                prompt,
                types.GenerateContentConfig(temperature=0.2, response_mime_type="application/json"),
            ).strip()
        except Exception as exc:
            print(f"Gemini call failed ({exc}).")
            raise _provider_failure(groq_error, exc) from exc
    if groq_error:
        raise RuntimeError(f"Groq request failed: {groq_error}") from groq_error
    raise RuntimeError("No LLM provider configured. Set GROQ_API_KEY or GEMINI_API_KEY.")
