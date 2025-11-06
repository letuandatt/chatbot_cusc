import os
import io
import base64
import uuid
import gridfs
import functools
import pytz
import hashlib

from chatbot import config
from chatbot.extract_data import fix_first_roman_headings

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
from langchain_core.runnables import RunnableLambda, RunnablePassthrough, ConfigurableFieldSpec
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

from llama_parse import LlamaParse
from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document


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

def get_mongo_collection(collection_name: str = "sessions"):
    """Trả về collection 'sessions' đã được khởi tạo."""
    if _mongo_client is None or _mongo_db is None:
        print(f"Lỗi: Kết nối MongoDB chưa được thiết lập")
        return None
    try:
        return _mongo_db[collection_name]
    except Exception as ex:
        print(f"Lỗi khi lấy collection '{collection_name}': {ex}")
        return None


try:
    DB_DOCUMENTS_COLLECTION = get_mongo_collection("documents")
    if DB_DOCUMENTS_COLLECTION is not None:
        DB_DOCUMENTS_COLLECTION.create_index([("session_id", ASCENDING)])
        DB_DOCUMENTS_COLLECTION.create_index([("user_id", ASCENDING)])
        DB_DOCUMENTS_COLLECTION.create_index([("created_at", DESCENDING)])
        print("MongoDB collection 'documents' initialized.")
except Exception as e:
    print(f"Failed to initialize 'documents' collection: {e}")
    DB_DOCUMENTS_COLLECTION = None


def check_session_belongs_to_user(session_id: str, user_id: str) -> bool:
    """Kiểm tra session có tồn tại và thuộc về user_id không."""
    coll = get_mongo_collection("sessions")  # Lấy collection sessions
    if coll is None:
        return False
    try:
        # Đếm số document khớp cả session_id và user_id
        return coll.count_documents({"session_id": session_id, "user_id": user_id}, limit=1) > 0
    except Exception as e:
        print(f"Lỗi khi kiểm tra session ownership: {e}")
        return False


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


# --- FILE RAG COMPONENTS ---
try:
    # Khởi tạo Chroma instance cho collection "temp"
    DB_CHROMA_TEMP = Chroma(
        persist_directory=config.VECTORSTORE_PATH,
        embedding_function=RAG_EMBEDDING_MODEL,
        collection_name=config.TEMP_COLLECTION_NAME  # Sử dụng collection "temp"
    )
    print(f"Chroma temp collection '{config.TEMP_COLLECTION_NAME}' loaded.")

    # Compressor riêng cho file RAG (sử dụng config riêng)
    FILE_COMPRESSOR = CohereRerank(
        top_n=config.FILE_RAG_RERANKER_TOP_N,
        model=config.RERANK_MODEL_NAME,
        cohere_api_key=config.COHERE_API_KEY
    )

    def get_file_retriever(session_id: str):
        """
        Tạo một retriever đã được lọc (filter) theo session_id.
        """
        print(f"--- DEBUG: Creating FILE retriever for session: {session_id} ---")
        # 1. Base retriever (từ collection temp, lọc theo session_id)
        file_base_retriever = DB_CHROMA_TEMP.as_retriever(
            search_kwargs={
                "k": config.FILE_RAG_RETRIEVER_K,
                "filter": {"session_id": session_id}  # Đây là mấu chốt
            }
        )
        # 2. Bọc retriever này với Reranker
        return ContextualCompressionRetriever(
            base_compressor=FILE_COMPRESSOR,
            base_retriever=file_base_retriever,
        )

except Exception as e:
    print(f"Failed to initialize FILE RAG pipeline: {e}")
    DB_CHROMA_TEMP = None
    FILE_COMPRESSOR = None

# --- VIETNAM TIMEZONE DEFINITION ---
try:
    VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
    print("VN_TZ initialized successfully.")
