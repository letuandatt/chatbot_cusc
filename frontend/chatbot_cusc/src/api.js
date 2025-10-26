// src/api.js
import axios from 'axios'
import { useAuthStore } from './stores/auth' // Import Pinia store
import router from './router';

// Lấy BASE_URL từ Vite proxy config
// Khi gọi API, chỉ cần gọi /sessions, /chat/text,... proxy sẽ thêm http://localhost:8000
const API_BASE_URL = '/api'; // Sử dụng proxy prefix

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000 // Tăng timeout
})

// --- Axios Request Interceptor ---
// Tự động thêm token Authorization vào header
api.interceptors.request.use(
  (config) => {
    // Lấy store bên trong interceptor
    const authStore = useAuthStore()
    const token = authStore.token
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
      // console.log('Interceptor: Added Auth token to request header');
    } else {
      // console.log('Interceptor: No token found');
    }
    return config
  },
  (error) => {
    console.error('Request Interceptor Error:', error);
    return Promise.reject(error)
  }
)

// --- Axios Response Interceptor ---
// Tự động logout nếu gặp lỗi 401 Unauthorized
api.interceptors.response.use(
  (response) => {
    return response // Trả về response nếu thành công (status 2xx)
  },
  (error) => {
    // Chỉ xử lý lỗi response từ server
    if (error.response && error.response.status === 401) {
      console.error('Response Interceptor Error:', error.response.status, error.response.data);
      if (error.response.status === 401) {
        // Nếu nhận lỗi 401
        console.warn("API 401 -> Logging out.");
        const authStore = useAuthStore()
        // Kiểm tra xem có đang ở trang login không để tránh vòng lặp logout
        if (router.currentRoute.value.name !== 'Login') {
          authStore.logout()
        }
      }
    } else if (error.request) {
       // Lỗi không nhận được response (network error, timeout)
       console.error('Network/Request Error:', error.message);
    } else {
       // Lỗi khác
       console.error('Axios Error:', error.message);
    }
    return Promise.reject(error) // Chuyển tiếp lỗi để component có thể bắt
  }
)


// --- Các hàm API cũ (Sessions, Chat) ---
// Giữ nguyên các hàm này. Interceptor sẽ tự thêm token.
export const listSessions = (limit = 50) => api.get(`/sessions?limit=${limit}`).then(r => r.data)
export const viewSession = (sessionId) => api.get(`/session/${sessionId}`).then(r => r.data)
export const createSession = () => api.post('/session/new').then(r => r.data)
export const deleteSession = (sessionId) => api.delete(`/session/${sessionId}/delete`).then(r => r.data)
export const deleteAllSessions = () => api.delete('/sessions/all').then(r => r.data)
export const renameSession = (sessionId, newName) => {
  return api.put(`/session/${sessionId}/rename`, { new_name: newName }).then(r => r.data);
}
export const deleteCurrentUserAccount = () => api.delete('/user/me').then(r => r.data)

// Lưu ý: Các hàm gọi chat (streamChatText, streamChatImage)
// nên được chuyển từ ChatWindow.vue sang đây để tái sử dụng
// và để interceptor hoạt động đúng với fetch API.
// Tuy nhiên, để đơn giản, tạm thời giữ chúng trong ChatWindow.vue
// nhưng cần đảm bảo chúng cũng gửi token.

// Ví dụ hàm chatText API (không dùng fetch trực tiếp trong component)
/*
export const streamChatTextAPI = async (question, sessionId, onChunk, onError, onDone) => {
  try {
    const form = new FormData();
    form.append('question', question);
    form.append('session_id', sessionId);

    // Gọi qua instance api đã có interceptor
    const response = await api.post('/chat/text', form, {
      responseType: 'stream' // Yêu cầu axios xử lý stream (cần xem lại cách axios xử lý)
      // HOẶC dùng fetch nhưng lấy token từ store:
      // headers: { 'Authorization': `Bearer ${useAuthStore().token}` }
    });

    // Xử lý stream response từ axios/fetch ở đây
    // ... gọi onChunk(chunk), onDone(), onError(err) ...

  } catch (err) {
    onError(err);
  }
};
*/