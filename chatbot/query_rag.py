import os
import io
import base64
import uuid
import gridfs
import functools

from chatbot import config

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

# ==============================================================================
# SECTION 1: KHỞI TẠO CÁC THÀNH PHẦN TOÀN CỤC (GLOBAL COMPONENTS)
# ==============================================================================

# --- MONGODB CONNECTION ---
try:
    _mongo_client = MongoClient(
        config.MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        maxPoolSize=20,
        retryWrites=True
    )
    _mongo_client.admin.command('ping')
    print("MongoDB ping successful.")

    _mongo_db = _mongo_client[config.MONGO_DB_NAME]
    DB_COLLECTION = _mongo_db["sessions"]

    FS = gridfs.GridFS(_mongo_db)

    # Indexes
    DB_COLLECTION.create_index([("session_id", ASCENDING)], unique=True)
    DB_COLLECTION.create_index([("updated_at", DESCENDING)])

    print(f"Connected successfully to MongoDB and GridFS.")
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    DB_COLLECTION = None
    FS = None


def get_mongo_collection():
    """Trả về collection 'sessions' đã được khởi tạo."""
    return DB_COLLECTION


# --- RAG COMPONENTS ---
try:
    RAG_EMBEDDING_MODEL = GoogleGenerativeAIEmbeddings(
        model=config.EMBEDDING_MODEL_NAME,
        google_api_key=config.GOOGLE_API_KEY
    )

    DB_CHROMA = Chroma(
        persist_directory=config.VECTORSTORE_PATH,
        embedding_function=RAG_EMBEDDING_MODEL,
        collection_name=config.COLLECTION_NAME
    )

    BASE_RETRIEVER = DB_CHROMA.as_retriever(search_kwargs={"k": config.RAG_RETRIEVER_K})

    BASE_COMPRESSOR = CohereRerank(
        top_n=config.RAG_RERANKER_TOP_N,
        model=config.RERANK_MODEL_NAME,
        cohere_api_key=config.COHERE_API_KEY
    )

    GLOBAL_RETRIEVER = ContextualCompressionRetriever(
        base_compressor=BASE_COMPRESSOR,
        base_retriever=BASE_RETRIEVER,
    )
    print("RAG pipeline components initialized successfully.")

except Exception as e:
    print(f"Failed to initialize RAG pipeline: {e}")
    GLOBAL_RETRIEVER = None


# --- LLM MODEL ---
def initialize_llm(model_name, temperature):
    """Khởi tạo mô hình ngôn ngữ."""
    return ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
    )


try:
    TEXT_LLM = initialize_llm(config.TEXT_MODEL_NAME, 0.1)
    VISION_LLM = initialize_llm(config.VISION_MODEL_NAME, 0.1)
    print("LLM model initialized successfully.")
except Exception as e:
    print(f"❌ Failed to initialize LLMs: {e}")
    TEXT_LLM = None
    VISION_LLM = None


# ==============================================================================
# SECTION 2: CÁC HÀM TIỆN ÍCH CỐT LÕI (CORE UTILITY FUNCTIONS)
# ==============================================================================

# --- SESSION MANAGEMENT (MONGO) ---
def save_session_message(session_id, question, answer, image_path=None):
    """Lưu câu hỏi và câu trả lời vào MongoDB (bản tối ưu)."""
    coll = get_mongo_collection()
    fs_client = FS
    if coll is None or fs_client is None:
        print("Lỗi: Không thể lưu session, DB hoặc GridFS chưa kết nối.")
        return

    now = datetime.now(timezone.utc).isoformat()

    image_gridfs_id = None

    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as i_f:
                image_gridfs_id = fs_client.put(
                    i_f,
                    filename=os.path.basename(image_path),
                    metadata={
                        "session_id": session_id,
                        "created_at": now,
                        "updated_at": now
                    }
                )
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


