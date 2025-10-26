// src/stores/auth.js
import { defineStore } from 'pinia'
import axios from 'axios' // Cần axios để gọi API login/register
import router from '../router' // Import router để điều hướng sau khi login/logout

// Lấy BASE_URL từ Vite proxy config hoặc định nghĩa ở đây
// Lưu ý: Khi gọi API từ frontend, KHÔNG cần '/api' prefix nữa vì proxy đã xử lý
const API_BASE_URL = '/api'; // Để trống nếu dùng proxy, hoặc 'http://localhost:8000' nếu không dùng

export const useAuthStore = defineStore('auth', {
  // 1. STATE: Lưu token lấy từ localStorage khi khởi tạo
  state: () => ({
    token: localStorage.getItem('access_token') || null,
    error: null,
    loading: false,
  }),

  // 2. GETTERS: Tính toán trạng thái đăng nhập
  getters: {
    isAuthenticated: (state) => !!state.token,
  },

  // 3. ACTIONS: Thực hiện login, register, logout
  actions: {
    // Hàm nội bộ để cập nhật token và localStorage
    _setToken(newToken) {
      this.token = newToken
      if (newToken) {
        localStorage.setItem('access_token', newToken)
        // Không cần set header mặc định ở đây, Interceptor sẽ làm (Bước 4)
      } else {
        localStorage.removeItem('access_token')
      }
    },

    // Action Đăng nhập
    async login(email, password) {
      this.loading = true
      this.error = null
      try {
        // Sử dụng FormData vì backend FastAPI dùng OAuth2PasswordRequestForm
        const formData = new FormData();
        formData.append('username', email); // FastAPI dùng 'username' cho email trong form này
        formData.append('password', password);

        // Gọi API login (lưu ý không có '/api' prefix)
        const response = await axios.post(`${API_BASE_URL}/token`, formData, {
           headers: { 'Content-Type': 'application/x-www-form-urlencoded' } // Quan trọng: Đổi content-type
        });

        const accessToken = response.data.access_token;
        if (!accessToken) {
            throw new Error("Đăng nhập thất bại: Không nhận được token.");
        }
        this._setToken(accessToken); // Lưu token
        localStorage.removeItem('current_session');
        await router.push('/'); // Chuyển hướng về trang Chat
        return true; // Thành công
      } catch (err) {
        console.error("Lỗi Đăng nhập:", err);
        this.error = err.response?.data?.detail || err.message || 'Đăng nhập thất bại';
        this._setToken(null); // Xóa token nếu lỗi
        return false; // Thất bại
      } finally {
        this.loading = false;
      }
    },

    // Action Đăng ký
    async register(email, password) {
       this.loading = true;
       this.error = null;
       try {
         // Gọi API register (lưu ý không có '/api' prefix)
         const response = await axios.post(`${API_BASE_URL}/register`, { email, password });
         console.log("Đăng ký thành công:", response.data);
         // Tùy chọn: Có thể tự động đăng nhập sau khi đăng ký thành công
         // return await this.login(email, password);
         return true; // Thành công
       } catch (err) {
         console.error("Lỗi Đăng ký:", err);
         this.error = err.response?.data?.detail || err.message || 'Đăng ký thất bại';
         return false; // Thất bại
       } finally {
         this.loading = false;
       }
    },

    // Action Đăng xuất
    logout() {
      console.log("Đang đăng xuất...");
      this._setToken(null) // Xóa token
      localStorage.removeItem('current_session');
      // Có thể thêm logic gọi API backend /logout nếu cần (để thu hồi token phía server)
      router.push('/login'); // Chuyển hướng về trang Login
    },
  },
})