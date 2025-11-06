import uuid
import os
import traceback
import tempfile
import shutil
import pytz

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from bson import ObjectId
from datetime import datetime, timezone
from pydantic import BaseModel, EmailStr, constr
from pymongo import DESCENDING

from chatbot.auth_utils import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user_id
)

# --- 1. IMPORT CÁC THÀNH PHẦN ĐÃ KHỞI TẠO ---
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
        FS,
        save_pdf_to_mongo,
        process_and_vectorize_pdf,
        delete_session_and_associated_files
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

# --- ĐỊNH NGHĨA MÚI GIỜ VIỆT NAM ---
try:
    VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
    print("VN_TZ initialized successfully.")
except pytz.UnknownTimeZoneError:
    print("VN_TZ not found, using UTC as default timezone.")
    VN_TZ = timezone.utc


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
    name: str
    email: EmailStr
    hashed_password: str
    created_at: datetime


class UserProfile(BaseModel):
    name: str
    email: EmailStr
    created_at: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: constr(min_length=8, max_length=64)


class ChageNameRequest(BaseModel):
    current_name: str
    new_name: str


# --- Rename Session Request Model ---
class RenameSessionRequest(BaseModel):
    new_name: str  # Định nghĩa dữ liệu cần gửi lên: tên mới


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
    now = datetime.now(VN_TZ).isoformat()
    new_user_data = {
        "name": user.email.split("@")[0],
        "email": user.email,
        "hashed_password": hashed_password,
        "created_at": now
    }
    try:
        result = users_coll.insert_one(new_user_data)
        return {"messages": "User registered successfully", "user_id": str(result.inserted_id)}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to register user: {str(ex)}")


