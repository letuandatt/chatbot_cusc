<template>
  <div class="profile-view">
    <div class="profile-card">
      <div class="profile-actions">
        <router-link to="/" class="btn ghost">Quay lại</router-link>
      </div>
      <img alt="Logo" class="profile-logo" src="../assets/20181031cusc.png">
      <h1>Thông tin tài khoản</h1>

      <div v-if="loading" class="loading-indicator">Đang tải...</div>
      <div v-if="error" class="error-message">{{ error }}</div>

      <div v-if="userProfile" class="profile-details">
        <p>
          <strong>Tên:</strong>
          <span>
            {{ userProfile.name || 'Chưa cập nhật' }}
            <button name="Cập nhật tên" class="btn-edit" @click="promptRename">✏️</button>
          </span>
        </p>
        <p>
          <strong>Email:</strong>
          <span>{{ userProfile.email }}</span>
        </p>
        <p>
          <strong>Ngày tạo:</strong>
          <span>{{ formatDate(userProfile.created_at) }}</span>
        </p>
      </div>

      <form @submit.prevent="handleChangePassword" class="change-password-form">
        <h3>Đổi mật khẩu</h3>
        <div class="form-group">
          <label for="currentPassword">Mật khẩu hiện tại:</label>
          <input type="password" id="currentPassword" v-model="currentPassword" required autocomplete="current-password">
        </div>
        <div class="form-group">
          <label for="newPassword">Mật khẩu mới (ít nhất 8 ký tự):</label>
          <input type="password" id="newPassword" v-model="newPassword" required autocomplete="new-password">
        </div>
        <div class="form-group">
          <label for="confirmNewPassword">Xác nhận mật khẩu mới:</label>
          <input type="password" id="confirmNewPassword" v-model="confirmNewPassword" required autocomplete="new-password">
        </div>
        <div v-if="changePasswordStatus.error" class="error-message">
          {{ changePasswordStatus.error }}
        </div>
         <div v-if="changePasswordStatus.success" class="success-message">
          {{ changePasswordStatus.success }}
        </div>
        <button type="submit" class="btn auth-btn" :disabled="changePasswordStatus.loading">
          {{ changePasswordStatus.loading ? 'Đang xử lý...' : 'Đổi mật khẩu' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, reactive } from 'vue';
import { useAuthStore } from '../stores/auth';
import { api, changeUserPassword, changUserName } from '../api';

export default {
  name: 'UserProfile',

  setup() {
    const authStore = useAuthStore();
    const userProfile = ref(null);
    const loading = ref(false);
    const error = ref(null);

    const currentPassword = ref('');
    const newPassword = ref('');
    const confirmNewPassword = ref('');

    const newName = ref('');
    const changeNameStatus = reactive({
      loading: false,
      error: null,
      success: null,
    });

    const changePasswordStatus = reactive({
      loading: false,
      error: null,
      success: null,
    });

    // Lấy thông tin user
    const fetchUserProfile = async () => {
      loading.value = true;
      error.value = null;
      try {
        const response = await api.get('/user/me');
        userProfile.value = response.data;
      } catch (err) {
        console.error("Error fetching user profile:", err);
        error.value = err.response?.data?.detail || err.message || "Không thể tải thông tin tài khoản.";
      } finally {
        loading.value = false;
      }
    };

    // Gọi khi mount
    onMounted(() => {
      fetchUserProfile();
    });

    // Format ngày
    const formatDate = (isoString) => {
      if (!isoString) return 'N/A';
      try {
        const date = new Date(isoString);
        return date.toLocaleString('vi-VN', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });
      } catch {
        return isoString;
      }
    };

    // Đổi mật khẩu
    const handleChangePassword = async () => {
      changePasswordStatus.loading = true;
      changePasswordStatus.error = null;
      changePasswordStatus.success = null;

      if (newPassword.value !== confirmNewPassword.value) {
        changePasswordStatus.error = "Mật khẩu mới và xác nhận không khớp.";
        changePasswordStatus.loading = false;
        return;
      }

      if (newPassword.value.length < 8) {
        changePasswordStatus.error = "Mật khẩu mới phải có ít nhất 8 ký tự.";
        changePasswordStatus.loading = false;
        return;
      }

      try {
        const result = await changeUserPassword(currentPassword.value, newPassword.value);
        changePasswordStatus.success = result.message || "Đổi mật khẩu thành công!";
        currentPassword.value = '';
        newPassword.value = '';
        confirmNewPassword.value = '';
      } catch (err) {
        console.error("Error changing password:", err);
        changePasswordStatus.error = err.response?.data?.detail || err.message || "Đổi mật khẩu thất bại.";
      } finally {
        changePasswordStatus.loading = false;
      }
    };

    const promptRename = () => {
      if (!userProfile.value) return;

      // Xóa thông báo cũ
      changeNameStatus.error = null;
      changeNameStatus.success = null;

      const currentName = userProfile.value.name || '';
      const newNameInput = prompt("Nhập tên mới của bạn:", currentName);

      if (newNameInput === null) {
        // User nhấn "Cancel"
        return;
      }

      const trimmedNewName = newNameInput.trim();

      if (!trimmedNewName) {
        changeNameStatus.error = "Tên không được để trống.";
        return;
      }

      if (trimmedNewName === currentName) {
        changeNameStatus.error = "Tên mới phải khác tên hiện tại.";
        return;
      }

      // Gán tên mới và gọi hàm xử lý
      newName.value = trimmedNewName;
      handleChangeName();
    };

    const handleChangeName = async () => {
      // Sửa: Dùng `changeNameStatus` (đã được định nghĩa)
      changeNameStatus.loading = true;
      changeNameStatus.error = null;
      changeNameStatus.success = null;

      if (!newName.value.trim()) {
        changeNameStatus.error = "Tên mới không được để trống.";
        changeNameStatus.loading = false;
        return;
      }

      // Sửa: Lấy tên hiện tại từ userProfile đã fetch
      const currentName = userProfile.value.name || '';

      try {
        const result = await changUserName(currentName, newName.value);
        changeNameStatus.success = result.message || "Cập nhật tên thành công!";

        // Cập nhật lại local store
        if (authStore.user) {
          authStore.user.name = newName.value;
        }
        // Cập nhật UI ngay lập tức
        if (userProfile.value) {
            userProfile.value.name = newName.value;
        }

        newName.value = ''; // Xóa tên mới sau khi thành công
      } catch (err) {
        changeNameStatus.error = err.response?.data?.detail || "Lỗi khi đổi tên người dùng.";
      } finally {
        changeNameStatus.loading = false;
      }
    };

    // Đăng xuất
    const logout = () => {
      authStore.logout();
    };

    // Trả ra biến và hàm cho template
    return {
      authStore,
      userProfile,
      loading,
      error,
      currentPassword,
      newPassword,
      confirmNewPassword,
      changePasswordStatus,
      fetchUserProfile,
      handleChangePassword,
      promptRename,
      formatDate,
      logout,
    };
  },
};
</script>

