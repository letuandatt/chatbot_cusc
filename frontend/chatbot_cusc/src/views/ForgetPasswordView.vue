<template>
  <div class="auth-page">
    <div class="auth-form">
      <img src="../assets/20181031cusc.png" alt="Logo" class="auth-logo">
      <h2>ChatCUSC</h2>
      <form @submit.prevent="handleLogin">
        <div class="form-group">
          <label for="email">Email:</label>
          <input type="email" id="email" v-model="email" required autocomplete="email">
        </div>
        <div v-if="authStore.error" class="error-message">
          {{ authStore.error }}
        </div>
        <button type="submit" class="btn auth-btn" :disabled="authStore.loading">
          {{ authStore.loading ? 'Đang xử lý...' : 'Gửi' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth' // Dùng @/ để import từ gốc src

const email = ref('')
const password = ref('')
const authStore = useAuthStore()

const handleLogin = async () => {
  // await authStore.login(email.value, password.value)
  // Router guard sẽ tự động chuyển hướng nếu thành công
}
</script>

<style scoped>
/* Thêm CSS cho trang Login/Register */
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

.forgot-password {
  margin-top: 20px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.forgot-password a {
  color: var(--bg-accent);
  text-decoration: none;
  font-weight: 500;
}
.forgot-password a:hover {
  text-decoration: underline;
}
</style>