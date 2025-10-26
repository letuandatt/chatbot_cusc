<template>
  <div class="auth-page">
    <div class="auth-form">
      <img src="../assets/20181031cusc.png" alt="Logo" class="auth-logo">
      <h2>Đăng ký tài khoản</h2>
      <form @submit.prevent="handleRegister">
        <div class="form-group">
          <label for="email">Email:</label>
          <input type="email" id="email" v-model="email" required autocomplete="email">
        </div>
        <div class="form-group">
          <label for="password">Mật khẩu (ít nhất 8 ký tự):</label>
          <input type="password" id="password" v-model="password" required autocomplete="new-password">
        </div>
        <div class="form-group">
          <label for="password">Xác nhận mật khẩu:</label>
          <input type="password" id="confirmPassword" v-model="confirmPassword" required autocomplete="new-password">
        </div>
         <div v-if="authStore.error" class="error-message">
          {{ authStore.error }}
        </div>
        <button type="submit" class="btn auth-btn" :disabled="authStore.loading">
          {{ authStore.loading ? 'Đang xử lý...' : 'Đăng ký' }}
        </button>
      </form>
      <p class="switch-auth">
        Đã có tài khoản? <router-link to="/login">Đăng nhập</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import router from '../router' // Import router để chuyển hướng sau khi đăng ký

const email = ref('')
const password = ref('')
const confirmPassword = ref('') // Nếu có ô xác nhận
const authStore = useAuthStore()

const handleRegister = async () => {
  if (password.value !== confirmPassword.value) {
    authStore.error = "Mật khẩu xác nhận không khớp.";
    return;
  }
  authStore.error = null;
  const success = await authStore.register(email.value, password.value)
  if (success) {
    alert('Đăng ký thành công! Vui lòng đăng nhập.');
    router.push('/login'); // Chuyển hướng đến trang đăng nhập
  }
}
</script>

<style scoped>
.auth-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background-color: var(--bg-primary);
}
.auth-form {
  background-color: var(--bg-secondary);
  padding: 40px 50px;
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-md);
  width: 100%;
  max-width: 420px;
  text-align: center;
}
.auth-logo {
  height: 50px;
  margin-bottom: 25px;
}
.auth-form h2 {
  color: var(--text-primary);
  margin-bottom: 30px;
  font-weight: 500;
}
.form-group {
  margin-bottom: 20px;
  text-align: left;
}
.form-group label {
  display: block;
  margin-bottom: 8px;
  color: var(--text-secondary);
  font-size: 0.9rem;
}
.form-group input {
  width: 100%;
  padding: 12px 15px;
  border-radius: var(--border-radius-base);
  border: 1px solid var(--border-color);
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-size: 1rem;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.form-group input:focus {
  border-color: var(--bg-accent);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
}
.error-message {
  color: #f87171; /* Màu đỏ lỗi */
  background-color: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.3);
  padding: 10px;
  border-radius: var(--border-radius-base);
  font-size: 0.85rem;
  margin-bottom: 20px;
  text-align: center;
}
.auth-btn {
  width: 100%;
  padding: 12px;
  font-size: 1rem;
  margin-top: 10px;
}
.switch-auth {
  margin-top: 25px;
  font-size: 0.9rem;
  color: var(--text-secondary);
}
.switch-auth a {
  color: var(--bg-accent);
  text-decoration: none;
  font-weight: 500;
}
.switch-auth a:hover {
  text-decoration: underline;
}
</style>