<style scoped>
.profile-view {
  display: flex;
  justify-content: center;
  align-items: flex-start; /* Căn thẻ card lên trên */
  padding: 5vh 20px; /* Padding tổng thể */
  min-height: 100vh;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  overflow-y: auto; /* Cho phép cuộn nếu cần */
}

.profile-card {
  background-color: var(--bg-secondary);
  padding: 25px 40px; /* Padding cân đối */
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-md);
  width: 100%;
  max-width: 500px; /* Giảm max-width chút */
  text-align: center;

  max-height: 88vh;
  overflow-y: auto;
}

.profile-logo {
  height: 40px;
  margin-bottom: 20px;
}

.profile-card h1 {
  margin-bottom: 25px;
  font-weight: 600; /* Đậm hơn */
  font-size: 1.6rem;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-color); /* Thêm đường kẻ dưới title */
  padding-bottom: 15px; /* Khoảng cách với đường kẻ */
}

/* --- Phần hiển thị thông tin User --- */
.profile-details {
  margin: 30px 0;
  text-align: left;
  font-size: 1rem; /* Cỡ chữ thông tin */
}
.profile-details p {
  display: flex; /* Dùng flex để căn lề label và value */
  justify-content: space-between; /* Đẩy value sang phải */
  margin-bottom: 15px; /* Khoảng cách giữa các dòng */
  padding-bottom: 10px; /* Khoảng cách với đường kẻ dưới (nếu có) */
  border-bottom: 1px dashed var(--border-color); /* Đường kẻ đứt nhẹ */
}
.profile-details p:last-child {
  margin-bottom: 0;
  border-bottom: none; /* Bỏ đường kẻ dòng cuối */
}
.profile-details strong {
  color: var(--text-secondary); /* Label màu nhạt hơn */
  font-weight: 500;
  margin-right: 15px; /* Khoảng cách giữa label và value */
  flex-shrink: 0; /* Không cho label co lại */
}
/* Giá trị (email, ngày tạo) */
.profile-details span {
    color: var(--text-primary);
    word-break: break-all; /* Cho phép xuống dòng nếu email/ID quá dài */
}