def load_session_messages(session_id, max_history_message: int = 50):
    """Load lịch sử hội thoại từ MongoDB."""
    coll = get_mongo_collection()
    fs_client = FS
    if coll is None or fs_client is None:
        return InMemoryChatMessageHistory()

    history = InMemoryChatMessageHistory()

    try:
        session_doc = coll.find_one(
            {"session_id": session_id},
            projection={"messages": {"$slice": -max_history_message}}
        )

        if not session_doc:
            return history

        for msg in session_doc.get("messages", []):
            if msg["role"] == "user":
                image_gridfs_id_str = msg.get("image_gridfs_id")
                content_list = [{"type": "text", "text": msg["content"]}]
                if image_gridfs_id_str:
                    try:
                        image_id = ObjectId(image_gridfs_id_str)
                        image_data = fs_client.get(image_id)  # Dùng fs_client
                        image_base64 = base64.b64encode(image_data.read()).decode("utf-8")
                        content_list.append(
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}})
                    except Exception as ex:
                        print(f"Lỗi khi tải ảnh từ GridFS (ID: {image_gridfs_id_str}): {ex}")
                history.add_message(HumanMessage(content=content_list))
            elif msg["role"] == "assistant":
                history.add_message(AIMessage(content=msg["content"]))
            else:
                print(f"⚠️ Unknown role: {msg['role']}")
    except Exception as e:
        print(f"Lỗi khi tải session ({session_id}) từ MongoDB: {e}")
        # Trả về history rỗng để tránh crash
        return InMemoryChatMessageHistory()

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
                "created_at": 1,
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
def image_to_base64(image_path, max_size_px=1024, jpeg_quality=85):
    """Chuyển file ảnh sang chuỗi base64, đồng thời
    resize và nén ảnh để tối ưu chi phí và tốc độ.
    """
    try:
        with Image.open(image_path) as img:
            img.thumbnail((max_size_px, max_size_px))

            if img.mode != 'RGB':
                img = img.convert('RGB')

            buffered = io.BytesIO()
            img.save(
                buffered,
                format="JPEG",
                quality=jpeg_quality,
                optimize=True
            )
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"Lỗi xử lý ảnh: {e}")
        return None


# Lưu 128 kết quả truy vấn gần nhất
@functools.lru_cache(maxsize=128)
def get_retrieved_docs(query: str):
    """
    Hàm này lấy tài liệu đã được Rerank.
    Nó được cache lại để tăng hiệu suất.
    Nó được bọc try/except để đảm bảo ổn định.
    """
    retriever = GLOBAL_RETRIEVER
    if retriever is None:
        print("Lỗi: GLOBAL_RETRIEVER chưa được khởi tạo.")
        return []

    try:
        retrieved_docs = retriever.invoke(query)
        return retrieved_docs
    except Exception as e:
        print(f"Failed to retrieve docs for query: {query}, error: {e}")
        return []


def format_docs(docs):
    """Format tài liệu cho prompt."""
    # ... (Hàm này đã tối ưu, giữ nguyên) ...
    return "\n\n".join([
        f"Chunk: {doc.page_content}\n"
        f"Metadata: (Văn bản: {doc.metadata.get('ten_van_ban', 'N/A')}, "
        f"Mã hiệu: {doc.metadata.get('ma_hieu', 'N/A')})" for doc in docs])


# --- MEMORY MANAGEMENT ---
message_history_store = {}


def get_session_history(session_id: str):
    """Lấy lịch sử chat trong bộ nhớ."""
    if session_id not in message_history_store:
        message_history_store[session_id] = load_session_messages(session_id)
    return message_history_store[session_id]


# ==============================================================================
# SECTION 3: CÁC HÀM TẠO CHAIN (CHAIN FACTORY FUNCTIONS)
# ==============================================================================


# --- PROMPTS ---
ROUTER_PROMPT_TEMPLATE = PromptTemplate.from_template("""
Bạn là AI phân loại câu hỏi. Dựa trên Lịch sử trò chuyện và Câu hỏi mới,
hãy phân loại câu hỏi vào MỘT trong hai loại sau:

1.  `rag_query`: Câu hỏi yêu cầu thông tin về quy trình, thủ tục, hoặc
    thông tin cụ thể (ví dụ: "Quy trình nghỉ phép là gì?", "TT07.03 nói về cái gì?",
    "thế còn nhân viên thử việc thì sao?").

2.  `history_query`: Câu hỏi về chính cuộc hội thoại
    (ví dụ: "bạn vừa nói gì?", "câu hỏi thứ 3 của tôi là gì?", "bạn có nhớ tôi không?").

Chỉ trả lời bằng MỘT từ duy nhất: `rag_query` hoặc `history_query`.

---
Lịch sử trò chuyện:
{chat_history}
---
Câu hỏi mới: {question}
---
Phân loại:
""")

