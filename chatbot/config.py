import os
from dotenv import load_dotenv

load_dotenv()

# --- API KEYS ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY")

# --- LLM MODELS ---
TEXT_MODEL_NAME = "gemini-2.5-pro"
VISION_MODEL_NAME = "gemini-2.5-pro"
EMBEDDING_MODEL_NAME = "models/text-embedding-004"
RERANK_MODEL_NAME = "rerank-multilingual-v3.0"
LLAMA_PARSE_MODEL = "anthropic-sonnet-4.5"

# --- DATABASE ---
VECTORSTORE_PATH = "vectorstores/chroma_db_2"
COLLECTION_NAME = "docs_cusc"

# --- RAG PARAMS ---
RAG_RETRIEVER_K = 40
RAG_RERANKER_TOP_N = 6

# --- PARSING ---
PARSE_DATA_DIR = "data"
PARSE_SAVE_DIR = "data/after_parse"

# --- MONGODB ---
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = "Chatbot_CUSC"
