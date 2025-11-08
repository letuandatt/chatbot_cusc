# Backend: FastAPI API Server

Phần backend của CUSC Chatbot đóng vai trò là **API Gateway**, được xây dựng trên nền **FastAPI**.  
Thành phần này chịu trách nhiệm xử lý logic nghiệp vụ, xác thực người dùng và cung cấp dữ liệu cho frontend.

---

## 🏛️ Kiến trúc Hệ thống

Cấu trúc server được tổ chức theo mô hình module (router) nhằm đảm bảo khả năng mở rộng và bảo trì dễ dàng.

- **`main.py`** – Điểm khởi tạo (entrypoint) chính, cấu hình ứng dụng FastAPI và nạp các router.  
- **`models.py`** – Khai báo toàn bộ mô hình dữ liệu sử dụng Pydantic để xác thực dữ liệu vào/ra.  
- **`config.py`** – Chứa các hằng số và thông số cấu hình chung (ví dụ: múi giờ `VN_TZ`).  
- **`routers/`** – Thư mục chứa logic nghiệp vụ chính:
  - **`auth.py`** – Xử lý đăng ký (`/register`) và đăng nhập (`/token`).  
  - **`user.py`** – Quản lý hồ sơ người dùng, thay đổi mật khẩu và kiểm tra trạng thái xử lý tệp (`/user/document/status`).  
  - **`session.py`** – Quản lý lịch sử hội thoại (tạo, xóa, đổi tên, liệt kê).  
  - **`chat.py`** – Cung cấp các endpoint RAG (`/chat/text`, `/chat/image`, `/upload_pdf`).  

---

## ✨ Tính năng Chính

### 1. Xử lý PDF bằng BackgroundTasks

Khi người dùng tải lên tệp PDF qua endpoint `/upload_pdf`:

1. API phản hồi ngay lập tức với mã trạng thái `200 OK` để tránh chờ đợi.  
2. Một tiến trình nền (`BackgroundTasks`) được kích hoạt.  
3. Tiến trình này gọi hàm `process_and_vectorize_pdf` trong `chatbot/query_rag.py` để xử lý và lưu trữ dữ liệu.

### 2. Xác thực bằng JWT

Hệ thống áp dụng **JSON Web Tokens (JWT)** để quản lý xác thực và phân quyền.

- File `chatbot/auth_utils.py` cung cấp các hàm như `create_access_token`, `verify_password`, ...  
- Router `auth.py` đảm nhiệm việc cấp phát token.  
- Các endpoint quan trọng (`chat.py`, `user.py`, `session.py`) đều được bảo vệ thông qua `Depends(get_current_user_id)`.

### 3. Cơ chế Polling API

Để frontend theo dõi trạng thái xử lý tệp PDF, backend cung cấp endpoint:  
`GET /user/document/status`  

Endpoint này cho phép frontend truy vấn trạng thái tệp dựa trên `filename` và `session_id`, ví dụ:  
- `processing` – Đang xử lý.  
- `processed` – Hoàn tất xử lý.  
- `error_parsing` – Lỗi khi trích xuất nội dung.

---

## 🚀 Hướng dẫn Cài đặt và Khởi chạy

### 1. Dịch vụ Nền (Prerequisites)

Trước khi khởi động FastAPI, cần đảm bảo các dịch vụ sau đang hoạt động:

1. **MongoDB Server** – Cơ sở dữ liệu chính của hệ thống.  
2. **ChromaDB Server** – Cơ sở dữ liệu vector cho RAG. Khởi động bằng lệnh:
   ```bash
   chroma run --host 127.0.0.1 --port 8001 --path "./chatbot/vectorstores/chroma_db_2"
   ```
   *(Tham số `--path` xác định vị trí lưu trữ vector, tính từ thư mục gốc dự án.)*

### 2. Cài đặt Python

Từ thư mục gốc của dự án, tạo và kích hoạt môi trường ảo:

```bash
python -m venv .venv
source .venv/bin/activate  # Đối với Linux/Mac
.\.venv\Scripts ctivate   # Đối với Windows
```

### 3. Thiết lập Biến Môi trường

1. Tạo file `.env` (có thể sao chép từ `.env.example` nếu có).  
2. Đảm bảo các biến sau được cấu hình đầy đủ:

```ini
# Khóa API cho các dịch vụ RAG
GOOGLE_API_KEY=
COHERE_API_KEY=
LLAMA_CLOUD_API_KEY=

# Thông tin kết nối MongoDB
MONGO_URI=
MONGO_DB_NAME=

# Cấu hình JWT
SECRET_KEY="your_super_secret_key_for_jwt"
```

### 4. Khởi động Server FastAPI

Thực thi lệnh sau từ thư mục gốc dự án:

```bash
uvicorn backend.main:app --reload --port 8000
```

Sau khi khởi động, backend sẽ lắng nghe tại địa chỉ:  
👉 `http://localhost:8000`

