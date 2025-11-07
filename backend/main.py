from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

# Import các thành phần RAG (giữ nguyên)
try:
    from chatbot.query_rag import (
        get_mongo_collection,
        GLOBAL_RETRIEVER,
        TEXT_LLM,
        VISION_LLM
    )
    print(f"RAG pipeline components initialized successfully.")
except Exception as e:
    print(f"Failed to initialize RAG pipeline: {e}")
    GLOBAL_RETRIEVER = None
    TEXT_LLM = None
    VISION_LLM = None

# Import config (chứa VN_TZ)
from backend.config import VN_TZ

# Import các routers
from backend.routers import auth, user, sessions, chat

app = FastAPI(
    title="RAG API Service",
    description="FastAPI backend for RAG-based AI assistant",
    version="1.0.0"
)

# --- Allow CORS for Vue or Postman ---
app.add_middleware(
    CORSMiddleware,
    # QUAN TRỌNG: Thay đổi "*" bằng domain frontend của bạn khi lên production
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Include Routers ---
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(sessions.router)
app.include_router(chat.router)


# --- Health check ---
@app.get("/health")
def health_check():
    """Kiểm tra trạng thái kết nối MongoDB và các thành phần AI."""
    mongo_ok = False
    try:
        coll = get_mongo_collection()
        if coll is not None:
            coll.database.client.admin.command("ping")
            mongo_ok = True
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        mongo_ok = False

    rag_pipeline_ok = GLOBAL_RETRIEVER is not None
    text_llm_ok = TEXT_LLM is not None
    vision_llm_ok = VISION_LLM is not None

    status_ = "ok" if mongo_ok and rag_pipeline_ok and text_llm_ok and vision_llm_ok else "not ok"

    return {
        "status": status_,
        "components": {
            "mongo": mongo_ok,
            "rag_pipeline": rag_pipeline_ok,
            "text_llm": text_llm_ok,
            "vision_llm": vision_llm_ok
        },
        "timestamp": datetime.now(VN_TZ).isoformat()
    }

# --- Root ---
@app.get("/")
def index():
    """Endpoint gốc, trả về thông tin cơ bản về API."""
    return {
        "service": "RAG API Backend",
        "description": "API backend cho trợ lý AI dựa trên RAG tại CUSC.",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "health_check": "/health"
    }