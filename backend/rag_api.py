import uuid
import os
import traceback
import tempfile  # Sử dụng thư mục tạm an toàn hơn
import shutil

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse  # <-- Quan trọng cho streaming
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from typing import Optional


# --- 1. IMPORT CÁC THÀNH PHẦN ĐÃ KHỞI TẠO TỪ query_rag.py ---
# Import các hàm tiện ích và các chain đã được tạo sẵn

try:
    from chatbot.query_rag import (
        get_mongo_collection,
        list_sessions,
        load_session_messages,
        save_session_message,
        get_session_history,
        RAG_CHAIN_WITH_HISTORY,
        VISION_CHAIN_WITH_HISTORY,
        GLOBAL_RETRIEVER,
        TEXT_LLM,
        VISION_LLM,
        message_history_store
    )
    print(f"RAG pipeline components initialized successfully.")
except Exception as e:
    print(f"Failed to initialize RAG pipeline: {e}")
    RAG_CHAIN_WITH_HISTORY = None
    VISION_CHAIN_WITH_HISTORY = None
    GLOBAL_RETRIEVER = None
    TEXT_LLM = None
    VISION_LLM = None
    message_history_store = None


app = FastAPI(
    title="RAG API Service",
    description="FastAPI backend for RAG-based AI assistant",
    version="1.0.0"
)

# --- Allow CORS for Vue or Postman ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to your frontend domain for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Health check ---
@app.get("/health")
def health_check():
    """Kiểm tra trạng thái kết nối MongoDB và các thành phần AI."""
    mongo_ok = False
    try:
        coll = get_mongo_collection()
        if coll:
            coll.database.client.admin.command("ping")
            mongo_ok = True
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        mongo_ok = False

    rag_pipeline_ok = GLOBAL_RETRIEVER is not None
    text_llm_ok = TEXT_LLM is not None
    vision_llm_ok = VISION_LLM is not None

    status = "ok" if mongo_ok and rag_pipeline_ok and text_llm_ok and vision_llm_ok else "not ok"

    return {
        "status": status,
        "components": {
            "mongo": mongo_ok,
            "rag_pipeline": rag_pipeline_ok,
            "text_llm": text_llm_ok,
            "vision_llm": vision_llm_ok
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# --- Session Management Endpoints ---
# --- Create new session ---
@app.post("/session/new")
def create_new_session():
    session_id = str(uuid.uuid4().hex)
    coll = get_mongo_collection()
    if coll is None:
        raise HTTPException(status_code=503, detail="Failed to connect to MongoDB")

    now = datetime.now(timezone.utc).isoformat()
    try:
        coll.insert_one({
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "messages": []
        })
        return {"session_id": session_id, "message": "Session created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


# --- List sessions ---
@app.get("/sessions")
def get_sessions():
    try:
        sessions = list_sessions(limit=50)
        return {"count": len(sessions), "sessions": sessions}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Error listing sessions: {str(ex)}")


# --- View a specific session ---
@app.get("/session/{session_id}")
def view_session(session_id: str):
    """Xem lịch sử tin nhắn của một session cụ thể."""
    try:
        history = load_session_messages(session_id)
        messages = []
        for msg in history.messages:
            role = "user" if msg.type == "human" else "assistant"
            content = msg.content
            messages.append({"role": role, "content": content})
        return {"session_id": session_id, "messages": messages}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Error loading session {session_id}: {str(ex)}")


# --- Delete session ---
@app.delete("/session/{session_id}/delete")
def delete_session(session_id: str):
    """Xóa một session khỏi MongoDB."""
    coll = get_mongo_collection()
    if coll is None:
        raise HTTPException(status_code=503, detail="Failed to connect to MongoDB")

    try:
        result = coll.delete_one({"session_id": session_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Session not found")
        if session_id in message_history_store:
            del message_history_store[session_id]
        return {"status": "deleted", "session_id": session_id}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Error deleting session {session_id}: {str(ex)}")


# --- Chat: text-only query ---
@app.post("/chat/text")
async def chat_text(question: str = Form(...), session_id: Optional[str] = Form(None)):
    """Endpoint chính để chat bằng văn bản, trả về stream."""
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Sử dụng chain RAG đã được khởi tạo toàn cục
    chain_to_run = RAG_CHAIN_WITH_HISTORY
    if chain_to_run is None:
        raise HTTPException(status_code=503, detail="RAG system is not available")

    session_id = session_id or str(uuid.uuid4().hex)

    async def stream_response():
        """Tạo generator để stream từng chunk câu trả lời."""
        full_response = ""
        config_ = {"configurable": {"session_id": session_id}}
        input_data = {"question": question}

        try:
            for chunk in chain_to_run.stream(input_data, config=config_):
                full_response += chunk
                yield chunk
        except Exception as ex:
            traceback.print_exc()
            yield f"\n\n--- Lỗi Server ---:\n{str(ex)}"
        finally:
            # Lưu tin nhắn vào DB sau khi stream xong (kể cả khi có lỗi)
            # Lưu ý: full_response có thể chứa thông báo lỗi
            if question and full_response:  # Chỉ lưu nếu có câu hỏi và câu trả lời (hoặc lỗi)
                save_session_message(session_id, question, full_response)

    return StreamingResponse(stream_response(), media_type="text/plain; charset=utf-8")


# --- Chat: text + image (multimodal) ---
@app.post("/chat/image")
async def chat_with_image(
    background_tasks: BackgroundTasks,
    question: str = Form(...),
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None)
):
    """Endpoint chính để chat có ảnh, trả về stream."""
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Sử dụng chain Vision đã được khởi tạo toàn cục
    chain_to_run = VISION_CHAIN_WITH_HISTORY
    if chain_to_run is None:
        raise HTTPException(status_code=503, detail="Vision system is not available")

    session_id = session_id or str(uuid.uuid4().hex)

    temp_dir = tempfile.mkdtemp()
    safe_filename = f"{uuid.uuid4().hex}_{file.filename}"
    image_path = os.path.join(temp_dir, safe_filename)

    try:
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as ex:
        shutil.rmtree(temp_dir)
        raise HTTPException(status_code=500, detail=f"Failed to save image: {str(ex)}")

    async def stream_response():
        """Tạo generator để stream từng chunk câu trả lời."""
        full_response = ""
        config_ = {"configurable": {"session_id": session_id}}
        input_data = {"question": question, "image_path": image_path}

        try:
            for chunk in chain_to_run.stream(input_data, config=config_):
                content = chunk.content
                full_response += content
                yield content
        except Exception as ex:
            traceback.print_exc()
            yield f"\n\n--- Lỗi Server ---:\n{str(ex)}"
        finally:
            # Lưu vào DB sau khi stream xong
            if question and full_response:
                try:
                    # Quan trọng: save_session_message cũng đọc image_path
                    save_session_message(session_id, question, full_response, image_path=image_path)
                except Exception as save_e:
                    print(f"Lỗi khi lưu message vào DB: {save_e}")

    def cleanup():
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temporary directory: {temp_dir}")

    background_tasks.add_task(cleanup)

    return StreamingResponse(stream_response(), media_type="text/plain; charset=utf-8")


# --- Root ---
@app.get("/")
def index():
    """Endpoint gốc, trả về thông tin cơ bản về API."""
    return {
        "service": "RAG API Backend",
        "description": "API backend cho trợ lý AI dựa trên RAG tại CUSC.",
        "docs_url": "/docs",  # Link tới tài liệu Swagger UI tự động
        "redoc_url": "/redoc",  # Link tới tài liệu ReDoc tự động
        "health_check": "/health"
        # run on: http://127.0.0.1:8000/docs#/
    }
