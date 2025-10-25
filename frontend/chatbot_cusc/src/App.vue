<template>
  <div class="app">
    <SessionList
        :current="currentSession"
        @select="onSelectSession"
        @created="onCreated"
        @refresh="refresh"
        @deleteAll="onDeleteAll"/>
    <ChatWindow
        :key="currentSession"
        :initialSessionId="currentSession"
        @deselect-session="onDeselectSession"/>
  </div>
</template>

<script>
import SessionList from './components/SessionList.vue'
import ChatWindow from './components/ChatWindow.vue'

export default {
  components: { SessionList, ChatWindow },
  data(){ return { currentSession: localStorage.getItem('current_session') || null } },
  methods:{
    onSelectSession(id){
      this.currentSession = id
      if (id) {
        localStorage.setItem('current_session', id)
      }
      else {
        localStorage.removeItem('current_session')
      }
      // reload page to pass prop — alternative: use event bus; easiest is to refresh
      window.location.reload()
    },
    onCreated(id){
      this.currentSession = id
      localStorage.setItem('current_session', id)
      window.location.reload()
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
      // :key="currentSession" sẽ tự động re-render ChatWindow về trạng thái chào mừng
    }
  }
}
</script>