except pytz.UnknownTimeZoneError:
    print("VN_TZ not found, using UTC as default timezone.")
    VN_TZ = timezone.utc


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
def save_session_message(session_id, user_id, question, answer, image_path=None):
    """Lưu câu hỏi và câu trả lời vào MongoDB (bản tối ưu)."""
    coll = get_mongo_collection()
    fs_client = FS
    if coll is None or fs_client is None:
        print("Lỗi: Không thể lưu session, DB hoặc GridFS chưa kết nối.")
        return

    now = datetime.now(VN_TZ).isoformat()

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
            "timestamp": datetime.now(VN_TZ).isoformat()
        }
    ]

    coll.update_one(
        {"session_id": session_id, "user_id": user_id},
        {
            "$push": {"messages": {"$each": new_messages}},
            "$set": {"updated_at": datetime.now(VN_TZ).isoformat()},
            "$setOnInsert": {  # <-- Chỉ set các trường này khi TẠO MỚI
                "created_at": now
            }
        },
        upsert=True  # <-- Tự động tạo nếu chưa có
    )


def load_session_messages(session_id: str, user_id: str, max_history_message: int = 50):
    """Load lịch sử hội thoại từ MongoDB."""
    coll = get_mongo_collection("sessions")
    fs_client = FS
    if coll is None or fs_client is None:
        return InMemoryChatMessageHistory()

    history = InMemoryChatMessageHistory()

    try:
        session_doc = coll.find_one(
            {"session_id": session_id, "user_id": user_id},
            projection={"messages": {"$slice": -max_history_message}}
        )

        if not session_doc:
            print(f"DEBUG: Session {session_id} not found or doesn't belong to user {user_id}")
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


