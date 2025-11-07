from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime

from chatbot.query_rag import get_mongo_collection
from chatbot.auth_utils import (
    verify_password,
    get_password_hash,
    create_access_token
)
from backend.models import UserCreate
from backend.config import VN_TZ

router = APIRouter(
    tags=["Authentication"]
)

@router.post("/register", status_code=status.HTTP_201_CREATED)
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


@router.post("/token")  # Standard OAuth2 endpoint name
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