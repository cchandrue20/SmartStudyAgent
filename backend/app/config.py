from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    groq_api_key: str = ""
    gemini_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    gemini_model: str = "gemini-2.5-flash"
    mongodb_uri: str = ""
    chroma_persist_dir: str = "./data/chroma"
    mongodb_database: str = "smart_study_agent"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    retrieval_min_similarity: float = 0.2
    tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    class Config:
        env_file = ".env"


settings = Settings()