def list_sessions(user_id: str, limit=50):
    """Liệt kê các session (đã tối ưu) mà không tải messages."""
    coll = get_mongo_collection("sessions")
    if coll is None:
        return []

    pipeline = [
        {
            "$match": {"user_id": user_id}
        },
        {
            "$project": {  # Chỉ lấy các trường này
                "_id": 0,
                "session_id": 1,
                "session_name": 1,
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

def check_session_has_files(session_id: str) -> bool:
    """Kiểm tra xem session này đã tải file PDF nào lên chưa."""
    coll = DB_DOCUMENTS_COLLECTION
    if coll is None:
        return False
    try:
        return coll.count_documents({"session_id": session_id}, limit=1) > 0
    except Exception as e:
        print(f"Lỗi khi kiểm tra file của session: {e}")
        return False


def compute_file_hash(file_path: str) -> str:
    """Tạo hash MD5 cho file để tránh trùng."""
    with open(file_path, "rb") as f:
        file_data = f.read()
    return hashlib.md5(file_data).hexdigest()

def save_pdf_to_mongo(file_path: str, session_id: str, user_id: str) -> str | None:
    fs_client = FS
    coll = DB_DOCUMENTS_COLLECTION
    if fs_client is None or coll is None:
        print("Lỗi: Không thể lưu file, DB hoặc GridFS chưa kết nối.")
        return None

    now = datetime.now(VN_TZ).isoformat()
    file_name = os.path.basename(file_path)
    file_hash = compute_file_hash(file_path)  # ✅ thêm dòng này

    try:
        with open(file_path, "rb") as f:
            file_id = fs_client.put(
                f,
                filename=file_name,
                metadata={
                    "session_id": session_id,
                    "user_id": user_id,
                    "file_hash": file_hash,
                    "created_at": now
                }
            )

        doc_record = {
            "session_id": session_id,
            "user_id": user_id,
            "filename": file_name,
            "gridfs_id": str(file_id),
            "file_hash": file_hash,  # ✅ thêm vào đây
            "created_at": now,
            "status": "uploaded"
        }
        coll.insert_one(doc_record)
        print(f"Đã lưu file '{file_name}' vào GridFS (ID: {file_id}) và collection 'documents'.")
        return str(file_id)
    except Exception as e:
        print(f"Lỗi khi lưu file PDF vào MongoDB: {e}")
        return None


def process_and_vectorize_pdf(file_path: str, session_id: str, user_id: str):
    """
    Sử dụng LlamaParse để phân tích PDF,
    split (Markdown + Semantic), và lưu vào Chroma (temp collection).
    (Phiên bản đã sửa lỗi và đồng bộ logic)
    """
    if DB_CHROMA_TEMP is None:
        print("Lỗi: Không thể vector hóa, DB_CHROMA_TEMP chưa sẵn sàng.")
        return

    print(f"Bắt đầu xử lý và vector hóa file: {os.path.basename(file_path)}")

    # 1. Parse PDF dùng LlamaParse (theo config)
    loader = LlamaParse(
        api_key=config.LLAMA_CLOUD_API_KEY,
        parse_mode="parse_page_with_agent",
        model=config.LLAMA_PARSE_MODEL,
        output_tables_as_HTML=True,
        merge_tables_across_pages_in_markdown=True,
        compact_markdown_table=True,
        language="vi",
        high_res_ocr=True,
        adaptive_long_table=True,
        outlined_table_extraction=True,
        result_type="markdown",
        specialized_chart_parsing_efficient=True
    )

    try:
        # documents là một list các LlamaDocument
        documents = loader.load_data(file_path)
    except Exception as e:
        print(f"Lỗi khi gọi LlamaParse: {e}")
        DB_DOCUMENTS_COLLECTION.update_one(
            {"session_id": session_id, "filename": os.path.basename(file_path)},
            {"$set": {"status": "error_parsing"}}
        )
        return

    print(f"LlamaParse hoàn tất, {len(documents)} tài liệu được trích xuất.")

    # 2. Split tài liệu (Tái sử dụng logic từ create_database.py)
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "section"), ("##", "subsection"), ("###", "subsubsection")],
        return_each_line=False,
        strip_headers=False
    )
    semantic_splitter = SemanticChunker(embeddings=RAG_EMBEDDING_MODEL)

    all_chunks = []
    base_metadata = {
        "session_id": session_id,
        "user_id": user_id,
        "source": os.path.basename(file_path)
    }

    for doc in documents:  # doc là một LlamaDocument

        # === SỬA LỖI TẠI ĐÂY ===
        markdown_content = doc.get_content()

        # (Tùy chọn) Áp dụng logic fix tiêu đề La Mã nếu cần
        markdown_content = fix_first_roman_headings(markdown_content)

        header_chunks = header_splitter.split_text(markdown_content)

        for header_chunk in header_chunks:
            chunk_metadata = base_metadata.copy()

            if isinstance(header_chunk, Document):
                chunk_metadata.update(header_chunk.metadata)
                text_chunk = header_chunk.page_content
            else:
                text_chunk = str(header_chunk)

            # === ĐỒNG BỘ LOGIC SPLIT ===
            # Dùng .split_text() để trả về list[str]
            semantic_chunks_strings = semantic_splitter.split_text(text_chunk)

            # Gán metadata đã được kết hợp
            for sc_string in semantic_chunks_strings:
                # Tạo Document mới cho mỗi chunk
                final_doc = Document(page_content=sc_string, metadata=chunk_metadata)
                all_chunks.append(final_doc)

    print(f"Split thành công {len(all_chunks)} chunks.")

    # 3. Lưu vào Chroma (TEMP Collection)
    if all_chunks:
        try:
            DB_CHROMA_TEMP.add_documents(documents=all_chunks)
            print(f"Đã lưu {len(all_chunks)} chunks vào collection '{config.TEMP_COLLECTION_NAME}'.")

            DB_DOCUMENTS_COLLECTION.update_one(
                {"session_id": session_id, "filename": os.path.basename(file_path)},
                {"$set": {"status": "processed"}}
            )
        except Exception as e:
            print(f"Lỗi khi lưu chunks vào Chroma: {e}")
            DB_DOCUMENTS_COLLECTION.update_one(
                {"session_id": session_id, "filename": os.path.basename(file_path)},
                {"$set": {"status": "error_vectorizing"}}
            )
    else:
        print("Không có chunks nào được tạo ra.")
        DB_DOCUMENTS_COLLECTION.update_one(
            {"session_id": session_id, "filename": os.path.basename(file_path)},
            {"$set": {"status": "error_no_chunks"}}
        )


# THAY THẾ hàm `delete_session_and_associated_files` trong file query_rag.py của bạn:

