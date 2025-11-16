# Chatbot Core: AI & RAG Logic

Thư mục này là **thành phần lõi (core)** của toàn bộ hệ thống chatbot.  
Nó **không phải là một máy chủ độc lập**, mà là một **thư viện Python** chứa toàn bộ logic RAG, được **backend (FastAPI)** import và sử dụng.

---

## 🏛️ Cấu trúc Thành phần

- **`query_rag.py`** – Thành phần trung tâm, chứa toàn bộ logic RAG, kiến trúc Agent và các hàm xử lý tệp.
- **`agents.py`** – Tập lệnh điều phối quá trình xử lý và nạp dữ liệu PDF (`extract_data.py`) vào ChromaDB (`create_database.py`).
- **`create_database.py`** – Triển khai hàm `create_data` phục vụ việc nạp dữ liệu tri thức chung (Global) vào ChromaDB.
- **`extract_data.py`** – Bao gồm các hàm `llama_parse_md` và `fix_first_roman_headings` để trích xuất và chuẩn hóa văn bản.
- **`config.py`** – Quản lý các hằng số cấu hình (API keys, tên mô hình, đường dẫn cơ sở dữ liệu).
- **`auth_utils.py`** – Cung cấp các hàm tiện ích để xử lý JWT (tạo hash, xác minh token).

---

## ✨ Logic RAG Cốt lõi (`query_rag.py`) - Kiến trúc Agent

Hệ thống RAG sử dụng kiến trúc sang Agent (tác tử). Agent có khả năng tự suy luận (reasoning) và chọn công cụ (tool calling) phù hợp dựa trên hướng dẫn.
Hệ thống Agent sử dụng các công cụ sau:

### 1. Tool: tool_search_general_policy (Kho tri thức chung)

- **Mục tiêu:** Giải đáp các câu hỏi tổng quát liên quan đến quy trình hoặc thông tin nội bộ của CUSC.
- **Cách hoạt động:**
  1. Tool này được Agent gọi khi câu hỏi liên quan đến quy trình chung  
  2. Nó thực thi logic của GLOBAL_RETRIEVER (được bọc trong get_retrieved_docs).
  3. Logic này bao gồm tìm kiếm k=40 tài liệu, sau đó dùng Cohere Rerank để chọn top_n=6 và sử dụng Redis Cache để tăng tốc.

### 2. Tool: tool_search_uploaded_file (Kho tri thức động)

- **Mục tiêu:** Giải đáp các câu hỏi liên quan đến tệp PDF do người dùng tải lên.
- **Cách hoạt động:**
  1. Tool này được Agent gọi khi câu hỏi nhắc đến "file" hoặc "tài liệu vừa gửi".  
  2. Nó yêu cầu tham số session_id để đảm bảo bảo mật dữ liệu.  
  3. Nó sử dụng hàm get_file_retriever(session_id) để tìm kiếm vector trong collection temp_docs_cusc và lọc theo đúng session_id của người dùng.

### 3. Agent Executor – Bộ điều phối Tác tử

- **Thành phần:** `RAG_AGENT_EXECUTOR`.  
- **Cách hoạt động:**
  1. Khi nhận câu hỏi, hàm _prepare_agent_input sẽ "tiêm" session_id vào câu hỏi (dưới dạng [Ghi chú Hệ thống: session_id là: ...]) và giữ nguyên chat_history.  
  2. AgentExecutor nhận input đã xử lý và lịch sử trò chuyện.  
  3. Dựa trên AGENT_SYSTEM_PROMPT, Agent tự suy luận xem có cần gọi tool hay không.
  4. Nếu là câu hỏi về file, Agent sẽ gọi tool_search_uploaded_file và phải truyền session_id (lấy từ Ghi chú Hệ thống trong prompt).
  5. Nếu là câu hỏi chung, Agent gọi tool_search_general_policy.
  6. Nếu là chào hỏi, Agent tự trả lời mà không dùng tool.
  7. Cuối cùng, Agent tổng hợp kết quả từ tool (nếu có) để trả lời người dùng.

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

