# Chatbot Core: AI & RAG Logic

Thư mục này là **thành phần lõi (core)** của toàn bộ hệ thống chatbot.  
Nó **không phải là một máy chủ độc lập**, mà là một **thư viện Python** chứa toàn bộ logic RAG, được **backend (FastAPI)** import và sử dụng.

---

## 🏛️ Cấu trúc Thành phần

- **`query_rag.py`** – Thành phần trung tâm, chứa toàn bộ logic RAG, các chuỗi xử lý (chain) và hàm xử lý tệp.
- **`agents.py`** – Tập lệnh điều phối quá trình xử lý và nạp dữ liệu PDF (`extract_data.py`) vào ChromaDB (`create_database.py`).
- **`create_database.py`** – Triển khai hàm `create_data` phục vụ việc nạp dữ liệu tri thức chung (Global) vào ChromaDB.
- **`extract_data.py`** – Bao gồm các hàm `llama_parse_md` và `fix_first_roman_headings` để trích xuất và chuẩn hóa văn bản.
- **`config.py`** – Quản lý các hằng số cấu hình (API keys, tên mô hình, đường dẫn cơ sở dữ liệu).
- **`auth_utils.py`** – Cung cấp các hàm tiện ích để xử lý JWT (tạo hash, xác minh token).

---

## ✨ Logic RAG Cốt lõi (`query_rag.py`)

Hệ thống RAG sử dụng một **bộ định tuyến (Router)** để xác định nguồn tri thức phù hợp cho mỗi truy vấn.

### 1. Global Retriever – Kho tri thức chung

- **Mục tiêu:** Giải đáp các câu hỏi tổng quát liên quan đến quy trình hoặc thông tin nội bộ của CUSC.  
- **Thành phần:** `GLOBAL_RETRIEVER` (được bọc trong get_retrieved_docs).  
- **Cách hoạt động:**
  1. Dữ liệu được nạp một lần thông qua `agents.py` → `create_database.py` vào collection `docs_cusc` trong ChromaDB.  
  2. Khi một truy vấn được gửi đến get_retrieved_docs, hệ thống đầu tiên sẽ kiểm tra Redis Cache.
  3. Hệ thống tìm `k=40` đoạn văn bản liên quan.  
  4. Sau đó sử dụng **Cohere Rerank** để sắp xếp và chọn ra `top_n=6` kết quả chính xác nhất.
  5. Kết quả top_n=6 này được lưu vào Redis (với CACHE_EXPIRATION_SECONDS) để sử dụng cho các lần truy vấn tương tự trong tương lai.

### 2. Dynamic Retriever – Kho tri thức động

- **Mục tiêu:** Giải đáp các câu hỏi liên quan đến tệp PDF do người dùng tải lên.  
- **Thành phần:** Hàm `get_file_retriever(session_id)`.  
- **Cách hoạt động:**
  1. Khi người dùng tải tệp, hàm `process_and_vectorize_pdf` xử lý nội dung và lưu vector vào collection `temp_docs_cusc`.  
  2. Mỗi vector được gắn metadata `{"session_id": "..."}`.  
  3. Hàm `get_file_retriever` chỉ tìm kiếm trong `temp_docs_cusc`, đồng thời lọc kết quả theo `session_id` hiện tại.

### 3. RAG Router – Bộ định tuyến truy vấn

- **Thành phần:** `RAG_CHAIN_WITH_HISTORY`.  
- **Cách hoạt động:**
  1. Khi nhận câu hỏi, hệ thống yêu cầu mô hình ngôn ngữ (Gemini) phân loại loại truy vấn bằng prompt `ROUTER_PROMPT_TEMPLATE`.  
  2. Kiểm tra xem phiên hiện tại có tệp PDF đã tải lên hay không (`check_session_has_files`).  
  3. Dựa trên kết quả phân loại, truy vấn sẽ được định tuyến đến một trong ba chain:
     - `file_rag_query`: Nếu truy vấn liên quan đến tệp PDF.  
     - `rag_query`: Nếu truy vấn mang tính tổng quát.  
     - `history_query`: Nếu truy vấn liên quan đến lịch sử trò chuyện.

---

## 📄 Quy trình Xử lý PDF (LlamaParse)

Hệ thống sử dụng **LlamaParse** để trích xuất nội dung và cấu trúc (bao gồm bảng biểu) từ tệp PDF.  
Quy trình được thực thi thông qua `BackgroundTasks` trong backend.

Hàm `process_and_vectorize_pdf` bao gồm các bước:

1. **Load:** Sử dụng `LlamaParse` (chế độ agent, model `config.LLAMA_PARSE_MODEL`) để trích xuất tệp PDF thành Markdown.  
2. **Fix:** Chuẩn hóa tiêu đề La Mã (I, II, III...) bằng hàm `fix_first_roman_headings`.  
3. **Split:** Thực hiện tách dữ liệu theo chiến lược "hybrid-split":  
   - Tách cấu trúc: Dựa trên `MarkdownHeaderTextSplitter` (các heading `#`, `##`).  
   - Tách ngữ nghĩa: Dựa trên `SemanticChunker` để phân chia đoạn văn theo ý nghĩa.  
4. **Embed & Store:** Nhúng (embed) các đoạn đã tách và lưu vào ChromaDB (`temp_docs_cusc`) cùng `session_id`.  
5. **Update Status:** Cập nhật trạng thái xử lý (`processing`, `processed`, `error_parsing`, ...) vào collection `documents` của MongoDB.

---

## 🚀 Hướng dẫn Xây dựng Kho Tri thức (Lần đầu)

Để chatbot có thể trả lời các truy vấn chung, cần khởi tạo dữ liệu nền cho RAG.

1. **Yêu cầu hệ thống:**
   - MongoDB Server (phải đang chạy để query_rag.py kết nối).
   - Redis server (phải đang chạy để query_rag.py kết nối cache)

2. **Cài đặt phụ thuộc:**
   ```bash
   # (Đã kích hoạt môi trường ảo .venv)
   pip install -r requirements.txt
   ```
3. **Chuẩn bị dữ liệu:**
   - Đặt tất cả tệp PDF (ví dụ: `TT07_*.pdf`) vào thư mục `data/`.
4. **Khởi động các dịch vụ nền:**
   - (Mở Terminal 1) Khởi động Redis Server: (Cách 1: Dùng Docker - khuyến nghị)
   ```bash
   docker run -d --name my-redis-cache -p 6379:6379 redis:latest
   ```
   (Cách 2: Cài đặt trực tiếp)
   ```bash
   redis-server
   ```
   - (Mở Terminal 2) Khởi động ChromaDB server:
   ```bash
   chroma run --host 127.0.0.1 --port 8001 --path "./chatbot/vectorstores/chroma_db_2"
   ```
5. **Nạp dữ liệu vào ChromaDB:**
   ```bash
   python agents.py
   ```

---

## ⌨️ Chạy Chatbot ở Chế độ CLI

Để kiểm thử nhanh logic RAG mà không cần khởi động toàn bộ hệ thống:

1. Đảm bảo ChromaDB Server đang chạy.  
2. Đảm bảo dữ liệu nền đã được nạp bằng `agents.py`.  
3. Thực thi lệnh:
   ```bash
   python chatbot/query_rag.py
   ```
4. Làm theo hướng dẫn trên terminal để tạo session và bắt đầu trò chuyện.