def delete_session_and_associated_files(session_id: str, user_id: str) -> dict:
    """
    Xóa 1 session và TẤT CẢ các file, chunks liên quan (bao gồm PDF và Ảnh).
    1. Tìm session, lấy ID ảnh.
    2. Tìm file PDF, lấy ID file PDF.
    3. Xóa tất cả file (Ảnh + PDF) khỏi GridFS.
    4. Xóa record trong 'sessions'.
    5. Xóa records trong 'documents'.
    6. Xóa chunks trong ChromaDB.
    """
    sessions_coll = get_mongo_collection("sessions")
    docs_coll = DB_DOCUMENTS_COLLECTION
    fs_client = FS
    chroma_temp = DB_CHROMA_TEMP

    if sessions_coll is None or fs_client is None or chroma_temp is None or docs_coll is None:
        raise Exception("Một hoặc nhiều thành phần DB (Mongo, GridFS, Chroma) chưa được khởi tạo")

    deleted_counts = {
        "sessions": 0,
        "document_records": 0,
        "gridfs_files": 0,
        "chroma_chunks": "N/A"
    }

    gridfs_ids_to_delete = []

    # --- Bước 1: Tìm session và thu thập ID ảnh TRƯỚC KHI XÓA ---
    try:
        session_doc = sessions_coll.find_one({"session_id": session_id, "user_id": user_id})
        if not session_doc:
            print(f"Không tìm thấy session {session_id} thuộc user {user_id} để xóa.")
            return deleted_counts

        # Thu thập image_gridfs_id từ messages
        for msg in session_doc.get("messages", []):
            if msg.get("image_gridfs_id"):
                try:
                    gridfs_ids_to_delete.append(ObjectId(msg["image_gridfs_id"]))
                except Exception as e:
                    print(f"Bỏ qua image_gridfs_id không hợp lệ: {msg['image_gridfs_id']}, lỗi: {e}")

        print(f"Tìm thấy {len(gridfs_ids_to_delete)} ảnh cần xóa từ session {session_id}.")

    except Exception as e:
        print(f"Lỗi khi tìm session doc hoặc thu thập ID ảnh: {e}")
        # Không dừng lại, vẫn tiếp tục xóa các thứ khác
        pass  # Chúng ta vẫn sẽ thử xóa dựa trên session_id

    # --- Bước 2: Thu thập ID file PDF (từ collection 'documents') ---
    try:
        doc_records = list(docs_coll.find({"session_id": session_id, "user_id": user_id}, {"gridfs_id": 1}))
        pdf_ids = []
        for doc in doc_records:
            if doc.get("gridfs_id"):
                try:
                    pdf_ids.append(ObjectId(doc["gridfs_id"]))
                except Exception as e:
                    print(f"Bỏ qua gridfs_id (PDF) không hợp lệ: {doc['gridfs_id']}, lỗi: {e}")

        print(f"Tìm thấy {len(pdf_ids)} file PDF cần xóa từ 'documents' cho session {session_id}.")
        gridfs_ids_to_delete.extend(pdf_ids)

    except Exception as mongo_e:
        print(f"Lỗi khi tìm file PDF trong 'documents': {mongo_e}")

    # --- Bước 3: Xóa tất cả file khỏi GridFS ---
    unique_ids_to_delete = list(set(gridfs_ids_to_delete))  # Tránh xóa trùng lặp
    for file_id in unique_ids_to_delete:
        try:
            fs_client.delete(file_id)
            deleted_counts["gridfs_files"] += 1
        except Exception as fs_e:
            print(f"Lỗi khi xóa file GridFS {file_id}: {fs_e}")

    print(f"Đã xóa tổng cộng {deleted_counts['gridfs_files']} file(s) (Ảnh + PDF) khỏi GridFS.")

    # --- Bước 4: Xóa record session ---
    session_delete_result = sessions_coll.delete_one({"session_id": session_id, "user_id": user_id})
    deleted_counts["sessions"] = session_delete_result.deleted_count
    print(f"Đã xóa {deleted_counts['sessions']} record(s) khỏi 'sessions'.")

    # --- Bước 5: Xóa records 'documents' (PDF) ---
    doc_delete_result = docs_coll.delete_many({"session_id": session_id, "user_id": user_id})
    deleted_counts["document_records"] = doc_delete_result.deleted_count
    print(f"Đã xóa {deleted_counts['document_records']} record(s) khỏi 'documents'.")

    # --- Bước 6: Xóa chunks khỏi ChromaDB ---
    try:
        chroma_temp.delete(where={"session_id": session_id})
        deleted_counts["chroma_chunks"] = "triggered"
        print(f"Đã kích hoạt xóa chunks cho session {session_id} khỏi Chroma.")
    except Exception as chroma_e:
        print(f"Lỗi khi xóa chunks khỏi Chroma: {chroma_e}")
        deleted_counts["chroma_chunks"] = f"error: {chroma_e}"

    return deleted_counts


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
def get_session_history(session_id: str, user_id: str):
    """Lấy lịch sử chat TRỰC TIẾP từ MongoDB cho user cụ thể."""
    print(f"--- DEBUG: Loading history for session '{session_id}' / user '{user_id}' from DB ---")
    return load_session_messages(session_id, user_id)


