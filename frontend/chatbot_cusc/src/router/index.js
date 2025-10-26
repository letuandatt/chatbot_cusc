// src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'
// Import các view (sẽ tạo ở bước sau)
import ChatView from '../views/ChatView.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import ProfileView from '../views/ProfileView.vue'
// Import Pinia store để kiểm tra trạng thái đăng nhập
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/',
    name: 'Chat',
    component: ChatView,
    meta: { requiresAuth: true } // Route này yêu cầu đăng nhập
  },
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
    meta: { requiresGuest: true } // Route này chỉ cho khách (chưa đăng nhập)
  },
  {
    path: '/register',
    name: 'Register',
    component: RegisterView,
    meta: { requiresGuest: true } // Route này chỉ cho khách
  },
    {
        path: '/profile',
        name: "Profile",
        component: ProfileView,
        meta: { requiresAuth: true }
    },
   // Bắt các route không tồn tại, chuyển về trang Chat (nếu đã đăng nhập) hoặc Login
   { path: '/:pathMatch(.*)*', redirect: to => {
       const authStore = useAuthStore();
       return authStore.isAuthenticated ? '/' : '/login';
     }
   }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Navigation Guard: Bảo vệ route
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore() // Lấy store

  // Dùng !! để ép kiểu sang boolean
  const isAuthenticated = !!authStore.token

  if (to.meta.requiresAuth && !isAuthenticated) {
    // Nếu cần đăng nhập mà chưa có token -> Về trang Login
    console.log('Navigation Guard: requiresAuth failed, redirecting to Login');
    next({ name: 'Login' })
  } else if (to.meta.requiresGuest && isAuthenticated) {
     // Nếu chỉ cho khách mà đã đăng nhập -> Về trang Chat
     console.log('Navigation Guard: requiresGuest failed, redirecting to Chat');
    next({ name: 'Chat' })
  } else {
    // Cho phép đi tiếp
    next()
  }
})

export default router