// src/main.js
import { createApp } from 'vue'
import { createPinia } from 'pinia' // Import Pinia
import router from './router'       // Import router
import './style.css'
import App from './App.vue'
// Bỏ dòng này nếu bạn không dùng store trực tiếp ở đây
// import { useAuthStore } from './stores/auth'

const app = createApp(App)
const pinia = createPinia() // Tạo instance Pinia

app.use(pinia) // Sử dụng Pinia
app.use(router) // Sử dụng Router

// Bỏ phần initializeAuth ở đây, Interceptor sẽ xử lý
// const authStore = useAuthStore()
// authStore.initializeAuth()

app.mount('#app')