# ==============================================================================
# SECTION 3: CÁC HÀM TẠO CHAIN (CHAIN FACTORY FUNCTIONS)
# ==============================================================================


# --- PROMPTS ---
ROUTER_PROMPT_TEMPLATE = PromptTemplate.from_template("""
Bạn là AI phân loại câu hỏi. Dựa trên Lịch sử trò chuyện và Câu hỏi mới,
hãy phân loại câu hỏi vào MỘT trong ba loại sau:

1.  `rag_query`: Câu hỏi yêu cầu thông tin về quy trình, thủ tục, hoặc
    thông tin cụ thể (ví dụ: "Quy trình nghỉ phép là gì?", "TT07.03 nói về cái gì?",
    "thế còn nhân viên thử việc thì sao?").

2.  `history_query`: Câu hỏi về chính cuộc hội thoại
    (ví dụ: "bạn vừa nói gì?", "câu hỏi thứ 3 của tôi là gì?", "bạn có nhớ tôi không?").

3.  `file_rag_query`: Câu hỏi liên quan đến tài liệu, file (PDF) MÀ NGƯỜI DÙNG VỪA TẢI LÊN.
(ví dụ: "Tóm tắt file tôi vừa gửi", "file đó nói gì về X?", "trong tài liệu có nhắc đến Y không?").

Chỉ trả lời bằng MỘT từ duy nhất: `rag_query` hoặc `history_query` hoặc `file_rag_query`.

---
[Tình trạng file]
{file_status}
---
[Lịch sử trò chuyện]
{chat_history}
---
[Câu hỏi mới]
{question}
---
Phân loại (chỉ 1 từ):
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

Hãy trả lời bằng tiếng Việt một cách tự nhiên, chi tiết, chính xác và định dạng đẹp, dễ đọc.
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
Bạn là trợ lý AI. Nhiệm vụ của bạn là trả lời CÂU HỎI của người dùng.
Để trả lời, bạn phải sử dụng TẤT CẢ các thông tin sau:
1. HÌNH ẢNH được cung cấp (để xác định đối tượng).
2. BỐI CẢNH TÀI LIỆU (nội dung user guide) được cung cấp.
3. LỊCH SỬ TRÒ CHUYỆN (để hiểu bối cảnh).

Hãy phân tích HÌNH ẢNH, tìm thông tin liên quan trong BỐI CẢNH TÀI LIỆU, và trả lời CÂU HỎI.
Nếu bối cảnh không có thông tin, hãy trả lời dựa trên hình ảnh và kiến thức chung của bạn.

---
[Lịch sử trò chuyện]
{chat_history}
---
[Bối cảnh tài liệu (Từ file PDF và/hoặc DB chính)]
{context}
---
[Câu hỏi]
{question}
---
Câu trả lời chi tiết:
""")