HISTORY_PROMPT_TEMPLATE = PromptTemplate.from_template("""
Bạn là trợ lý AI tại CUSC.
Chỉ dựa vào LỊCH SỬ TRÒ CHUYỆN được cung cấp, hãy trả lời CÂU HỎI của người dùng.
Không được bịa đặt thông tin.

---
Lịch sử trò chuyện:
{chat_history}
---
Câu hỏi: {question}
---
Câu trả lời:
""")

RAG_PROMPT_TEMPLATE = PromptTemplate.from_template("""
Bạn là trợ lý AI trả lời các câu hỏi về quy trình, thủ tục nội bộ tại CUSC.

Sử dụng NGỮ CẢNH (tài liệu CUSC) được cung cấp bên dưới để trả lời CÂU HỎI.
Sử dụng LỊCH SỬ TRÒ CHUYỆN chỉ để hiểu bối cảnh (ví dụ: "cái đó" là gì).

Hãy trả lời bằng tiếng Việt, chi tiết, chính xác.
- Luôn trích dẫn nguồn từ NGỮ CẢNH (ví dụ: "(Nguồn: [tên văn bản]...)").
- Nếu NGỮ CẢNH không có thông tin, hãy nói "Tôi không tìm thấy thông tin...".

---
Lịch sử trò chuyện:
{chat_history}
---
Ngữ cảnh (tài liệu CUSC):
{context}
---
Câu hỏi: {question}
Câu trả lời chi tiết:
""")

VISION_PROMPT_TEMPLATE = PromptTemplate.from_template("""
Bạn là trợ lý AI trả lời các câu hỏi về quy trình, thủ tục nội bộ tại CUSC.

Dựa vào lịch sử trò chuyện, hình ảnh và câu hỏi được cung cấp, hãy đưa ra câu trảLợi chi tiết, chính xác và hữu ích.
Trả lời bằng tiếng Việt.

Lịch sử trò chuyện: {chat_history}

Câu hỏi: {question}

Câu trả lời:
""")


def create_rag_router_chain(llm, retriever):
    """Tạo chain RAG có bộ định tuyến."""
    if llm is None or retriever is None:
        print("Lỗi: Không thể tạo RAG chain do thiếu LLM hoặc Retriever.")
        return None

    # --- Định nghĩa các chain con ---
    router_chain = ROUTER_PROMPT_TEMPLATE | llm | StrOutputParser()
    rag_chain = (
            {"context": lambda x: format_docs(get_retrieved_docs(x["question"])),
             "question": lambda x: x["question"],
             "chat_history": lambda x: x.get("chat_history", [])}
            | RAG_PROMPT_TEMPLATE
            | llm
            | StrOutputParser()
    )
    history_chain = (
            {"question": lambda x: x["question"],
             "chat_history": lambda x: x.get("chat_history", [])}
            | HISTORY_PROMPT_TEMPLATE
            | llm
            | StrOutputParser()
    )

    # --- Logic Route ---
    def route(input_dict):
        history = input_dict.get("chat_history", [])
        question = input_dict["question"]
        try:
            classification = router_chain.invoke({"chat_history": history, "question": question})
            if "history_query" in classification:
                print("--- (Router: Lịch sử) ---")
                return history_chain
            else:
                print("--- (Router: RAG) ---")
                return rag_chain
        except Exception as e:
            print(f"Lỗi khi chạy router: {e}. Mặc định dùng RAG.")
            return rag_chain  # Fallback an toàn

    # --- Chain cơ sở có router ---
    base = (
            {"question": lambda x: x["question"],
             "chat_history": lambda x: x.get("chat_history", [])}
            | RunnableLambda(route)
    )

    # --- Bọc bộ nhớ ---
    chain_with_history = RunnableWithMessageHistory(
        base,
        get_session_history,
        input_messages_key="question",
        history_messages_key="chat_history",
    )
    return chain_with_history


