import os
import io
import base64
import config
import uuid
import gridfs

from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson.objectid import ObjectId
from PIL import Image

from langchain.retrievers.contextual_compression import ContextualCompressionRetriever
from langchain_cohere import CohereRerank
from langchain_chroma import Chroma
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate


# --- MONGODB CONNECTION ---
try:
    _mongo_client = MongoClient(
        config.MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000
    )
    _mongo_client.admin.command('ping')
    print("MongoDB ping successful.")

    _mongo_db = _mongo_client[config.MONGO_DB_NAME]
    DB_COLLECTION = _mongo_db["sessions"]

    FS = gridfs.GridFS(_mongo_db)

    DB_COLLECTION.create_index([("session_id", ASCENDING)], unique=True)
    print(f"Connected successfully to MongoDB and GridFS.")
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    DB_COLLECTION = None
    FS = None


def get_mongo_collection():
    """Trả về collection 'sessions' đã được khởi tạo."""
    return DB_COLLECTION


# --- SESSION MANAGEMENT (MONGO) ---
def save_session_message(session_id, question, answer, image_path=None):
    """Lưu câu hỏi và câu trả lời vào MongoDB (bản tối ưu)."""
    coll = get_mongo_collection()
    if coll is None or FS is None:
        print("Lỗi: Không thể lưu session, DB hoặc GridFS chưa kết nối.")
        return

    now = datetime.now(timezone.utc).isoformat()

    image_gridfs_id = None

    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as i_f:
                image_gridfs_id = FS.put(i_f, filename=os.path.basename(image_path))
        except Exception as ex:
            print(f"Lỗi khi lưu ảnh vào GridFS: {ex}")

    new_messages = [
        {
            "role": "user",
            "content": question,
            "image_gridfs_id": str(image_gridfs_id) if image_gridfs_id else None,
            "timestamp": now
        },
        {
            "role": "assistant",
            "content": answer,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    ]

    coll.update_one(
        {"session_id": session_id},
        {
            "$push": {"messages": {"$each": new_messages}},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
            "$setOnInsert": {  # <-- Chỉ set các trường này khi TẠO MỚI
                "_id": uuid.uuid4().hex,
                "created_at": now
            }
        },
        upsert=True  # <-- Tự động tạo nếu chưa có
    )


def load_session_messages(session_id):
    """Load lịch sử hội thoại từ MongoDB."""
    coll = get_mongo_collection()
    if coll is None or FS is None:
        return InMemoryChatMessageHistory()

    history = InMemoryChatMessageHistory()

    session_doc = coll.find_one({"session_id": session_id})
    if not session_doc:
        return history

    for msg in session_doc.get("messages", []):
        if msg["role"] == "user":
            image_gridfs_id_str = msg.get("image_gridfs_id")
            content_list = [{"type": "text", "text": msg["content"]}]

            if image_gridfs_id_str:
                try:
                    image_id = ObjectId(image_gridfs_id_str)
                    image_data = FS.get(image_id)
                    image_base64 = base64.b64encode(image_data.read()).decode("utf-8")
                    content_list.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                    })
                except Exception as ex:
                    print(f"Lỗi khi tải ảnh từ GridFS (ID: {image_gridfs_id_str}): {ex}")

            history.add_message(HumanMessage(content=content_list))
        elif msg["role"] == "assistant":
            history.add_message(AIMessage(content=msg["content"]))
        else:
            print(f"⚠️ Unknown role: {msg['role']}")

    return history


def list_sessions(limit=50):
    """Liệt kê các session (đã tối ưu) mà không tải messages."""
    coll = get_mongo_collection()
    if coll is None:
        return []

    pipeline = [
        {
            "$project": {  # Chỉ lấy các trường này
                "_id": 0,
                "session_id": 1,
                "updated_at": 1,
                "num_messages": {"$size": "$messages"}  # Yêu cầu DB đếm
            }
        },
        {
            "$sort": {"updated_at": DESCENDING}
        },
        {
            "$limit": limit  # Chỉ lấy 50 session gần nhất
        }
    ]

    try:
        sessions = list(coll.aggregate(pipeline))
        return sessions
    except Exception as e:
        print(f"Lỗi khi list sessions: {e}")
        return []


# --- UTILS ---
def image_to_base64(image_path):
    """Chuyển file ảnh sang chuỗi base64."""
    try:
        with Image.open(image_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"Lỗi xử lý ảnh: {e}")
        return None