FILE_RAG_PROMPT_TEMPLATE = PromptTemplate.from_template("""
Bạn là trợ lý AI. Nhiệm vụ của bạn là trả lời câu hỏi của người dùng
dựa trên NGỮ CẢNH (nội dung file PDF do người dùng tải lên).
Sử dụng LỊCH SỬ TRÒ CHUYỆN chỉ để hiểu bối cảnh (ví dụ: "cái đó" là gì).

Hãy trả lời bằng tiếng Việt, trích dẫn thông tin trực tiếp từ ngữ cảnh.
- Luôn trích dẫn nguồn từ NGỮ CẢNH (ví dụ: "(Nguồn: {source_file})").
- Nếu NGỮ CẢNH không có thông tin, hãy nói "Tôi không tìm thấy thông tin này trong file bạn đã tải lên.".

---
Lịch sử trò chuyện:
{chat_history}
---
Ngữ cảnh (Nội dung file PDF):
{context}
---
Câu hỏi: {question}
Câu trả lời chi tiết:
""")


def create_rag_router_chain(llm):
    """Tạo chain RAG có bộ định tuyến."""
    if llm is None :
        print("Lỗi: Không thể tạo RAG chain do thiếu LLM hoặc Retriever.")
        return None

    def get_history_for_request(session_id: str, user_id: str):
        return get_session_history(session_id, user_id)

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
    def route(input_dict, config=None):
        session_id = config["configurable"]["session_id"]

        # 1. Kiểm tra tình trạng file
        has_files = check_session_has_files(session_id)
        file_status = "Người dùng đã tải lên 1 file." if has_files else "Người dùng CHƯA tải lên file nào."

        # 2. Chạy router
        try:
            classification = router_chain.invoke({
                "chat_history": input_dict.get("chat_history", []),
                "question": input_dict["question"],
                "file_status": file_status
            }, config)
        except Exception as e:
            print(f"Lỗi khi chạy router: {e}. Mặc định dùng RAG chính.")
            classification = "rag_query"

        # 3. Trả về chain tương ứng
        if "history_query" in classification:
            print("--- (Router: Lịch sử) ---")
            return history_chain

        if "file_rag_query" in classification and has_files:
            print(f"--- (Router: File RAG session {session_id}) ---")

            # Tạo chain File RAG động (dynamic)
            # bằng cách gọi hàm get_file_retriever với session_id

            @functools.lru_cache(maxsize=1)
            def get_cached_file_docs(query):
                # cache 1 lần gọi cho mỗi câu hỏi
                retriever = get_file_retriever(session_id)
                return retriever.invoke(query)

            file_rag_chain = (
                    {"context": lambda x: format_docs(get_cached_file_docs(x["question"])),
                     "question": lambda x: x["question"],
                     "chat_history": lambda x: x.get("chat_history", []),
                     "source_file": lambda x: "File bạn đã tải lên"
                     }
                    | FILE_RAG_PROMPT_TEMPLATE
                    | llm
                    | StrOutputParser()
            )
            return file_rag_chain

        # Mặc định (hoặc khi router chọn rag_query)
        print("--- (Router: RAG Chính) ---")
        return rag_chain

    # --- Chain cơ sở có router ---
    base = (
            {"question": lambda x: x["question"],
             "chat_history": lambda x: x.get("chat_history", [])}
            | RunnableLambda(route)
    )

    # --- Bọc bộ nhớ ---
    chain_with_history = RunnableWithMessageHistory(
        base,
        get_history_for_request,
        input_messages_key="question",
        history_messages_key="chat_history",
        history_factory_config=[
            ConfigurableFieldSpec(id="user_id", annotation=str, name="User ID"),
            ConfigurableFieldSpec(id="session_id", annotation=str, name="Session ID"),
        ]
    )
    return chain_with_history