# --- CHAIN FACTORY: VISION ---
def create_vision_chain(llm):
    """Tạo chain Vision có bộ nhớ."""
    if llm is None:
        print("Lỗi: Không thể tạo Vision chain do thiếu LLM.")
        return None

    # --- Hàm format message (lồng bên trong) ---
    def _format_vision_message(input_dict):
        history = input_dict.get("chat_history", [])
        question = input_dict["question"]
        img_path = input_dict["image_path"]
        prompt_text = VISION_PROMPT_TEMPLATE.invoke(
            {"question": question, "chat_history": history}).to_string()  # Dùng invoke và to_string
        image_base64 = image_to_base64(img_path)  # Đã có resize/compress
        if not image_base64: return [HumanMessage(content="Lỗi ảnh.")]
        image_data = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        return [HumanMessage(content=[{"type": "text", "text": prompt_text}, image_data])]

    def _format_history_input(input_dict):
        question = input_dict["question"]
        img_path = input_dict["image_path"]
        image_base64 = image_to_base64(img_path)
        if not image_base64: return HumanMessage(content=f"(Lỗi ảnh) {question}")
        image_data = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        return HumanMessage(content=[{"type": "text", "text": question}, image_data])

    # --- Chain cơ sở ---
    base_vision = RunnablePassthrough() | RunnableLambda(_format_vision_message) | llm

    # --- Bọc bộ nhớ ---
    vision_chain_with_history = RunnableWithMessageHistory(
        base_vision, get_session_history,
        input_messages_key="question",
        input_messages_key_fx=RunnableLambda(_format_history_input),
        history_messages_key="chat_history",
    )
    return vision_chain_with_history


# ==============================================================================
# SECTION 4: KHỞI TẠO CHAIN TOÀN CỤC (ĐỂ API SỬ DỤNG)
# ==============================================================================

# Gọi các hàm factory để tạo chain sẵn sàng cho API import
RAG_CHAIN_WITH_HISTORY = create_rag_router_chain(TEXT_LLM, GLOBAL_RETRIEVER)
VISION_CHAIN_WITH_HISTORY = create_vision_chain(VISION_LLM)


# ==============================================================================
# SECTION 5: CÁC HÀM XỬ LÝ CLI (COMMAND-LINE INTERFACE)
# ==============================================================================

def handle_text_query(query_text, session_id="default_session"):
    print("--- 🔍 Đang xử lý câu hỏi văn bản bằng RAG ---")

    chain_to_run = RAG_CHAIN_WITH_HISTORY

    if chain_to_run is None:
        print("Lỗi: RAG Chain chưa được khởi tạo.")
        return

    full_response = ""
    config_ = {"configurable": {"session_id": session_id}}
    input_data = {"question": query_text}

    try:
        for chunk in chain_to_run.stream(input_data, config=config_):
            full_response += chunk
            print(chunk, end="", flush=True)
        print("\n")
        # Lưu vào DB sau khi stream xong
        save_session_message(session_id, query_text, full_response)
    except Exception as e:
        print(f"\nLỗi khi xử lý câu hỏi text: {e}")


def handle_multimodal_query(query_text, image_path, session_id="default_session"):
    print(f"--- 🖼️ Xử lý câu hỏi có ảnh: {os.path.basename(image_path)} ---")

    chain_to_run = VISION_CHAIN_WITH_HISTORY

    if chain_to_run is None:
        print("Lỗi: Vision Chain chưa được khởi tạo.")
        return

    full_response = ""
    input_data = {"question": query_text, "image_path": image_path}
    config_ = {"configurable": {"session_id": session_id}}

    try:
        for chunk in chain_to_run.stream(input_data, config=config_):
            content = chunk.content
            full_response += content
            print(content, end="", flush=True)
        print("\n")
        # Lưu vào DB sau khi stream xong
        save_session_message(session_id, query_text, full_response, image_path=image_path)
    except Exception as e:
        print(f"\nLỗi khi xử lý câu hỏi ảnh: {e}")


# ==============================================================================
# SECTION 6: HÀM MAIN CHO CLI
# ==============================================================================

def main():
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
                created_ts = s.get('created_at', 'N/A')
                updated_ts = s.get('updated_at', 'N/A')
                print(f"  [{i + 1}] {s['session_id']} ({s['num_messages']} tin nhắn, cập nhật: {s['updated_at']})")
                print(f"      Tạo: {created_ts} | Cập nhật: {updated_ts}")

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
            handle_multimodal_query(query_text, image_path, session_id)
        elif image_path:
            print(f"⚠️ Không tìm thấy ảnh tại '{image_path}'")
        else:
            handle_text_query(query_text, session_id)


if __name__ == "__main__":
    main()