/* --- Form đổi mật khẩu --- */
.change-password-form {
  margin-top: 30px;
  padding-top: 25px;
  border-top: 1px solid var(--border-color); /* Đường kẻ trên form */
  text-align: left;
}
.change-password-form h3 {
  text-align: center;
  margin-bottom: 25px;
  font-weight: 500;
  font-size: 1.25rem; /* Cỡ chữ title form */
  color: var(--text-primary);
}

/* Style chung cho form group */
.form-group {
  margin-bottom: 18px; /* Khoảng cách form group */
}
.form-group label {
  display: block;
  margin-bottom: 7px;
  color: var(--text-secondary);
  font-size: 0.9rem;
  font-weight: 500;
}
.form-group input[type="password"],
.form-group input[type="email"] /* Áp dụng cho cả input email (nếu có form đổi email sau này) */
 {
  width: 100%;
  padding: 11px 15px; /* Padding input */
  border-radius: var(--border-radius-base);
  border: 1px solid var(--border-color);
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-size: 1rem;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.form-group input[type="password"]:focus,
.form-group input[type="email"]:focus {
  border-color: var(--bg-accent);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25); /* Focus ring rõ hơn */
}

/* Thông báo lỗi và thành công */
.error-message, .success-message {
  padding: 10px 15px;
  border-radius: var(--border-radius-base);
  font-size: 0.9rem;
  margin: 10px 0 18px 0; /* Điều chỉnh margin */
  text-align: center;
}
.error-message {
  color: #fca5a5; /* Màu chữ đỏ nhạt */
  background-color: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
}
.success-message {
  color: #6ee7b7; /* Màu chữ xanh lá nhạt */
  background-color: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

/* Nút Đổi mật khẩu */
.auth-btn {
  width: 100%;
  padding: 11px;
  font-size: 1rem;
  margin-top: 8px; /* Giảm margin top */
}

/* Text placeholder */
.placeholder-text {
  font-style: italic;
  color: var(--text-secondary);
  font-size: 0.85rem;
  margin-top: 25px; /* Giữ khoảng cách với nút */
}

/* Nút actions cuối trang */
.profile-actions {
  margin-top: 5px; /* Khoảng cách với placeholder */
  display: flex;
  gap: 15px;
  margin-bottom: 30px;
}
.profile-actions .btn { /* Áp dụng chung cho các nút/link ở đây */
    font-size: 0.9rem;
    padding: 8px 18px; /* Padding nút */
}

.btn-edit {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 0.9rem; /* Cỡ icon */
  padding: 8px;
  margin-left: auto; /* Đẩy nút sửa và xóa về cuối */
  opacity: 0.6;
  transition: opacity 0.2s, color 0.2s;
}
.btn-edit:hover {
  opacity: 1;
  color: var(--bg-accent); /* Màu xanh khi hover */
}

.name-status {
  margin-top: 15px;
  margin-bottom: 0;
}
</style>