def initialize_llm(model_name, temperature):
    """Khởi tạo mô hình ngôn ngữ."""
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
    )


# --- RAG PIPELINE (TEXT) ---
PROMPT_TEMPLATE_RAG = """
Bạn là trợ lý AI trả lời các câu hỏi về quy trình, thủ tục nội bộ tại CUSC.

Bạn có hai nguồn thông tin để trả lời: LỊCH SỬ TRÒ CHUYỆN và NGỮ CẢNH (tài liệu CUSC).
Hãy sử dụng cả hai một cách thông minh để trả lời câu hỏi của người dùng.

1.  **Nếu câu hỏi là về quy trình, thủ tục CUSC:**
    * Hãy dựa chủ yếu vào NGỮ CẢNH (tài liệu) để trả lời.
    * Sử dụng LỊCH SỬ TRÒ CHUYỆN chỉ để hiểu bối cảnh (ví dụ: "cái đó" là gì).
    * Luôn trích dẫn nguồn từ NGỮ CẢNH (ví dụ: "(Nguồn: [tên văn bản]...)").
    * Nếu NGỮ CẢNH không có thông tin, hãy nói "Tôi không tìm thấy thông tin...".

2.  **Nếu câu hỏi là về chính cuộc hội thoại (ví dụ: "tôi đã hỏi gì?", "bạn vừa nói gì?"):**
    * Hãy dựa hoàn toàn vào LỊCH SỬ TRÒ CHUYỆN để trả lời.
    * Không cần trích dẫn nguồn từ NGỮ CẢNH.

Hãy trả lời bằng tiếng Việt, với định dạng đẹp và dễ đọc.

---
Lịch sử trò chuyện:
{chat_history}

---
Ngữ cảnh (tài liệu CUSC):
{context}

---
Câu hỏi: {question}

Câu trả lời chi tiết:
"""

message_history_store = {}


def get_session_history(session_id: str):
    """Lấy lịch sử chat trong bộ nhớ."""
    if session_id not in message_history_store:
        message_history_store[session_id] = load_session_messages(session_id)
    return message_history_store[session_id]


def handle_text_query(llm, query_text, session_id="default_session"):
    print("--- 🔍 Đang xử lý câu hỏi văn bản bằng RAG ---")

    embedding_model = GoogleGenerativeAIEmbeddings(
        model=config.EMBEDDING_MODEL_NAME,
        google_api_key=config.GOOGLE_API_KEY
    )

    db = Chroma(
        persist_directory=config.VECTORSTORE_PATH,
        embedding_function=embedding_model,
        collection_name=config.COLLECTION_NAME
    )

    base_retriever = db.as_retriever(search_kwargs={"k": config.RAG_RETRIEVER_K})
    base_compressor = CohereRerank(
        top_n=config.RAG_RERANKER_TOP_N,
        model=config.RERANK_MODEL_NAME,
        cohere_api_key=config.COHERE_API_KEY
    )
    retriever = ContextualCompressionRetriever(
        base_compressor=base_compressor,
        base_retriever=base_retriever,
    )

    def format_docs(docs):
        return "\n\n".join([
            f"Nội dung Chunk: {doc.page_content}\n"
            f"Metadata: (Tên văn bản: {doc.metadata.get('ten_van_ban', 'N/A')}, "
            f"Mã hiệu: {doc.metadata.get('ma_hieu', 'N/A')})"
            for doc in docs
        ])

    prompt = PromptTemplate.from_template(PROMPT_TEMPLATE_RAG)
    base_rag_chain = (
        {"context": lambda x: format_docs(retriever.invoke(x["question"])),
         "question": lambda x: x["question"],
         "chat_history": lambda x: x.get("chat_history", [])}
        | prompt
        | llm
        | StrOutputParser()
    )

    rag_chain_with_history = RunnableWithMessageHistory(
        base_rag_chain,
        get_session_history,
        input_messages_key="question",
        history_messages_key="chat_history",
    )

    full_response = ""
    config_ = {"configurable": {"session_id": session_id}}
    input_data = {"question": query_text}

    for chunk in rag_chain_with_history.stream(input_data, config=config_):
        full_response += chunk
        print(chunk, end="", flush=True)
    print("\n")

    save_session_message(session_id, query_text, full_response)


# --- MULTIMODAL QUERY (TEXT + IMAGE) ---
PROMPT_TEMPLATE_VISION = """
Bạn là một trợ lý AI thông minh. Dựa vào hình ảnh và câu hỏi được cung cấp, hãy đưa ra câu trả lời chi tiết, chính xác và hữu ích.
Trả lời bằng tiếng Việt.

Lịch sử trò chuyện: {chat_history}

Câu hỏi: {question}

Câu trả lời:
"""


