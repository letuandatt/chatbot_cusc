import uuid
import os
import traceback
import tempfile  # Sử dụng thư mục tạm an toàn hơn
import shutil

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, status
from fastapi.responses import StreamingResponse  # <-- Quan trọng cho streaming
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from bson import ObjectId
from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr, constr

from chatbot.auth_utils import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user_id,
    TokenData
)


# --- 1. IMPORT CÁC THÀNH PHẦN ĐÃ KHỞI TẠO TỪ query_rag.py ---
# Import các hàm tiện ích và các chain đã được tạo sẵn

try:
    from chatbot.query_rag import (
        get_mongo_collection,
        list_sessions,
        load_session_messages,
        save_session_message,
        get_session_history,
        check_session_belongs_to_user,
        RAG_CHAIN_WITH_HISTORY,
        VISION_CHAIN_WITH_HISTORY,
        GLOBAL_RETRIEVER,
        TEXT_LLM,
        VISION_LLM,
        FS
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
    FS = None


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

# --- User model (for validation) ---
class UserCreate(BaseModel):
    email: EmailStr
    password: constr(min_length=8, max_length=64)

class UserInDB(BaseModel):
    email: EmailStr
    hashed_password: str
    created_at: datetime


# --- Rename Session Request Model ---
class RenameSessionRequest(BaseModel):
    new_name: str # Định nghĩa dữ liệu cần gửi lên: tên mới


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
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# --- Authentication Endpoints ---
@app.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user: UserCreate):
    """Register a new user."""
    users_coll = get_mongo_collection("users")
    if users_coll is None:
        raise HTTPException(status_code=503, detail="Failed to connect to MongoDB")

    existing_user = users_coll.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_password = get_password_hash(user.password)
    now = datetime.now(timezone.utc)
    new_user_data = {
        "email": user.email,
        "hashed_password": hashed_password,
        "created_at": now
    }
    try:
        result = users_coll.insert_one(new_user_data)
        return {"messages": "User registered successfully", "user_id": str(result.inserted_id)}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to register user: {str(ex)}")