# --- CHAIN FACTORY: VISION ---
def create_vision_chain(llm):
    """Tạo chain Vision RAG (kết hợp) có bộ nhớ."""
    if llm is None:
        print("Lỗi: Không thể tạo Vision chain do thiếu LLM.")
        return None

    # --- Hàm format message (lồng bên trong) ---
    def _format_vision_rag_message(input_dict, config=None):
        session_id = config["configurable"]["session_id"]

        # 1. Lấy thông tin cơ bản
        history = input_dict.get("chat_history", [])
        question = input_dict["question"]
        img_path = input_dict["image_path"]

        # 2. LẤY BỐI CẢNH (RAG)
        context_docs = []
        has_files = check_session_has_files(session_id)

        # A. Tra cứu file PDF (RAG Động)
        if has_files:
            try:
                print(f"--- (Vision: Tra cứu File RAG session {session_id}) ---")
                # Dùng chính câu hỏi để tìm context trong file PDF
                file_retriever = get_file_retriever(session_id)
                context_docs.extend(file_retriever.invoke(question))
            except Exception as e:
                print(f"Lỗi khi tra cứu file RAG cho Vision: {e}")

        # B. Tra cứu DB chính (RAG Chính)
        try:
            print("--- (Vision: Tra cứu RAG Chính) ---")
            context_docs.extend(get_retrieved_docs(question))
        except Exception as e:
            print(f"Lỗi khi tra cứu RAG chính cho Vision: {e}")

        # Dùng hàm format_docs (đã sửa)
        formatted_context = format_docs(context_docs)

        # 3. Tạo Prompt
        prompt_text = VISION_PROMPT_TEMPLATE.invoke({
            "question": question,
            "chat_history": history,
            "context": formatted_context
        }).to_string()

        # 4. Chuyển ảnh sang base64
        image_base64 = image_to_base64(img_path)
        if not image_base64:
            return [HumanMessage(content=f"(Lỗi ảnh) {prompt_text}")]

        image_data = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}

        # 5. Trả về HumanMessage (gồm Text + Ảnh)
        return [HumanMessage(content=[{"type": "text", "text": prompt_text}, image_data])]

    # Hàm này dùng để lưu lại lịch sử (giữ nguyên)
    def _format_history_input(input_dict):
        question = input_dict["question"]
        img_path = input_dict["image_path"]
        image_base64 = image_to_base64(img_path)
        if not image_base64: return HumanMessage(content=f"(Lỗi ảnh) {question}")
        image_data = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        return HumanMessage(content=[{"type": "text", "text": question}, image_data])

    def get_history_for_request(session_id: str, user_id: str):
        return get_session_history(session_id, user_id)

    # --- Chain cơ sở ---
    # Thay _format_vision_message bằng _format_vision_rag_message
    base_vision = RunnablePassthrough() | RunnableLambda(_format_vision_rag_message) | llm

    # --- Bọc bộ nhớ ---
    vision_chain_with_history = RunnableWithMessageHistory(
        base_vision,
        get_history_for_request,
        input_messages_key="question",
        input_messages_key_fx=RunnableLambda(_format_history_input),
        history_messages_key="chat_history",
        history_factory_config=[
            ConfigurableFieldSpec(id="user_id", annotation=str, name="User ID"),
            ConfigurableFieldSpec(id="session_id", annotation=str, name="Session ID"),
        ]
    )
    return vision_chain_with_history


# ==============================================================================
# SECTION 4: KHỞI TẠO CHAIN TOÀN CỤC (ĐỂ API SỬ DỤNG)
# ==============================================================================

# Gọi các hàm factory để tạo chain sẵn sàng cho API import
RAG_CHAIN_WITH_HISTORY = create_rag_router_chain(TEXT_LLM)
VISION_CHAIN_WITH_HISTORY = create_vision_chain(VISION_LLM)


# ==============================================================================
# SECTION 5: CÁC HÀM XỬ LÝ CLI (COMMAND-LINE INTERFACE)
# ==============================================================================

def handle_text_query(query_text, user_id, session_id="default_session"):
    print("--- 🔍 Đang xử lý câu hỏi văn bản bằng RAG ---")

    chain_to_run = RAG_CHAIN_WITH_HISTORY

    if chain_to_run is None:
        print("Lỗi: RAG Chain chưa được khởi tạo.")
        return

    full_response = ""
    config_ = {"configurable": {"session_id": session_id, "user_id": user_id}}
    input_data = {"question": query_text}

    try:
        for chunk in chain_to_run.stream(input_data, config=config_):
            full_response += chunk
            print(chunk, end="", flush=True)
        print("\n")
        # Lưu vào DB sau khi stream xong
        save_session_message(session_id, user_id, query_text, full_response)
    except Exception as e:
        print(f"\nLỗi khi xử lý câu hỏi text: {e}")


