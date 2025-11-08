# Frontend: Ứng dụng Vue.js 3

Đây là giao diện người dùng (UI) cho CUSC Chatbot, được xây dựng bằng Vue 3, Vite, và Pinia.

## 🏛️ Cấu trúc Dự án

-   **`public/`**: Chứa các tài sản tĩnh (assets).
-   **`src/`**: Mã nguồn chính của ứng dụng.
    -   **`main.js`**: Điểm vào, khởi tạo Vue, Pinia, và Router.
    -   **`style.css`**: CSS toàn cục.
    -   **`api.js`**: Nơi quản lý việc gọi API.
    -   **`router/index.js`**: Định nghĩa các route (trang) và "navigation guards" (bảo vệ route, yêu cầu đăng nhập).
    -   **`stores/auth.js`**: Pinia store, quản lý trạng thái đăng nhập và lưu/xóa JWT token khỏi `localStorage`.
    -   **`components/`**: Các thành phần tái sử dụng.
        -   `ChatWindow.vue`: Cửa sổ chat chính.
        -   `SessionList.vue`: Thanh sidebar quản lý các phiên chat.
        -   `MessageBubble.vue`: Bong bóng tin nhắn (render Markdown bằng `DOMPurify` để chống XSS).
    -   **`views/`**: Các "trang" chính được router sử dụng.
        -   `ChatView.vue`: Trang chat chính (chứa `SessionList` và `ChatWindow`).
        -   `LoginView.vue`, `RegisterView.vue`, `ProfileView.vue`, `FileListView.vue`.

## ✨ Logic Cốt lõi (Frontend)

### 1. Quản lý Xác thực (Authentication)

-   Khi user đăng nhập (tại `LoginView.vue`), `stores/auth.js` được gọi.
-   Nó gửi request đến `POST /api/token`.
-   Nếu thành công, token JWT được lưu vào `localStorage`.
-   `api.js` sử dụng `axios.interceptors` để tự động đính kèm token này vào *mọi* request API sau đó.
-   Nếu API trả về lỗi 401 (token hết hạn), interceptor sẽ tự động bắt lỗi và gọi `authStore.logout()`.

### 2. Trải nghiệm Người dùng (UX)

-   **Không Tải lại trang (No Reload):** Trong `ChatView.vue`, khi người dùng chọn session mới, app không dùng `window.location.reload()`. Thay vào đó, nó cập nhật `prop`, và component `ChatWindow.vue` sử dụng `watch` để tải session mới.
-   **Streaming Phản hồi:** `ChatWindow.vue` sử dụng `fetch` và `ReadableStream` để nhận và hiển thị câu trả lời của bot (từ `/chat/text`) theo từng từ, thay vì chờ toàn bộ câu.

### 3. Logic Polling (Theo dõi Xử lý PDF)

Đây là logic phức tạp nhất của frontend, đảm bảo người dùng biết khi nào file của họ được xử lý xong (sau khi roll back về `BackgroundTasks`).

1.  Trong `ChatWindow.vue`, người dùng chọn 1 file PDF.
2.  Hàm `uploadPdfInternal` được gọi.
3.  Biến `isProcessingPDF` được set thành `true`, làm vô hiệu hóa nút "Send".
4.  API `uploadPdf` (gọi `POST /api/upload_pdf`) được gọi. Nó trả về 200 OK gần như ngay lập tức.
5.  **Quan trọng:** Ngay sau đó, hàm `pollPdfStatus` (hàm mới) được kích hoạt.
6.  Hàm này gọi API `checkPdfStatus` (gọi `GET /api/user/document/status`) mỗi 3 giây.
7.  Nó cập nhật `fileName` để hiển thị tiến trình (ví dụ: "Đang xử lý (20%): ...").
8.  Chỉ khi API polling trả về `processed` (hoặc `error`), biến `isProcessingPDF` mới được set về `false`, kích hoạt lại nút "Send".

## 🚀 Hướng dẫn Cài đặt & Chạy

1.  **Cài đặt Dependencies:**
    * (Đảm bảo bạn đã cài đặt Node.js 18+)
    * `cd` vào thư mục `frontend/chatbot_cusc` (nếu bạn đang ở thư mục gốc).
    ```bash
    npm install
    ```

2.  **Cấu hình Proxy (Vite):**
    * Ứng dụng này sử dụng proxy của Vite để chuyển tiếp các yêu cầu API (tránh lỗi CORS).
    * Đảm bảo file `vite.config.js` của bạn có cấu hình proxy để chuyển `/api` đến `http://localhost:8000` (nơi backend đang chạy).
    ```js
    // vite.config.js
    export default defineConfig({
      // ...
      server: {
        proxy: {
          '/api': {
            target: 'http://localhost:8000', // Backend FastAPI
            changeOrigin: true,
          }
        }
      }
    })
    ```

3.  **Khởi động Server Dev:**
    ```bash
    npm run dev
    ```

4.  Truy cập ứng dụng tại `http://localhost:5173` (hoặc cổng mà Vite hiển thị).