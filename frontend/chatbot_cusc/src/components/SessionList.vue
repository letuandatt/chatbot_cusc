<template>
  <div class="sessions">
    <div class="sidebar-header">
      <div class="btn-group">
        <button class="btn" @click="createNew" title="Create New Session">+ New</button>
        <button class="btn ghost danger" @click="confirmDeleteAll" title="Delete All Sessions">🗑️ Delete All</button>
        <button class="btn ghost" @click="$emit('refresh')" title="Refresh List" style="margin-left: auto;">🔄</button>
      </div>
    </div>

    <div class="session-list-items">
      <div v-if="loading" class="loading-text">Loading sessions...</div>
      <div v-else-if="!sessions || sessions.length === 0" class="no-sessions">No sessions found. Create one!</div>
      <div v-else>
        <div v-for="s in sessions" :key="s.session_id" class="session-item-wrapper">

          <div @click="select(s)" :class="['session-item', { active: current == s.session_id }]">
            <div>
              <strong>{{ s.session_name || s.session_id.slice(0, 8) }}</strong>
            </div>
            <div class="meta date">{{ formatDate(s.updated_at) }}</div>
          </div>

          <button @click="promptRename(s)" class="btn-edit" title="Rename this session">✏️</button>
          <button @click="confirmDeleteSession(s.session_id)" class="btn-delete" title="Delete this session">🗑️</button>
        </div>
      </div>
    </div>

    </div>
</template>

<script>
import { listSessions, createSession, deleteSession, deleteAllSessions, renameSession } from '../api'
export default {
  name: 'SessionList',
  props: { current: String },
  data(){ return { sessions: [], loading:false } },
  emits: ['select','refresh','created'],
  methods:{
    async fetch(){
      this.loading = true
      try{
        const res = await listSessions()
        this.sessions = res.sessions || []
      }catch(e){ console.error(e) }
      finally{ this.loading=false }
    },
    async createNew(){
      try{
        const res = await createSession()
        this.$emit('created', res.session_id)
        await this.fetch()
      }catch(e){ console.error(e) }
    },
    select(s){ this.$emit('select', s.session_id) },
    confirmDeleteSession(sessionId) {
      if (confirm(`Bạn có chắc muốn xóa session ${sessionId.slice(0,8)} không?`)) {
        this.deleteThisSession(sessionId);
      }
    },
    async deleteThisSession(sessionId) {
      try {
        await deleteSession(sessionId);
        console.log(`Deleted session: ${sessionId}`);
        // Nếu session đang mở bị xóa, clear currentSession
        if (this.current === sessionId) {
          localStorage.removeItem('current_session');
          this.$emit('select', null); // Báo cho App.vue biết không còn session nào được chọn
        }
        await this.fetch(); // Tải lại danh sách
      } catch (e) {
        console.error(`Error deleting session ${sessionId}:`, e);
        alert(`Không thể xóa session: ${e.response?.data?.detail || e.message}`);
      }
    },
    confirmDeleteAll() {
      if (confirm("!!! CẢNH BÁO !!!\nBạn có chắc muốn xóa TẤT CẢ các session không?\nHành động này không thể hoàn tác.")) {
        this.deleteAllUserSessions();
      }
    },
    async deleteAllUserSessions() {
      try {
        const res = await deleteAllSessions();
        console.log(`Deleted ${res.count} sessions.`);
        localStorage.removeItem('current_session');
        this.$emit('deletedAll'); // Báo cho App.vue biết tất cả đã bị xóa
        await this.fetch(); // Tải lại danh sách (sẽ rỗng)
      } catch (e) {
        console.error('Error deleting all sessions:', e);
        alert(`Không thể xóa tất cả sessions: ${e.response?.data?.detail || e.message}`);
      }
    },
    formatDate(isoString) {
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
        return isoString; // Trả về chuỗi gốc nếu không parse được
      }
    },
    promptRename(session) {
      const currentName = session.session_name;
      const newName = prompt(`Nhập tên mới cho session "${currentName}":`, currentName);
      if (newName !== null && newName.trim() !== '' && newName !== currentName) {
        this.renameThisSession(session.session_id, newName.trim());
      }
    },
    async renameThisSession(sessionId, newName) {
      try {
        await renameSession(sessionId, newName);
        console.log(`Renamed session ${sessionId} to "${newName}"`);
        // Tìm và cập nhật tên trong danh sách hiện tại để UI update ngay
        const index = this.sessions.findIndex(s => s.session_id === sessionId);
        if (index !== -1) {
          this.sessions[index].session_name = newName;
          // Có thể cập nhật luôn updated_at nếu API trả về
        }
        // Hoặc đơn giản là fetch lại toàn bộ danh sách
        // await this.fetch();
      } catch (e) {
        console.error(`Error renaming session ${sessionId}:`, e);
        // --- PHẦN SỬA LỖI ---
        let errorMessage = 'Không thể đổi tên session.'; // Mặc định
        if (e.response && e.response.data && e.response.data.detail) {
          // Lấy lỗi 'detail' từ FastAPI nếu có
          errorMessage = e.response.data.detail;
        } else if (e.message) {
          // Lấy message lỗi chung nếu không có response từ API
          errorMessage = e.message;
        } else {
           // Nếu không có gì cả, thử chuyển object lỗi thành chuỗi JSON
           try {
               errorMessage = JSON.stringify(e);
           } catch {
               // Bỏ qua nếu không thể stringify
           }
        }
        alert(errorMessage); // Hiển thị lỗi đã được xử lý
      }
    }
  },
  mounted(){ this.fetch() }
}
</script>

