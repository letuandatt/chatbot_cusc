from pydantic import BaseModel, EmailStr, constr
from datetime import datetime

# --- User models (for validation) ---
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
