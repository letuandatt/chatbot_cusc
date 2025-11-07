import traceback
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from pymongo import DESCENDING

from chatbot.query_rag import get_mongo_collection, FS
from chatbot.auth_utils import get_current_user_id, verify_password, get_password_hash
from backend.models import UserProfile, ChangePasswordRequest, ChageNameRequest

router = APIRouter(
    tags=["User Management"],
    dependencies=[Depends(get_current_user_id)]  # Tất cả endpoint trong file này đều cần đăng nhập
)

@router.delete("/user/me", status_code=status.HTTP_200_OK)
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


@router.get("/user/me", response_model=UserProfile)
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


@router.put("/user/me/password", status_code=status.HTTP_200_OK)
async def change_current_user_password(
        request: ChangePasswordRequest,
        current_user_id: str = Depends(get_current_user_id)
):
    """Xác thực mật khẩu hiện tại và cập nhật mật khẩu mới cho người dùng."""
    users_coll = get_mongo_collection("users")
    if users_coll is None:
        raise HTTPException(status_code=503, detail="User database not connected")

    try:
        user_doc = users_coll.find_one({"_id": ObjectId(current_user_id)})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")

        if not verify_password(request.current_password, user_doc["hashed_password"]):
            raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")

        new_hashed_password = get_password_hash(request.new_password)

        result = users_coll.update_one(
            {"_id": ObjectId(current_user_id)},
            {"$set": {"hashed_password": new_hashed_password}}
        )

        if result.modified_count == 1:
            print(f"DEBUG: Password updated successfully for user {current_user_id}")
            return {"message": "Mật khẩu đã được cập nhật thành công."}
        else:
            raise HTTPException(status_code=500, detail="Không thể cập nhật mật khẩu.")

    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        print(f"Lỗi khi đổi mật khẩu user {current_user_id}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi máy chủ khi đổi mật khẩu.")


@router.put("/user/me/name", status_code=status.HTTP_200_OK)
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
            return {"message": "Đã cập nhật tên thành công"}
        elif result.modified_count == 0 and result.matched_count == 1:
            return {"message": "Tên không thay đổi (giống tên cũ)."}
        else:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng để cập nhật.")
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        print(f"Lỗi khi đổi tên user {current_user_id}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi máy chủ khi đổi tên user.")


@router.get("/user/documents", status_code=status.HTTP_200_OK)
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