def handle_multimodal_query(query_text, image_path, user_id, session_id="default_session"):
    print(f"--- 🖼️ Xử lý câu hỏi có ảnh: {os.path.basename(image_path)} ---")

    chain_to_run = VISION_CHAIN_WITH_HISTORY

    if chain_to_run is None:
        print("Lỗi: Vision Chain chưa được khởi tạo.")
        return

    full_response = ""
    input_data = {"question": query_text, "image_path": image_path}
    config_ = {"configurable": {"session_id": session_id, "user_id": user_id}}

    try:
        for chunk in chain_to_run.stream(input_data, config=config_):
            content = chunk.content
            full_response += content
            print(content, end="", flush=True)
        print("\n")
        # Lưu vào DB sau khi stream xong
        save_session_message(session_id, user_id, query_text, full_response, image_path=image_path)
    except Exception as e:
        print(f"\nLỗi khi xử lý câu hỏi ảnh: {e}")


def handle_pdf_upload(pdf_path: str, session_id: str, user_id: str):
    """Quy trình xử lý khi người dùng tải lên 1 file PDF."""
    print(f"\n⏳ Đang xử lý file: {pdf_path}...")
    try:
        # 1. Lưu file vào Mongo (GridFS + 'documents' collection)
        file_id = save_pdf_to_mongo(pdf_path, session_id, user_id)

        if file_id:
            # 2. Phân tích và vector hóa file
            # (Hàm này chạy nền, nhưng CLI sẽ đợi)
            process_and_vectorize_pdf(pdf_path, session_id, user_id)
            print("✅ Xử lý và vector hóa file PDF thành công.")
        else:
            print("❌ Lỗi khi lưu file vào DB.")

    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng khi xử lý file PDF: {e}")


# ==============================================================================
# SECTION 6: HÀM MAIN CHO CLI
# ==============================================================================

def main():
    print("🤖 Chatbot CUSC (MongoDB) sẵn sàng!")
    print("=" * 30)
    print("[1] Tạo session mới")
    print("[2] Tiếp tục session cũ")

    session_id = None
    user_id = "69023a7b6c98b8abb985500a"
    choice = input("Lựa chọn của bạn (1 hoặc 2): ").strip()

    if choice == '2':
        # --- Logic tiếp tục session ---
        print("\nĐang tải các session gần đây...")
        sessions = list_sessions(limit=10, user_id=user_id)  # Lấy 10 session gần nhất

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
    print("   Gõ 'exit' để thoát.")
    print("   Gõ 'pdf' để tải file PDF mới.\n")

    # Tải lịch sử ngay khi bắt đầu (để chat_history không bị rỗng)
    get_session_history(session_id, user_id)

    while True:
        print("-" * 20)
        user_input = input("👤 Bạn hỏi (hoặc gõ 'pdf'): ")

        if user_input.lower() == "exit":
            print("Tạm biệt!")
            break

        # --- LUỒNG MỚI: TẢI PDF ---
        if user_input.lower() == "pdf":
            pdf_path = input("📂 Nhập đường dẫn PDF: ").strip()
            if pdf_path and os.path.exists(pdf_path):
                # Xử lý file
                handle_pdf_upload(pdf_path, session_id, user_id)
            else:
                print(f"⚠️ Không tìm thấy file tại '{pdf_path}'")
            continue

        query_text = user_input
        image_path = input("🖼️ Nhập đường dẫn ảnh (Enter nếu không có): ").strip()
        print("\n💡 Trả lời:")

        if image_path and os.path.exists(image_path):
            handle_multimodal_query(query_text, image_path, user_id, session_id)
        elif image_path:
            print(f"⚠️ Không tìm thấy ảnh tại '{image_path}'")
        else:
            handle_text_query(query_text, user_id, session_id)


if __name__ == "__main__":
    main()
