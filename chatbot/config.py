import os
from dotenv import load_dotenv
from pathlib import Path


current_dir = Path(__file__).parent.resolve()
env_path = current_dir / ".env"

load_dotenv(dotenv_path=env_path, verbose=True)
print(f"Attempting to load .env from: {env_path}")

# --- API KEYS ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY")

# --- LLM MODELS ---
TEXT_MODEL_NAME = "gemini-2.5-flash"
VISION_MODEL_NAME = "gemini-2.5-flash"
EMBEDDING_MODEL_NAME = "models/text-embedding-004"
RERANK_MODEL_NAME = "rerank-multilingual-v3.0"
LLAMA_PARSE_MODEL = "anthropic-sonnet-4.5"

# --- DATABASE ---
VECTORSTORE_PATH = str(current_dir / "vectorstores" / "chroma_db_2")
print(f"Using absolute VECTORSTORE_PATH: {VECTORSTORE_PATH}")
COLLECTION_NAME = "docs_cusc"

# --- RAG PARAMS ---
RAG_RETRIEVER_K = 40
RAG_RERANKER_TOP_N = 6

# --- PARSING ---
PARSE_DATA_DIR = str(current_dir / "data")
PARSE_SAVE_DIR = str(current_dir / "data" / "after_parse")

# --- MONGODB ---
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = "Chatbot_CUSC"