def handle_multimodal_query(llm, query_text, image_path, session_id="default_session"):
    print(f"--- 🖼️ Xử lý câu hỏi có ảnh: {os.path.basename(image_path)} ---")

    def _format_vision_message(input_dict):
        history = input_dict.get("chat_history", [])
        question = input_dict["question"]
        img_path = input_dict["image_path"]
        prompt_text = PROMPT_TEMPLATE_VISION.format(question=question, chat_history=history)
        image_base64 = image_to_base64(img_path)
        if not image_base64:
            return [HumanMessage(content="Lỗi ảnh.")]
        image_data = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        return [HumanMessage(content=[{"type": "text", "text": prompt_text}, image_data])]

    def _format_history_input(input_dict):
        question = input_dict["question"]
        img_path = input_dict["image_path"]
        image_base64 = image_to_base64(img_path)
        if not image_base64:
            return HumanMessage(content=f"(Lỗi ảnh) {question}")
        image_data = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        return HumanMessage(content=[{"type": "text", "text": question}, image_data])

    base_vision_chain = RunnablePassthrough() | RunnableLambda(_format_vision_message) | llm

    vision_chain_with_history = RunnableWithMessageHistory(
        base_vision_chain,
        get_session_history,
        input_messages_key="question",
        input_messages_key_fx=RunnableLambda(_format_history_input),
        history_messages_key="chat_history",
    )

    input_data = {"question": query_text, "image_path": image_path}
    config_ = {"configurable": {"session_id": session_id}}

    full_response = ""
    for chunk in vision_chain_with_history.stream(input_data, config=config_):
        full_response += chunk.content
        print(chunk.content, end="", flush=True)
    print("\n")

    save_session_message(session_id, query_text, full_response, image_path=image_path)


# --- MAIN FUNCTION ---
def main():
    text_llm = initialize_llm(config.TEXT_MODEL_NAME, temperature=0.1)
    vision_llm = initialize_llm(config.VISION_MODEL_NAME, temperature=0.1)

    print("🤖 Chatbot CUSC (MongoDB) sẵn sàng!")
    print("=" * 30)
    print("[1] Tạo session mới")
    print("[2] Tiếp tục session cũ")

    session_id = None
    choice = input("Lựa chọn của bạn (1 hoặc 2): ").strip()

    if choice == '2':
        # --- Logic tiếp tục session ---
        print("\nĐang tải các session gần đây...")
        sessions = list_sessions(limit=10)  # Lấy 10 session gần nhất

        if not sessions:
            print("Không tìm thấy session nào. Sẽ tạo session mới.")
            session_id = str(uuid.uuid4())
        else:
            for i, s in enumerate(sessions):
                print(f"  [{i + 1}] {s['session_id']} ({s['num_messages']} tin nhắn, cập nhật: {s['updated_at']})")

            try:
                s_choice = int(input("Chọn session (nhập số 1, 2,...) hoặc 0 để tạo mới: ").strip())
                if 0 < s_choice <= len(sessions):
                    session_id = sessions[s_choice - 1]['session_id']
                else:
                    print("Lựa chọn không hợp lệ, sẽ tạo session mới.")
                    session_id = str(uuid.uuid4())
            except ValueError:
                print("Lựa chọn không hợp lệ, sẽ tạo session mới.")
                session_id = str(uuid.uuid4())
    else:
        # --- Logic tạo session mới (mặc định) ---
        session_id = str(uuid.uuid4())

    print(f"\n🆔 Session ID hiện tại: {session_id}")
    print("Nhập 'exit' để thoát.\n")

    # Tải lịch sử ngay khi bắt đầu (để chat_history không bị rỗng)
    get_session_history(session_id)

    while True:
        query_text = input("👤 Bạn hỏi: ")
        if query_text.lower() == "exit":
            break

        image_path = input("🖼️ Nhập đường dẫn ảnh (Enter nếu không có): ").strip()
        print("\n💡 Trả lời:")

        if image_path and os.path.exists(image_path):
            handle_multimodal_query(vision_llm, query_text, image_path, session_id)
        elif image_path:
            print(f"⚠️ Không tìm thấy ảnh tại '{image_path}'")
        else:
            handle_text_query(text_llm, query_text, session_id)


if __name__ == "__main__":
    main()