<style scoped>
/* Thêm style cho nút xóa và layout item */
.sessions {
  /* ... styles cũ ... */
  display: flex;
  flex-direction: column; /* Đảm bảo layout dọc */
}

.session-list-items {
  flex-grow: 1; /* Cho phép danh sách chiếm không gian còn lại */
  overflow-y: auto; /* Cho phép cuộn nếu danh sách dài */
}

.session-item-wrapper {
  display: flex;
  align-items: center; /* Căn giữa nút xóa theo chiều dọc */
  margin-bottom: 3px;
  border-radius: var(--border-radius-base);
  transition: background-color 0.1s ease;
}

.session-item-wrapper:hover {
   background-color: rgba(255, 255, 255, 0.03); /* Highlight nhẹ khi hover cả wrapper */
}

.session-item {
  flex-grow: 1; /* Session item chiếm phần lớn không gian */
  /* Bỏ margin-bottom ở đây vì đã có ở wrapper */
}

.btn-delete {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 1rem;
  padding: 8px; /* Tăng vùng bấm */
  margin-left: 8px; /* Khoảng cách với session item */
  opacity: 0.6;
  transition: opacity 0.2s, color 0.2s;
}

.btn-delete:hover {
  opacity: 1;
  color: #f87171; /* Màu đỏ nhẹ khi hover */
}

.btn.danger { /* Style cho nút Delete All */
    background: #dc2626; /* Màu đỏ cảnh báo */
    border-color: #b91c1c;
}
.btn.danger:hover {
    background: #b91c1c;
    filter: none;
}

.loading-text, .no-sessions {
  color: var(--text-secondary);
  padding: 20px;
  text-align: center;
}

.meta.date { /* Style riêng cho ngày tháng */
    font-size: 0.7rem;
    margin-top: 4px;
}

/* Thêm style cho nút sửa tên */
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

/* Điều chỉnh lại nút xóa một chút */
.btn-delete {
  font-size: 0.9rem; /* Đồng bộ cỡ icon */
  margin-left: 4px; /* Giảm khoảng cách với nút sửa */
}

/* Đảm bảo tên session không bị tràn */
.session-item strong {
  display: block; /* Cho phép text-overflow hoạt động */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>