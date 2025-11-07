import uuid
import os
import traceback
import tempfile
import shutil

from fastapi import (
    APIRouter, UploadFile, File, Form, HTTPException,
    BackgroundTasks, Depends
)
from fastapi.responses import StreamingResponse

from chatbot.auth_utils import get_current_user_id
from chatbot.query_rag import (
    check_session_belongs_to_user,
    RAG_CHAIN_WITH_HISTORY,
    VISION_CHAIN_WITH_HISTORY,
    save_session_message,
    save_pdf_to_mongo,
    process_and_vectorize_pdf
)

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
    dependencies=[Depends(get_current_user_id)]  # Tất cả endpoint trong file này đều cần đăng nhập
)


@router.post("/text")
async def chat_text(question: str = Form(...), session_id: str = Form(...),
                    current_user_id: str = Depends(get_current_user_id)):
    """Endpoint chính để chat bằng văn bản, trả về stream."""
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if not check_session_belongs_to_user(session_id, current_user_id):
        raise HTTPException(status_code=403, detail="Access forbidden: Session does not belong to user")

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
            if question and full_response:
                save_session_message(session_id, current_user_id, question, full_response)

    return StreamingResponse(stream_response(), media_type="text/plain; charset=utf-8")


@router.post("/image")
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

    if not check_session_belongs_to_user(session_id, current_user_id):
        raise HTTPException(status_code=403, detail="Access forbidden: Session does not belong to user")

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
            if question and full_response:
                try:
                    save_session_message(session_id, current_user_id, question, full_response, image_path=image_path)
                except Exception as save_e:
                    print(f"Lỗi khi lưu message vào DB: {save_e}")

    def cleanup():
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temporary directory: {temp_dir}")

    background_tasks.add_task(cleanup)

    return StreamingResponse(stream_response(), media_type="text/plain; charset=utf-8")


@router.post("/upload_pdf")
async def chat_upload_pdf(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        session_id: str = Form(...),
        current_user_id: str = Depends(get_current_user_id)
):
    """Endpoint để tải lên file PDF và xử lý (vector hóa) trong nền."""
    if not check_session_belongs_to_user(session_id, current_user_id):
        raise HTTPException(status_code=403, detail="Access forbidden: Session does not belong to user")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    temp_dir = tempfile.mkdtemp()
    safe_filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(temp_dir, safe_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as ex:
        shutil.rmtree(temp_dir)
        raise HTTPException(status_code=500, detail=f"Failed to save temporary file: {str(ex)}")

    def process_in_background(path, s_id, u_id):
        """Hàm này sẽ được BackgroundTasks gọi sau khi API trả về."""
        try:
            print(f"BG Task: Saving PDF to Mongo for session {s_id}...")
            file_id = save_pdf_to_mongo(path, s_id, u_id)
            if file_id:
                print(f"BG Task: Vectorizing PDF {file.filename} for session {s_id}...")
                process_and_vectorize_pdf(path, s_id, u_id)
                print(f"BG Task: Processing complete for {file.filename}.")
            else:
                print(f"BG Task: Failed to save PDF to Mongo for {file.filename}.")
        except Exception as e:
            print(f"BG Task ERROR: Failed to process file {path}: {e}")
            traceback.print_exc()
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print(f"BG Task: Cleaned up temporary directory: {temp_dir}")

    background_tasks.add_task(process_in_background, file_path, session_id, current_user_id)

    return {
        "message": "File received and starting processing in background.",
        "filename": file.filename,
        "session_id": session_id
    }