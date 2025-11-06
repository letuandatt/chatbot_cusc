<template>
  <div class="auth-page">
    <div class="auth-form file-list-card">
      <div class="profile-actions">
        <router-link to="/" class="btn ghost">Quay lại Chat</router-link>
      </div>

      <h1>File đã tải lên</h1>

      <div v-if="loading" class="loading-indicator">Đang tải danh sách file...</div>
      <div v-else-if="error" class="error-message">{{ error }}</div>

      <div v-else-if="!files || files.length === 0" class="no-files">
        <p>Bạn chưa tải lên file PDF nào.</p>
      </div>

      <div v-else class="file-list-container">
        <table class="file-table">
          <thead>
            <tr>
              <th>Tên File</th>
              <th>Ngày tải lên</th>
              <th>Trạng thái</th>
              <th>Session ID</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(file, index) in files" :key="index">
              <td class="filename">{{ file.filename }}</td>
              <td>{{ formatDate(file.created_at) }}</td>
              <td>
                <span :class="['status', file.status || 'unknown']">
                  {{ file.status || 'N/A' }}
                </span>
              </td>
              <td class="session-id">{{ file.session_id.slice(0, 12) }}...</td>
            </tr>
          </tbody>
        </table>
        <span style="color: var(--text-secondary); font-size: 0.9rem; margin-top: 25px; display: block; font-style: italic">
          Vui lòng đảm bảo bạn còn lưu trữ các file trên.
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { listUserDocuments, downloadDocument } from '../api'; // Import hàm API mới

const files = ref([]);
const loading = ref(false);
const error = ref(null);

// Lấy danh sách file khi component được mounted
const fetchFiles = async () => {
  loading.value = true;
  error.value = null;
  try {
    const response = await listUserDocuments();
    files.value = response.documents || [];
  } catch (err) {
    console.error("Error fetching files:", err);
    error.value = err.message || "Không thể tải danh sách file.";
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchFiles();
});

// Hàm format ngày (tái sử dụng từ SessionList)
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
</script>

<style scoped>
/* Tái sử dụng style từ LoginView/ProfileView */
.auth-page {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 5vh 20px;
  min-height: 100vh;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  overflow-y: auto;
}

.file-list-card {
  background-color: var(--bg-secondary);
  padding: 25px 40px;
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-md);
  width: 100%;
  max-width: 800px; /* Rộng hơn để chứa bảng */
  text-align: center;
  max-height: 88vh;
  overflow-y: auto;
}

.file-list-card h1 {
  margin-bottom: 25px;
  font-weight: 600;
  font-size: 1.6rem;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 15px;
}

.profile-actions {
  display: flex;
  justify-content: flex-start;
  margin-bottom: 20px;
}
.profile-actions .btn {
  font-size: 0.9rem;
  padding: 8px 18px;
}

.loading-indicator, .no-files {
  margin-top: 30px;
  color: var(--text-secondary);
  font-size: 1rem;
}
.no-files p {
  margin: 0;
}

.error-message {
  color: #fca5a5;
  background-color: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  padding: 10px 15px;
  border-radius: var(--border-radius-base);
  font-size: 0.9rem;
  margin: 20px 0;
  text-align: center;
}

/* Style cho bảng */
.file-list-container {
  margin-top: 25px;
  width: 100%;
  overflow-x: auto; /* Cho phép cuộn ngang nếu bảng quá rộng */
}
.file-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
.file-table th, .file-table td {
  padding: 12px 15px;
  border-bottom: 1px solid var(--border-color);
  font-size: 0.9rem;
  vertical-align: middle;
}
.file-table th {
  color: var(--text-secondary);
  font-weight: 500;
  background-color: var(--bg-tertiary);
  border-top: 1px solid var(--border-color);
}
.file-table td {
  color: var(--text-primary);
}
.file-table .filename {
  font-weight: 500;
  word-break: break-all;
}
.file-table .session-id {
  font-family: 'Courier New', Courier, monospace;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

/* Style cho trạng thái (status) */
.status {
  padding: 4px 8px;
  border-radius: var(--border-radius-base);
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}
.status.processed {
  background-color: rgba(16, 185, 129, 0.1);
  color: #6ee7b7;
}
.status.uploaded {
  background-color: rgba(59, 130, 246, 0.1);
  color: #93c5fd;
}
.status.error_parsing, .status.error_vectorizing, .status.error_no_chunks {
  background-color: rgba(239, 68, 68, 0.1);
  color: #fca5a5;
}
.status.unknown {
  background-color: var(--bg-tertiary);
  color: var(--text-secondary);
}

.btn-download {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 1.1rem;
  padding: 8px;
  opacity: 0.7;
  transition: opacity 0.2s, color 0.2s;
}
.btn-download:hover {
  opacity: 1;
  color: var(--bg-accent);
}
.btn-download:disabled {
  opacity: 0.3;
  cursor: not-allowed;
  color: var(--text-secondary);
}

</style>