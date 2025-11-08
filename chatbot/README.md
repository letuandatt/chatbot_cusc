# Chatbot Core: AI & RAG Logic

Đây là "bộ não" của toàn bộ dự án. Thư mục này **không phải là một server chạy độc lập**, mà là một "thư viện" Python chứa tất cả logic RAG, được `backend` (FastAPI) import và sử dụng.

## 🏛️ Cấu trúc

-   **`query_rag.py`**: File quan trọng nhất, chứa toàn bộ logic RAG, các chain, và hàm xử lý file.
-   **`agents.py`**: Script (chạy 1 lần) để điều phối việc xử lý PDF (`extract_data.py`) và nạp chúng vào ChromaDB (`create_database.py`).
-   **`create_database.py`**: Chứa logic `create_data` để nạp dữ liệu chung (Global) vào ChromaDB.
-   **`extract_data.py`**: Chứa hàm `llama_parse_md` và `fix_first_roman_headings`.
-   **`config.py`**: Quản lý các hằng số (API keys, tên model, đường dẫn DB).
-   **`auth_utils.py`**: Các hàm tiện ích để xử lý JWT (tạo hash, verify token).

## ✨ Logic RAG Cốt lõi (trong `query_rag.py`)

Hệ thống RAG của chúng ta sử dụng một "Router" (Bộ định tuyến) để quyết định nguồn tri thức nào cần dùng cho câu trả lời.

### 1. Global Retriever (Kho tri thức chung)

-   **Mục tiêu:** Trả lời các câu hỏi chung về quy trình của CUSC.
-   **Thành phần:** `GLOBAL_RETRIEVER`.
-   **Cách hoạt động:**
    1.  Dữ liệu được nạp 1 lần từ `agents.py` -> `create_database.py` vào collection `docs_cusc` trong ChromaDB.
    2.  Khi truy vấn, nó tìm `k=40` chunk liên quan.
    3.  Nó dùng `CohereRerank` để sắp xếp lại và chỉ lấy `top_n=6` chunk chính xác nhất.

### 2. Dynamic Retriever (Kho tri thức động)

-   **Mục tiêu:** Trả lời các câu hỏi về file PDF mà người dùng vừa tải lên.
-   **Thành phần:** Hàm `get_file_retriever(session_id)`.
-   **Cách hoạt động:**
    1.  Khi người dùng tải file, hàm `process_and_vectorize_pdf` sẽ xử lý và lưu vector vào collection `temp_docs_cusc`.
    2.  **Quan trọng:** Mỗi vector được gắn metadata `{"session_id": "..."}`.
    3.  Hàm `get_file_retriever` tạo ra một retriever chỉ tìm kiếm trong `temp_docs_cusc` VÀ **lọc (filter)** theo `session_id` của người dùng hiện tại.

### 3. RAG Router (Bộ định tuyến)

-   **Thành phần:** `RAG_CHAIN_WITH_HISTORY`.
-   **Cách hoạt động:**
    1.  Khi nhận câu hỏi, nó hỏi LLM (Gemini) một câu hỏi phân loại (sử dụng `ROUTER_PROMPT_TEMPLATE`).
    2.  Nó kiểm tra xem session này có file không (`check_session_has_files`).
    3.  Dựa trên câu trả lời, nó sẽ "lái" câu hỏi của người dùng đến 1 trong 3 chain:
        -   `file_rag_query` (Nếu hỏi về file): Dùng **Dynamic Retriever**.
        -   `rag_query` (Nếu hỏi chung): Dùng **Global Retriever**.
        -   `history_query` (Nếu hỏi lịch sử): Chỉ dùng bộ nhớ.

## 📄 Quy trình Xử lý PDF (Trích xuất Nâng cao - LlamaParse)

Hệ thống này sử dụng **LlamaParse** để trích xuất văn bản và cấu trúc (như bảng) từ file PDF. Quy trình này được gọi bởi `BackgroundTasks` trong API backend.

Hàm `process_and_vectorize_pdf` thực hiện:

1.  **Load (Tải):** Dùng `LlamaParse` với chế độ agent (`parse_page_with_agent`) và model (`config.LLAMA_PARSE_MODEL`) để gọi API bên ngoài, trích xuất PDF thành Markdown.
2.  **Fix (Sửa):** Áp dụng hàm `fix_first_roman_headings` để chuẩn hóa các tiêu đề La Mã (I, II, III...) về cấp `<h1>`.
3.  **Split (Tách):** Sử dụng chiến lược "hybrid-split":
    * Tách lần 1 (Cấu trúc): Dùng `MarkdownHeaderTextSplitter` để tách file theo các heading `#`, `##`.
    * Tách lần 2 (Ngữ nghĩa): Dùng `SemanticChunker` để tách các khối text lớn (giữa các heading) thành các chunk nhỏ hơn về mặt ngữ nghĩa.
4.  **Embed & Store (Nhúng & Lưu):** Nhúng (embed) các chunk và lưu vào ChromaDB (collection `temp_docs_cusc`) với `session_id`.
5.  **Update Status:** Cập nhật trạng thái (`processing`, `processed`, `error_parsing`...) vào collection `documents` của MongoDB.

## 🚀 Hướng dẫn: Xây dựng Kho tri thức (Lần đầu)

Để chatbot có thể trả lời các câu hỏi chung (Global RAG), bạn phải nạp dữ liệu cho nó 1 lần.

1.  **Cài đặt Dependencies:**
    ```bash
    # (Đã kích hoạt .venv từ thư mục gốc)
    pip install -r requirements.txt
    ```
2.  **Chuẩn bị Dữ liệu:**
    * Đặt tất cả các file PDF (ví dụ 7 file `TT07...pdf`) vào thư mục `data/`.

3.  **Khởi động ChromaDB Server:**
    * (Bắt buộc) Mở một terminal và chạy (giữ cho nó chạy):
    ```bash
    chroma run --host 127.0.0.1 --port 8001 --path "./chatbot/vectorstores/chroma_db_2"
    ```

4.  **Chạy Script Nạp Dữ liệu:**
    * Mở một terminal **khác** (đã kích hoạt `.venv`).
    * Chạy script `agents.py`. Script này sẽ (1) gọi LlamaParse để xử lý file PDF trong `data/` và (2) nạp vector vào ChromaDB.
    ```bash
    python agents.py
    ```

## ⌨️ Chạy Chatbot (Chế độ CLI)

Để kiểm tra nhanh logic RAG mà không cần chạy Backend/Frontend, bạn có thể dùng file `query_rag.py` như một script:

1.  (Đảm bảo ChromaDB Server đang chạy).
2.  (Đảm bảo bạn đã chạy `agents.py` ít nhất 1 lần).
3.  Chạy lệnh:
    ```bash
    python chatbot/query_rag.py
    ```
4.  Làm theo hướng dẫn trên terminal để tạo session mới và bắt đầu chat.