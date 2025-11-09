<template>
  <div class="sessions">
    <div class="sidebar-header">
      <div class="btn-group">

        <button class="btn" @click="createNew" title="Tạo mới">+ Tạo mới</button>
        <button class="btn ghost danger" @click="confirmDeleteAll" title="Xóa tất cả">🗑️ Xóa tất cả</button>

        <button class="btn ghost toggle-btn" @click="$emit('toggle')" title="Thu gọn">«</button>
      </div>
    </div>

    <div class="session-list-items">
      <div v-if="loading" class="loading-text">Đang tải các phiên ...</div>
      <div v-else-if="!sessions || sessions.length === 0" class="no-sessions">
        <div style="margin-bottom: 10px">Không có phiên làm việc nào.</div>
        <div>Hãy tạo một phiên làm việc để chat</div></div>
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

    <div class="sidebar-footer">
      <button class="btn ghost logout-btn-bottom" @click="$emit('logout')" title="Logout">
        🚪 Đăng xuất
      </button>
      <button class="btn ghost delete-account-btn" @click="confirmDeleteAccount" title="Delete Account">
         ⚠️ Xóa Tài khoản
       </button>
    </div>

    </div>
</template>

<script>
import { listSessions, createSession, deleteSession, deleteAllSessions, renameSession, deleteCurrentUserAccount } from '../api'
import { useAuthStore } from '../stores/auth'
export default {
  name: 'SessionList',
  props: { current: String },
  data(){ return { sessions: [], loading:false } },
  // THÊM 'toggle' VÀO EMITS
  emits: ['select','refresh','created', 'deletedAll', 'logout', 'toggle'],
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
        this.$emit('select', null); // Báo cho App.vue biết tất cả đã bị xóa
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
    },
    confirmDeleteAccount() {
      // Hiển thị cảnh báo mạnh mẽ
      const confirmation = prompt(
        "!!! CẢNH BÁO XÓA TÀI KHOẢN !!!\n" +
        "Hành động này sẽ xóa vĩnh viễn tài khoản của bạn và TOÀN BỘ lịch sử trò chuyện.\n" +
        "Không thể hoàn tác.\n\n" +
        "Nhập 'DELETE' vào ô bên dưới để xác nhận:"
      );

      if (confirmation && confirmation.trim().toUpperCase() === 'DELETE') {
        this.deleteAccount();
      } else if (confirmation !== null){
        alert("Xác nhận không hợp lệ. Hủy bỏ xóa tài khoản.");
      } else {
        console.log("Xóa tài khoản đã bị hủy.");
      }
    },
    deleteAccount: async function () {
      const authStore = useAuthStore(); // Lấy auth store
      let success = false;
      try {
        const result = await deleteCurrentUserAccount();
        alert(`Delete account result: ${result}`);

        if (result && result.status === "deleted") {
          alert("Tài khoản và dữ liệu của bạn đã được xóa thành công.");
          success = true; // Đánh dấu là đã xóa thành công
        } else {
          // Nếu API không trả về status mong đợi
          throw new Error("API không xác nhận xóa thành công.");
        }
      } catch (e) {
        console.error('Error deleting account:', e);
        // Xử lý và hiển thị lỗi như cũ
        let errorMessage = 'Không thể xóa tài khoản.';
        if (e.response && e.response.data && e.response.data.detail) {
          errorMessage = e.response.data.detail;
        } else if (e.message) {
          errorMessage = e.message;
        }
        alert(errorMessage);
        success = false; // Đánh dấu là thất bại
      } finally {
        if (success) {
          authStore.logout();
        }
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

.session-item strong {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  /* Thêm hoặc sửa dòng font-size này */
  font-size: 0.85rem; /* Ví dụ: giảm xuống còn 0.85rem (khoảng 13.6px nếu font gốc là 16px) */
  /* Hoặc dùng pixel: font-size: 13px; */
  /* Hoặc dùng %: font-size: 85%; */
  font-weight: 500; /* Giữ nguyên độ đậm */
  color: var(--text-primary); /* Đảm bảo màu chữ rõ */
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

/* Phần Tip */
.sidebar-tip {
  padding: 10px 16px;
  font-size: 0.75rem; /* Nhỏ hơn */
  color: var(--text-secondary);
  text-align: center;
  border-top: 1px solid var(--border-color); /* Thêm đường kẻ trên */
  margin-top: auto; /* Đẩy tip và footer xuống dưới nếu list ngắn */
  flex-shrink: 0; /* Không co lại */
}

/* Phần Chân Sidebar (chứa nút Logout) */
.sidebar-footer {
  padding: 12px 16px; /* Padding xung quanh nút */
  border-top: 1px solid var(--border-color); /* Đường kẻ trên */
  flex-shrink: 0; /* Không co lại */
}

/* Nút Logout mới ở dưới */
.logout-btn-bottom {
  width: 100%; /* Chiếm toàn bộ chiều rộng */
  display: flex; /* Để căn giữa icon/text */
  align-items: center;
  justify-content: center;
  gap: 8px; /* Khoảng cách giữa icon và text */
  padding: 10px 12px; /* Padding bên trong nút */
  font-size: 0.9rem;
  color: #fca5a5; /* Màu đỏ nhạt */
  border-color: rgba(239, 68, 68, 0.3); /* Viền đỏ mờ */
}

.logout-btn-bottom:hover {
  background-color: rgba(239, 68, 68, 0.1); /* Nền đỏ rất nhạt khi hover */
  border-color: rgba(239, 68, 68, 0.6); /* Viền đỏ rõ hơn */
  color: #ef4444; /* Màu đỏ rõ hơn */
}

/* Ghi đè lại style mặc định của .btn.ghost nếu cần */
.logout-btn-bottom.btn.ghost {
    background: transparent; /* Đảm bảo nền trong suốt ban đầu */
    box-shadow: none;
}

/* Style cho nút Xóa Tài khoản */
.delete-account-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 12px;
  font-size: 0.85rem; /* Nhỏ hơn nút logout */
  color: #fca5a5; /* Màu đỏ nhạt */
  border-color: rgba(239, 68, 68, 0.3);
  margin-top: 8px; /* Khoảng cách với nút logout */
}

.delete-account-btn:hover {
  background-color: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.6);
  color: #ef4444; /* Màu đỏ rõ hơn */
}
/* Ghi đè lại style mặc định của .btn.ghost nếu cần */
.delete-account-btn.btn.ghost {
    background: transparent;
    box-shadow: none;
}

/* --- THÊM MỚI STYLE CHO NÚT TOGGLE VÀ HEADER --- */
.sidebar-header .btn-group {
    display: flex;
    gap: 8px;
    align-items: center;
}
.sidebar-header .btn {
   flex-grow: 0; /* Ngăn nút bị giãn */
}
.toggle-btn {
  font-size: 1.5rem;
  padding: 0px 10px;
  font-weight: bold;
  min-width: 40px;
}
</style>