@app.post("/token") # Standard OAuth2 endpoint name
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Logs in user and returns JWT token."""
    users_coll = get_mongo_collection("users")
    if users_coll is None:
        raise HTTPException(status_code=503, detail="User database not connected")

    user_doc = users_coll.find_one({"email": form_data.username}) # form uses 'username' for email
    if not user_doc or not verify_password(form_data.password, user_doc["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(user_doc["_id"]) # Get MongoDB ObjectId as string
    access_token = create_access_token(data={"sub": user_id}) # Store user_id in 'sub' claim
    return {"access_token": access_token, "token_type": "bearer"}


# --- Session Management Endpoints ---
# --- Create new session ---
@app.post("/session/new")
async def create_new_session(current_user_id: str = Depends(get_current_user_id)):
    session_id = str(uuid.uuid4().hex)
    sessions_coll = get_mongo_collection("sessions")
    if sessions_coll is None:
        raise HTTPException(status_code=503, detail="Failed to connect to MongoDB")

    now = datetime.now(timezone.utc).isoformat()
    default_name = f"Chat {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S')}"
    try:
        sessions_coll.insert_one({
            "session_id": session_id,
            "user_id": current_user_id,
            "session_name": default_name,
            "created_at": now,
            "updated_at": now,
            "messages": []
        })
        return {
            "session_id": session_id,
            "session_name": default_name,
            "message": "Session created successfully"}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(ex)}")


# --- Rename session ---
@app.put("/session/{session_id}/rename")
def rename_session(session_id: str, request: RenameSessionRequest, current_user_id: str = Depends(get_current_user_id)):
    """Đổi tên session NẾU nó thuộc về user hiện tại."""
    sessions_coll = get_mongo_collection("sessions")
    if sessions_coll is None:
        raise HTTPException(status_code=503, detail="Failed to connect to MongoDB")

    new_name = request.new_name.strip()

    if not new_name:
        raise HTTPException(status_code=400, detail="New session name cannot be empty")

    try:
        result = sessions_coll.update_one(
            {"session_id": session_id, "user_id": current_user_id},
            {"$set": {
                "session_name": new_name,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Session not found")

        return {"status": "renamed", "session_id": session_id, "new_name": new_name}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Error renaming session {session_id}: {str(ex)}")

# --- List sessions ---
@app.get("/sessions")
def get_sessions(current_user_id: str = Depends(get_current_user_id)):
    try:
        sessions = list_sessions(user_id=current_user_id, limit=50)
        return {"count": len(sessions), "sessions": sessions}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Error listing sessions: {str(ex)}")


# --- View a specific session ---
@app.get("/session/{session_id}")
def view_session(session_id: str, current_user_id: str = Depends(get_current_user_id)):
    """Xem lịch sử tin nhắn NẾU session thuộc về user hiện tại."""
    try:
        history = load_session_messages(session_id, user_id=current_user_id)
        if not history.messages and not check_session_belongs_to_user(session_id, current_user_id):
            raise HTTPException(status_code=404, detail="Session not found or does not belong to you")

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
def delete_session(session_id: str, current_user_id: str = Depends(get_current_user_id)):
    """Xóa session NẾU nó thuộc về user hiện tại."""
    sessions_coll = get_mongo_collection("sessions")
    if sessions_coll is None:
        raise HTTPException(status_code=503, detail="Failed to connect to MongoDB")

    try:
        result = sessions_coll.delete_one({"session_id": session_id, "user_id": current_user_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "deleted", "session_id": session_id}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Error deleting session {session_id}: {str(ex)}")

@app.delete("/sessions/all")
def delete_all_user_sessions(current_user_id: str = Depends(get_current_user_id)):
    """Xóa TẤT CẢ các session CỦA USER HIỆN TẠI khỏi MongoDB."""
    coll = get_mongo_collection("sessions")
    if coll is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    try:
        result = coll.delete_many({"user_id": current_user_id}) # Xóa tất cả document
        print(f"User {current_user_id} deleted {result.deleted_count} sessions.")
        return {"status": "deleted_user_sessions", "count": result.deleted_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

# --- Chat: text-only query ---
@app.post("/chat/text")
async def chat_text(question: str = Form(...), session_id: str = Form(...), current_user_id: str = Depends(get_current_user_id)):
    """Endpoint chính để chat bằng văn bản, trả về stream."""
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Verify session belongs to user BEFORE chatting
    if not check_session_belongs_to_user(session_id, current_user_id):
        raise HTTPException(status_code=403, detail="Access forbidden: Session does not belong to user")

    # Sử dụng chain RAG đã được khởi tạo toàn cục
    chain_to_run = RAG_CHAIN_WITH_HISTORY
    if chain_to_run is None:
        raise HTTPException(status_code=503, detail="RAG system is not available")

    async def stream_response():
        """Tạo generator để stream từng chunk câu trả lời."""
        full_response = ""
        config_ = {"configurable": {"session_id": session_id, "user_id": current_user_id}}
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
                save_session_message(session_id, current_user_id, question, full_response)

    return StreamingResponse(stream_response(), media_type="text/plain; charset=utf-8")


# --- Chat: text + image (multimodal) ---
@app.post("/chat/image")
async def chat_with_image(
    background_tasks: BackgroundTasks,
    question: str = Form(...),
    file: UploadFile = File(...),
    session_id: str = Form(...),
    current_user_id: str = Depends(get_current_user_id)
):
    """Endpoint chính để chat có ảnh, trả về stream."""
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Verify session belongs to user BEFORE chatting
    if not check_session_belongs_to_user(session_id, current_user_id):
        raise HTTPException(status_code=403, detail="Access forbidden: Session does not belong to user")

    # Sử dụng chain Vision đã được khởi tạo toàn cục
    chain_to_run = VISION_CHAIN_WITH_HISTORY
    if chain_to_run is None:
        raise HTTPException(status_code=503, detail="Vision system is not available")

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
        config_ = {"configurable": {"session_id": session_id, "user_id": current_user_id, "image_path": image_path}}
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
                    save_session_message(session_id, current_user_id, question, full_response, image_path=image_path)
                except Exception as save_e:
                    print(f"Lỗi khi lưu message vào DB: {save_e}")

    def cleanup():
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temporary directory: {temp_dir}")

    background_tasks.add_task(cleanup)

    return StreamingResponse(stream_response(), media_type="text/plain; charset=utf-8")

# --- Delete user ---
@app.delete("/user/me", status_code=status.HTTP_200_OK)
async def delete_current_user(current_user_id: str = Depends(get_current_user_id)):
    """Xoa tai khoan dang nhap cua user hien tai."""
    users_coll = get_mongo_collection("users")
    sessions_coll = get_mongo_collection("sessions")
    fs_client = FS
    
    if users_coll is None or sessions_coll is None or fs_client is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        user_delete_result = users_coll.delete_one({"_id": ObjectId(current_user_id)})
        if user_delete_result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="User not found")

        print(f"DEBUG: Deleted user document for user_id: {current_user_id}")

        session_delete_result = sessions_coll.delete_many({"user_id": current_user_id})
        print(f"DEBUG: Deleted {session_delete_result.deleted_count} sessions for user_id: {current_user_id}")

        return {"status": "deleted", "user_id": current_user_id, "sessions_deleted": session_delete_result.deleted_count}
    except Exception as ex:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error deleting user account: {ex}")


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