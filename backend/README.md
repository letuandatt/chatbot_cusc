# Backend: FastAPI API Server

Chào mừng bạn đến với server Backend của CUSC Chatbot. Đây là một API Gateway được xây dựng bằng FastAPI, chịu trách nhiệm xử lý logic nghiệp vụ, xác thực, và cung cấp dữ liệu cho Frontend.

## 🏛️ Kiến trúc

Server này được cấu trúc theo các module (router) để dễ dàng bảo trì:

-   **`main.py`**: Điểm vào (entrypoint) chính, khởi tạo app FastAPI và include các router.
-   **`models.py`**: Chứa tất cả các mô hình Pydantic (validation data).
-   **`config.py`**: Chứa các hằng số cấu hình (như múi giờ `VN_TZ`).
-   **`routers/`**: Thư mục chứa logic nghiệp vụ chính:
    -   **`auth.py`**: Xử lý đăng ký (`/register`) và đăng nhập (`/token`).
    -   **`user.py`**: Quản lý hồ sơ người dùng, đổi mật khẩu, và chứa API kiểm tra trạng thái file (`/user/document/status`).
    -   **`session.py`**: Quản lý lịch sử chat (tạo, xóa, đổi tên, liệt kê).
    -   **`chat.py`**: Xử lý các endpoint RAG (`/chat/text`, `/chat/image`, `/upload_pdf`).

## ✨ Tính năng Cốt lõi

### 1. Xử lý PDF (BackgroundTasks)

Khi người dùng upload một file PDF qua endpoint `/upload_pdf`:

1.  API **ngay lập tức** trả về 200 OK cho frontend.
2.  Một tác vụ nền (`BackgroundTasks`) được kích hoạt.
3.  Tác vụ này gọi hàm `process_and_vectorize_pdf` (từ `chatbot/query_rag.py`) để xử lý file.

### 2. Xác thực (JWT)

Hệ thống sử dụng JWT (JSON Web Tokens) để xác thực.

-   File `chatbot/auth_utils.py` cung cấp các hàm `create_access_token`, `verify_password`, v.v.
-   Router `auth.py` sử dụng chúng để cấp token.
-   Tất cả các endpoint quan trọng (như trong `chat.py`, `user.py`, `session.py`) đều được bảo vệ bằng `Depends(get_current_user_id)`.

### 3. API Polling

Để frontend biết khi nào `BackgroundTasks` xử lý PDF xong, backend cung cấp endpoint:
`GET /user/document/status`

Endpoint này cho phép frontend "hỏi" trạng thái của file (ví dụ: `processing`, `processed`, `error_parsing`), dựa trên `filename` và `session_id`.

## 🚀 Hướng dẫn Cài đặt & Chạy

Để chạy server Backend, bạn cần đảm bảo các dịch vụ (services) nền đã chạy.

### 1. Điều kiện tiên quyết (Services)

Trước khi chạy FastAPI, hãy đảm bảo 2 dịch vụ sau đang chạy:

1.  **MongoDB Server:** Khởi động dịch vụ MongoDB của bạn.
2.  **ChromaDB Server:** (Bắt buộc) Mở một terminal và chạy server ChromaDB.
    ```bash
    chroma run --host 127.0.0.1 --port 8001 --path "./chatbot/vectorstores/chroma_db_2"
    ```
    *(Lưu ý: `--path` là đường dẫn đến nơi bạn muốn lưu trữ vector, tính từ thư mục gốc của dự án)*

### 2. Cài đặt Python

Đứng từ thư mục gốc, tạo và kích hoạt môi trường ảo:
```bash
python -m venv .venv
source .venv/bin/activate  # (Linux/Mac)
.\.venv\Scripts\activate   # (Windows)
```

### 3. Cấu hình Biến môi trường

1.  Tạo file `.env` (từ file `.env.example` nếu có).
2.  Đảm bảo các biến sau được thiết lập:
    ```ini
    # Dùng cho RAG (chatbot/query_rag.py)
    GOOGLE_API_KEY="AIzaSy..."
    COHERE_API_KEY="your_cohere_key"
    LLAMA_CLOUD_API_KEY="llm_..." # (Mặc dù PyMuPDF thay thế LlamaParse, config này có thể vẫn được dùng)

    # Dùng cho MongoDB (chatbot/query_rag.py)
    MONGO_URI="mongodb://localhost:27017/"
    MONGO_DB_NAME="Chatbot_CUSC"

    # Dùng cho JWT (chatbot/auth_utils.py)
    SECRET_KEY="your_super_secret_key_for_jwt"
    ```

### 4. Khởi động Server

Chạy Uvicorn từ thư mục gốc của dự án:

```bash
uvicorn backend.main:app --reload --port 8000