from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from pymongo import MongoClient

from chatbot import config


# --- Config ---
SECRET_KEY = config.SECRET_KEY
ALGORITHM = config.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = config.ACCESS_TOKEN_EXPIRE_MINUTES

# Encrypt password
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Database
MONGO_URI = config.MONGO_URI
client = MongoClient(MONGO_URI)
db = client["cusc_rag"]
users = db["users"]

router = APIRouter(prefix="/auth", tags=["Auth"])

# --- Constants ---
MAX_PASSWORD_CHARS = 64
BCRYPT_MAX_BYTES = 72
MIN_PASSWORD_LENGTH = 8


def _truncate_to_bcrypt_bytes(pw: str) -> str:
    # Truncate to max 72 bytes safely for bcrypt
    encoded = pw.encode("utf-8")
    if len(encoded) <= BCRYPT_MAX_BYTES:
        return pw
    # truncate bytes and decode ignoring partial character at boundary
    truncated = encoded[:BCRYPT_MAX_BYTES]
    return truncated.decode("utf-8", errors="ignore")


# --- Models ---
class UserRegister(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("Password is required")
        if len(v) > MAX_PASSWORD_CHARS:
            raise ValueError(f"Password must be at most {MAX_PASSWORD_CHARS} characters")
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError("Password must be at least 8 characters")

        # if not any(c.isupper() for c in v):
        #     raise ValueError("Password must contain at least one uppercase letter")
        # if not any(c.islower() for c in v):
        #     raise ValueError("Password must contain at least one lowercase letter")
        # if not any(c.isdigit() for c in v):
        #     raise ValueError("Password must contain at least one digit")
        # if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
        #     raise ValueError("Password must contain at least one special character")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Utility ---
def hash_password(password: str):
    # Safe truncate for bcrypt byte-limit
    safe_pw = _truncate_to_bcrypt_bytes(password)
    return pwd_context.hash(safe_pw[:72])

def verify_password(plain, hashed):
    safe_pw = _truncate_to_bcrypt_bytes(plain)
    return pwd_context.verify(safe_pw, hashed)

def create_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- Routes ---
@router.post("/register")
def register(user: UserRegister):
    if users.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(user.password)
    users.insert_one({"email": user.email, "password": hashed, "created_at": datetime.utcnow()})
    return {"msg": "User created successfully"}

@router.post("/login", response_model=Token)
def login(user: UserLogin):
    db_user = users.find_one({"email": user.email})
    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}