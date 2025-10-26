<template>
  <div class="profile-view">
    <div class="profile-card">
      <img src="../assets/20181031cusc.png" alt="Logo" class="profile-logo">
      <h1>Thông tin tài khoản</h1>

      <div v-if="loading" class="loading-indicator">Đang tải...</div>
      <div v-if="error" class="error-message">{{ error }}</div>

      <div v-if="userProfile" class="profile-details">
        <p><strong>Tên:</strong> {{ userProfile.name }}</p>
        <p><strong>Email:</strong> {{ userProfile.email }}</p>
        <p><strong>Ngày tạo:</strong> {{ formatDate(userProfile.created_at) }}</p>
        </div>

      <p class="placeholder-text">(Các chức năng chỉnh sửa mật khẩu, thông tin khác sẽ được thêm vào sau)</p>

      <div class="profile-actions">
        <router-link to="/" class="btn ghost">Quay lại Chat</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useAuthStore } from '../stores/auth';
import { api } from '../api'; // Import instance axios đã cấu hình
import router from '../router';

const authStore = useAuthStore();
const userProfile = ref(null);
const loading = ref(false);
const error = ref(null);

// Hàm gọi API lấy thông tin user
const fetchUserProfile = async () => {
  loading.value = true;
  error.value = null;
  try {
    // Gọi API /user/me (axios interceptor sẽ tự thêm token)
    const response = await api.get('/user/me');
    userProfile.value = response.data;
  } catch (err) {
    console.error("Error fetching user profile:", err);
    error.value = err.response?.data?.detail || err.message || "Không thể tải thông tin tài khoản.";
    // Nếu lỗi 401, interceptor sẽ tự logout
  } finally {
    loading.value = false;
  }
};

// Gọi API khi component được tạo
onMounted(() => {
  fetchUserProfile();
});

// Hàm format ngày tháng (tương tự SessionList)
const formatDate = (isoString) => {
   if (!isoString) return 'N/A';
      try {
        const date = new Date(isoString);
        return date.toLocaleString('vi-VN', { /* ... options ... */ });
      } catch { return isoString; }
};

// Hàm đăng xuất
const logout = () => {
  authStore.logout();
};
</script>

<style scoped>
.profile-view {
  display: flex;
  justify-content: center;
  align-items: flex-start; /* Căn thẻ card lên trên */
  padding-top: 5vh; /* Khoảng cách từ top */
  min-height: 100vh;
  background-color: var(--bg-primary);
  color: var(--text-primary);
}

.profile-card {
  background-color: var(--bg-secondary);
  padding: 35px 45px;
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-md);
  width: 100%;
  max-width: 550px; /* Rộng hơn form login */
  text-align: center;
}

.profile-logo {
  height: 45px;
  margin-bottom: 20px;
}

.profile-card h1 {
  margin-bottom: 30px;
  font-weight: 500;
  font-size: 1.5rem;
}

.loading-indicator {
  color: var(--text-secondary);
  margin: 20px 0;
}

.error-message { /* Style giống form login */
  color: #f87171;
  background-color: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.3);
  padding: 12px;
  border-radius: var(--border-radius-base);
  font-size: 0.9rem;
  margin: 20px 0;
}

.profile-details {
  margin: 25px 0;
  text-align: left;
  border-top: 1px solid var(--border-color);
  border-bottom: 1px solid var(--border-color);
  padding: 20px 0;
}
.profile-details p {
  margin-bottom: 12px;
  font-size: 1rem;
  color: var(--text-secondary);
}
.profile-details strong {
  color: var(--text-primary);
  margin-right: 8px;
  min-width: 120px; /* Căn chỉnh label */
  display: inline-block;
}

.placeholder-text {
  font-style: italic;
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-top: 25px;
}

.profile-actions {
  margin-top: 30px;
  display: flex;
  justify-content: center;
  gap: 15px;
}
.profile-actions .btn,
.profile-actions button,
.profile-actions a {
    font-size: 0.9rem;
    padding: 8px 16px;
}
</style>