@app.post("/token")  # Standard OAuth2 endpoint name
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Logs in user and returns JWT token."""
    users_coll = get_mongo_collection("users")
    if users_coll is None:
        raise HTTPException(status_code=503, detail="User database not connected")

    user_doc = users_coll.find_one({"email": form_data.username})  # form uses 'username' for email
    if not user_doc or not verify_password(form_data.password, user_doc["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(user_doc["_id"])  # Get MongoDB ObjectId as string
    access_token = create_access_token(data={"sub": user_id})  # Store user_id in 'sub' claim
    return {"access_token": access_token, "token_type": "bearer"}


# --- Session Management Endpoints ---
# --- Create new session ---
@app.post("/session/new")
async def create_new_session(current_user_id: str = Depends(get_current_user_id)):
    session_id = str(uuid.uuid4().hex)
    sessions_coll = get_mongo_collection("sessions")
    if sessions_coll is None:
        raise HTTPException(status_code=503, detail="Failed to connect to MongoDB")

    now = datetime.now(VN_TZ).isoformat()
    default_name = f"Chat {datetime.now(VN_TZ).strftime('%d/%m/%Y %H:%M:%S')}"
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
                "updated_at": datetime.now(VN_TZ).isoformat()
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
    """Xóa session VÀ TẤT CẢ CÁC FILE LIÊN QUAN (GridFS, Documents, Chroma)."""
    try:
        # Gọi hàm xóa mới từ query_rag.py
        delete_results = delete_session_and_associated_files(session_id, current_user_id)

        if delete_results["sessions"] == 0:
            raise HTTPException(status_code=404, detail="Session not found or does not belong to user")

        print(f"Cascade delete complete for session {session_id}: {delete_results}")

        return {
            "status": "deleted_with_files",
            "session_id": session_id,
            "details": delete_results
        }
    except Exception as ex:
        print(f"Error during cascade delete for session {session_id}: {ex}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error deleting session and associated files: {str(ex)}")


@app.delete("/sessions/all")
@app.delete("/sessions/all")
def delete_all_user_sessions(current_user_id: str = Depends(get_current_user_id)):
    """Xóa TẤT CẢ các session VÀ DỮ LIỆU LIÊN QUAN (PDF, Ảnh, Chunks) của user."""

    sessions_coll = get_mongo_collection("sessions")
    if sessions_coll is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    print(f"--- BẮT ĐẦU XÓA TẤT CẢ SESSION CHO USER: {current_user_id} ---")

    try:
        # 1. Tìm tất cả session_id của user này
        session_ids_to_delete = [
            s['session_id'] for s in sessions_coll.find(
                {"user_id": current_user_id},
                {"session_id": 1, "_id": 0}
            )
        ]

        if not session_ids_to_delete:
            print(f"User {current_user_id} không có session nào để xóa.")
            return {"status": "no_sessions_found", "count": 0}

        print(f"Tìm thấy {len(session_ids_to_delete)} session(s) cần xóa cascade...")

        total_deleted_count = 0

        # 2. Lặp qua từng session và gọi hàm xóa cascade
        for session_id in session_ids_to_delete:
            try:
                print(f"Đang xóa cascade cho session: {session_id}...")
                delete_results = delete_session_and_associated_files(session_id, current_user_id)
                if delete_results["sessions"] > 0:
                    total_deleted_count += 1
            except Exception as e_inner:
                print(f"Lỗi khi xóa cascade session {session_id}: {e_inner}")
                # Tiếp tục chạy dù có lỗi 1 session

        print(f"--- HOÀN TẤT XÓA TẤT CẢ SESSION. Đã xóa {total_deleted_count} session(s) ---")
        return {"status": "all_sessions_deleted_with_files", "count": total_deleted_count}

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi thực hiện delete_all_user_sessions: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


# --- Chat: text-only query ---
@app.post("/chat/text")
async def chat_text(question: str = Form(...), session_id: str = Form(...),
                    current_user_id: str = Depends(get_current_user_id)):
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

# --- Chat: upload PDF ---
@app.post("/chat/upload_pdf")
async def chat_upload_pdf(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        session_id: str = Form(...),
        current_user_id: str = Depends(get_current_user_id)
):
    """Endpoint để tải lên file PDF và xử lý (vector hóa) trong nền."""

    # 1. Xác thực session
    if not check_session_belongs_to_user(session_id, current_user_id):
        raise HTTPException(status_code=403, detail="Access forbidden: Session does not belong to user")

    # 2. Kiểm tra định dạng file
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # 3. Lưu file vào thư mục tạm
    temp_dir = tempfile.mkdtemp()
    safe_filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(temp_dir, safe_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as ex:
        shutil.rmtree(temp_dir)
        raise HTTPException(status_code=500, detail=f"Failed to save temporary file: {str(ex)}")

    # 4. Định nghĩa tác vụ chạy nền
    def process_in_background(path, s_id, u_id):
        """
        Hàm này sẽ được BackgroundTasks gọi sau khi API trả về.
        Nó sẽ lưu, vector hóa, và dọn dẹp file tạm.
        """
        try:
            print(f"BG Task: Saving PDF to Mongo for session {s_id}...")
            # Bước 4a: Lưu file vào Mongo (GridFS + 'documents' collection)
            file_id = save_pdf_to_mongo(path, s_id, u_id)

            if file_id:
                # Bước 4b: Phân tích và vector hóa file
                print(f"BG Task: Vectorizing PDF {file.filename} for session {s_id}...")
                process_and_vectorize_pdf(path, s_id, u_id)
                print(f"BG Task: Processing complete for {file.filename}.")
            else:
                print(f"BG Task: Failed to save PDF to Mongo for {file.filename}.")
        except Exception as e:
            print(f"BG Task ERROR: Failed to process file {path}: {e}")
            traceback.print_exc()
        finally:
            # Bước 4c: Dọn dẹp thư mục tạm
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print(f"BG Task: Cleaned up temporary directory: {temp_dir}")

    # 5. Thêm tác vụ vào hàng đợi
    background_tasks.add_task(process_in_background, file_path, session_id, current_user_id)

    # 6. Trả về thông báo ngay lập tức
    return {
        "message": "File received and starting processing in background.",
        "filename": file.filename,
        "session_id": session_id
    }

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

        return {"status": "deleted", "user_id": current_user_id,
                "sessions_deleted": session_delete_result.deleted_count}
    except Exception as ex:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error deleting user account: {ex}")


# --- Xem thong tin User ---
@app.get("/user/me", response_model=UserProfile)
async def read_users_me(current_user_id: str = Depends(get_current_user_id)):
    """
    Get information about the current user.
    """
    users_coll = get_mongo_collection("users")
    if users_coll is None:
        raise HTTPException(status_code=503, detail="Failed to connect to MongoDB")

    try:
        user_doc = users_coll.find_one({"_id": ObjectId(current_user_id)})
        if user_doc is None:
            raise HTTPException(status_code=404, detail="User not found")
        return UserProfile(
            name=user_doc["name"],
            email=user_doc["email"],
            created_at=user_doc["created_at"]
        )
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Error reading user account: {ex}")


# --- Change password ---
@app.put("/user/me/password", status_code=status.HTTP_200_OK)
async def change_current_user_password(
        request: ChangePasswordRequest,
        current_user_id: str = Depends(get_current_user_id)
):
    """Xác thực mật khẩu hiện tại và cập nhật mật khẩu mới cho người dùng."""
    users_coll = get_mongo_collection("users")
    if users_coll is None:
        raise HTTPException(status_code=503, detail="User database not connected")

    try:
        # 1. Lấy thông tin user hiện tại
        user_doc = users_coll.find_one({"_id": ObjectId(current_user_id)})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        # 2. Xác thực mật khẩu hiện tại
        if not verify_password(request.current_password, user_doc["hashed_password"]):
            raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")

        # 3. Băm mật khẩu mới
        new_hashed_password = get_password_hash(request.new_password)

        # 4. Cập nhật mật khẩu mới vào DB
        result = users_coll.update_one(
            {"_id": ObjectId(current_user_id)},
            {"$set": {"hashed_password": new_hashed_password}}
        )

        if result.modified_count == 1:
            print(f"DEBUG: Password updated successfully for user {current_user_id}")
            return {"message": "Mật khẩu đã được cập nhật thành công."}
        else:
            # Trường hợp hiếm gặp: không cập nhật được dù đã tìm thấy user
            raise HTTPException(status_code=500, detail="Không thể cập nhật mật khẩu.")

    except HTTPException as http_ex:
        raise http_ex  # Ném lại lỗi HTTP để FastAPI xử lý
    except Exception as e:
        print(f"Lỗi khi đổi mật khẩu user {current_user_id}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi máy chủ khi đổi mật khẩu.")


@app.put("/user/me/name", status_code=status.HTTP_200_OK)
async def change_current_user_name(
        request: ChageNameRequest,
        current_user_id: str = Depends(get_current_user_id)
):
    users_coll = get_mongo_collection("users")
    if users_coll is None:
        raise HTTPException(status_code=503, detail="User database not connected")

    try:
        user_doc = users_coll.find_one({"_id": ObjectId(current_user_id)})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        result = users_coll.update_one(
            {"_id": ObjectId(current_user_id)},
            {"$set": {"name": request.new_name}}
        )

        if result.modified_count == 1:
            # Nếu sửa thành công 1 dòng -> Trả về OK
            return {"message": "Đã cập nhật tên thành công"}
        elif result.modified_count == 0 and result.matched_count == 1:
            # Nếu tìm thấy user nhưng tên mới = tên cũ -> Vẫn trả về OK
            return {"message": "Tên không thay đổi (giống tên cũ)."}
        else:
            # Nếu không tìm thấy user (matched_count = 0)
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng để cập nhật.")
    except HTTPException as http_ex:
        raise http_ex  # Ném lại lỗi HTTP để FastAPI xử lý
    except Exception as e:
        print(f"Lỗi khi đổi tên user {current_user_id}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi máy chủ khi đổi tên user.")


# --- List documents ---
@app.get("/user/documents", status_code=status.HTTP_200_OK)
async def list_documents(current_user_id: str = Depends(get_current_user_id)):
    """Lấy danh sách file đã tải liên bởi user hiện tại"""
    docs_coll = get_mongo_collection("documents")
    if docs_coll is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    try:
        docs_cursor = docs_coll.find(
            {"user_id": current_user_id},
            {"_id": 0, "filename": 1, "created_at": 1, "session_id": 1, "status": 1, "gridfs_id": 1}
        ).sort("created_at", DESCENDING)

        documents = list(docs_cursor)
        return {"documents": documents, "count": len(documents)}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Error listing documents: {ex}")

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