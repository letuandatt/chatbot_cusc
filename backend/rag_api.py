import uuid
import os
import traceback
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from typing import Optional
from chatbot.query_rag import (
    handle_text_query,
    handle_multimodal_query,
    list_sessions,
    load_session_messages,
    get_mongo_collection,
    initialize_llm
)
import chatbot.config as config

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
    try:
        coll = get_mongo_collection()
        coll.database.client.admin.command("ping")
        return {"status": "ok", "mongo": True, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# --- Create new session ---
@app.post("/session/new")
def create_new_session():
    session_id = str(uuid.uuid4().hex)
    coll = get_mongo_collection()
    now = datetime.now(timezone.utc).isoformat()
    coll.insert_one({
        "session_id": session_id,
        "created_at": now,
        "updated_at": now,
        "messages": []
    })
    return {"session_id": session_id, "message": "Session created successfully"}


# --- List sessions ---
@app.get("/sessions")
def get_sessions():
    sessions = list_sessions(limit=50)
    return {"count": len(sessions), "sessions": sessions}


# --- View a specific session ---
@app.get("/session/{session_id}")
def view_session(session_id: str):
    history = load_session_messages(session_id)
    messages = []
    for msg in history.messages:
        role = "user" if msg.type == "human" else "assistant"
        content = msg.content
        messages.append({"role": role, "content": content})
    return {"session_id": session_id, "messages": messages}


# --- Delete session ---
@app.delete("/session/{session_id}/delete")
def delete_session(session_id: str):
    coll = get_mongo_collection()
    result = coll.delete_one({"session_id": session_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


# --- Chat: text-only query ---
@app.post("/chat/text")
async def chat_text(question: str = Form(...), session_id: Optional[str] = Form(None)):
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    session_id = session_id or str(uuid.uuid4().hex)
    try:
        llm = initialize_llm(config.TEXT_MODEL_NAME, temperature=0.1)
        answer = handle_text_query(llm, question, session_id)
        return JSONResponse({
            "session_id": session_id,
            "question": question,
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error during query: {str(e)}")


# --- Chat: text + image (multimodal) ---
@app.post("/chat/image")
async def chat_with_image(
    question: str = Form(...),
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None)
):
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    session_id = session_id or str(uuid.uuid4().hex)

    try:
        # Save temporary file
        image_bytes = await file.read()
        image_path = f"/tmp/{uuid.uuid4().hex}_{file.filename}"
        with open(image_path, "wb") as f:
            f.write(image_bytes)

        llm = initialize_llm(config.VISION_MODEL_NAME, temperature=0.1)
        answer = handle_multimodal_query(llm, question, image_path, session_id)

        os.remove(image_path)
        return JSONResponse({
            "session_id": session_id,
            "question": question,
            "filename": file.filename,
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error handling image query: {str(e)}")


# --- Root ---
@app.get("/")
def index():
    return {
        "service": "RAG API Backend",
        "description": "Use /chat/text or /chat/image to interact with the AI assistant.",
        "docs": "/docs",
        "health": "/health"
        # run on: http://127.0.0.1:8000/docs#/
    }
