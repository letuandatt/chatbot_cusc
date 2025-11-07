import uuid
import traceback
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime

from chatbot.auth_utils import get_current_user_id
from chatbot.query_rag import (
    get_mongo_collection,
    list_sessions,
    load_session_messages,
    check_session_belongs_to_user,
    delete_session_and_associated_files
)
from backend.models import RenameSessionRequest
from backend.config import VN_TZ

router = APIRouter(
    tags=["Session Management"],
    dependencies=[Depends(get_current_user_id)] # Tất cả endpoint trong file này đều cần đăng nhập
)

@router.post("/session/new")
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


@router.put("/session/{session_id}/rename")
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


@router.get("/sessions")
def get_sessions(current_user_id: str = Depends(get_current_user_id)):
    try:
        sessions = list_sessions(user_id=current_user_id, limit=50)
        return {"count": len(sessions), "sessions": sessions}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Error listing sessions: {str(ex)}")


@router.get("/session/{session_id}")
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


@router.delete("/session/{session_id}/delete")
def delete_session(session_id: str, current_user_id: str = Depends(get_current_user_id)):
    """Xóa session VÀ TẤT CẢ CÁC FILE LIÊN QUAN (GridFS, Documents, Chroma)."""
    try:
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


@router.delete("/sessions/all")
def delete_all_user_sessions(current_user_id: str = Depends(get_current_user_id)):
    """Xóa TẤT CẢ các session VÀ DỮ LIỆU LIÊN QUAN (PDF, Ảnh, Chunks) của user."""
    sessions_coll = get_mongo_collection("sessions")
    if sessions_coll is None:
        raise HTTPException(status_code=503, detail="Database not connected")

    print(f"--- BẮT ĐẦU XÓA TẤT CẢ SESSION CHO USER: {current_user_id} ---")

    try:
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

        for session_id in session_ids_to_delete:
            try:
                print(f"Đang xóa cascade cho session: {session_id}...")
                delete_results = delete_session_and_associated_files(session_id, current_user_id)
                if delete_results["sessions"] > 0:
                    total_deleted_count += 1
            except Exception as e_inner:
                print(f"Lỗi khi xóa cascade session {session_id}: {e_inner}")

        print(f"--- HOÀN TẤT XÓA TẤT CẢ SESSION. Đã xóa {total_deleted_count} session(s) ---")
        return {"status": "all_sessions_deleted_with_files", "count": total_deleted_count}

    except Exception as e:
        print(f"Lỗi nghiêm trọng khi thực hiện delete_all_user_sessions: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")