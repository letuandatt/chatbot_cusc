<template>
  <div class="app">
    <SessionList
        v-if="!isSidebarCollapsed"
        :current="currentSession"
        @select="onSelectSession"
        @created="onCreated"
        @deleteAll="onDeleteAll"
        @logout="handleLogout"
        @toggle="toggleSidebar"
    />

    <ChatWindow
        :initialSessionId="currentSession"
        :is-sidebar-collapsed="isSidebarCollapsed"
        @deselect-session="onDeselectSession"
        @toggle-sidebar="toggleSidebar"
    />
  </div>
</template>

<script>
import SessionList from '../components/SessionList.vue'
import ChatWindow from '../components/ChatWindow.vue'
import { useAuthStore } from "../stores/auth.js";

export default {
  name: "ChatView",
  components: { SessionList, ChatWindow },
  data(){
    return {
      currentSession: localStorage.getItem('current_session') || null,
      // Thêm state để quản lý việc thu gọn, đọc từ localStorage
      isSidebarCollapsed: JSON.parse(localStorage.getItem('sidebar_collapsed') || 'false')
    }
  },
  methods:{
    onSelectSession(id){
      this.currentSession = id
      if (id) {
        localStorage.setItem('current_session', id)
      }
      else {
        localStorage.removeItem('current_session')
      }
    },
    onCreated(id){
      this.currentSession = id
      localStorage.setItem('current_session', id)
    },
    onDeleteAll(){
      console.log("App: All sessions deleted");
      this.currentSession = null; // Cập nhật data
      localStorage.removeItem('current_session');
    },
    refresh(){
      window.location.reload()
    },
    onDeselectSession() {
      console.log("App: Deselecting session");
      this.currentSession = null; // Xóa session hiện tại trong data
      localStorage.removeItem('current_session'); // Xóa khỏi localStorage
    },
    handleLogout(){
      if (confirm("Are u sure you want to logout?")) {
        const authStore = useAuthStore();
        authStore.logout();
      }
    },
    // Thêm hàm này: Bật/tắt thanh bên và lưu vào localStorage
    toggleSidebar() {
      this.isSidebarCollapsed = !this.isSidebarCollapsed;
      localStorage.setItem('sidebar_collapsed', JSON.stringify(this.isSidebarCollapsed));
    }
  }
}
</script>