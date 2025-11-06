<template>
  <div class="chat">
    <div class="header">
      <div>
        <div class="header-title">
            <img src="../assets/20181031cusc.png" alt="Logo" class="header-logo">
            <span @click="goHome" class="clickable-title">
              <strong style="font-size: xx-large">ChatCUSC</strong>
            </span>
          </div>
      </div>
      <div class="header-controls">
<!--            <div class="meta" v-if="sessionId">Session: {{ sessionIdShort }}</div>-->
            <router-link to="/profile" class="profile-button" title="Thông tin tài khoản">
              👤
            </router-link>
          </div>
    </div>

    <div v-if="!sessionId" class="welcome-screen">
      <h2>Chào mừng đến với ChatCUSC!</h2>
      <p>Tạo phiên làm việc mới hoặc chọn một phiên làm việc đã tồn tại.</p>
      <div class="welcome-icon">🤖</div>
    </div>

    <template v-else>
      <div ref="historyEl" class="history">
        <div v-for="(m, idx) in messages" :key="idx">
          <MessageBubble :role="m.role" :content="m.content" />
          </div>
        <div v-if="isStreaming" class="msg assistant">
          <MessageBubble role="assistant" :content="streamText + '▍'" /> </div>
      </div>

      <div class="input-area">
        <label for="file-input" class="file-label"></label>
        <input
          id="file-input"
          type="file"
          ref="fileInput"
          @change="onFile"
          :disabled="!sessionId || sending"
          accept=".pdf,.jpg,.jpeg,.png,.webp"
        />
        <span v-if="fileName" class="file-name">{{ fileName }}</span>

        <input
          type="text"
          v-model="question"
          @keyup.enter="sendMessage"
          placeholder="Gõ câu hỏi..."
          :disabled="!sessionId || sending" /> <button
          class="btn send" @click="sendMessage"
          :disabled="!sessionId || sending || !question.trim()"> Send
        </button>
      </div>
    </template>
  </div>
</template>

<script>
import MessageBubble from './MessageBubble.vue'
import { viewSession, uploadPdf } from '../api'
import { v4 as uuidv4 } from 'uuid'
import { useAuthStore } from "../stores/auth.js";

export default {
  name: 'ChatWindow',
  components: { MessageBubble },
  props: { initialSessionId: { type: String, default: null } },
  emits: ['deselect-session'],
  data(){ return {
    sessionId: this.initialSessionId || localStorage.getItem('current_session') || null,
    messages: [],
    question: '',
    file: null,
    fileName: '',
    fileType: '',
    sending: false,
    isStreaming: false,
    streamText: ''
  }},
  computed: {
    sessionIdShort(){ return this.sessionId ? this.sessionId.slice(0,8) : '—' }
  },
  methods: {
    async loadSession(sessionId){
      if(!sessionId) {
        this.messages = []
        return;
      }
      console.log(`ChatWindow: Loading session ${sessionId}`);
      try{
        const res = await viewSession(sessionId)
        // Convert from API format to messages array
        this.messages = res.messages.map(m => ({
          role: m.role,
          content: m.content
        }))
        this.$nextTick(()=> this.scrollToBottom())
      }catch(e){
        console.error('loadSession', e) ;
        this.messages = [{role: 'assistant', content: `Lỗi: Không thể tải lịch sử session ${sessionIdShort}. Vui lòng thử lại.`}];
      }
    },
    onFile(e) {
      const f = e.target.files[0];
      if (!f) {
        this.resetFileInput();
        return;
      }

      this.file = f;
      this.fileName = f.name;

      if (f.type.startsWith('image/')) {
        this.fileType = 'image';
        console.log("Đã chọn ảnh");
      }
      else if (f.type.startsWith('application/pdf')) {
        this.fileType = "pdf";
        console.log("Đã chọn PDF")
        this.uploadPdfInternal();
      }
      else {
        this.messages.push({ role: "assistant", content: `Lỗi: Loại file "${f.name}" không được hỗ trợ. Chỉ chấp nhận PDF, JPG, PNG.`})
        this.resetFileInput();
        this.scrollToBottom();
      }
    },
    sendMessage() {
      if (!this.sessionId) {
        alert("Vui lòng tạo hoặc chọn một session trước khi gửi tin nhắn.");
        return;
      }
      if (!this.question.trim()) return;

      // Nếu có file được chọn, gọi logic gửi ảnh
      if (this.file && this.fileType === 'image') {
        this.sendImageInternal(); // Gọi hàm helper gửi ảnh
      }
      // Nếu không có file, gọi logic gửi text
      else {
        this.sendTextInternal(); // Gọi hàm helper gửi text
      }
    },
    async uploadPdfInternal() {
      if (!this.file || this.fileType !== 'pdf' || !this.sessionId) return;

      const pdfFile = this.file; // Lưu file PDF lại
      this.sending = true; // Hiển thị trạng thái "đang bận"

      this.fileName = `Đang xử lý: ${pdfFile.name}...`;

      try {
        // Gọi API (hàm chúng ta tạo ở Bước 1)
        const response = await uploadPdf(pdfFile, this.sessionId);

        this.fileName = response.filename;
        this.file = null;

      } catch (err) {
        console.error('Lỗi khi tải PDF:', err);
        this.fileName = `Lỗi: ${err.message}. Vui lòng chọn lại file.`;
        setTimeout(() => {
          if (this.fileName.startsWith("Lỗi: ")) {
            this.resetFileInput();
          }
        }, 3000)
      } finally {
        this.sending = false; // Tắt trạng thái "đang bận"
        // this.scrollToBottom();
      }
    },
    resetFileInput() {
      this.file = null;
      this.fileName = '';
      this.fileType = 'none';
      if (this.$refs.fileInput) this.$refs.fileInput.value = null;
    },
    // --- HÀM HELPER GỬI TEXT (gần giống sendText cũ) ---
    async sendTextInternal(){
      if(!this.question.trim() || this.sending) return; // Kiểm tra thêm sending
      const q = this.question;
      this.question = ''; // Xóa input

      // Thêm tin nhắn user vào giao diện
      this.messages.push({ role: 'user', content: q });
      this.$nextTick(()=> this.scrollToBottom());

      // Bắt đầu stream từ backend
      await this.streamChatText(q); // Hàm stream giữ nguyên
    },
    // --- HÀM HELPER GỬI ẢNH (gần giống sendImage cũ) ---
    async sendImageInternal(){
      if(!this.question.trim() || !this.file || this.sending) return; // Kiểm tra thêm sending và question
      const q = this.question;
      const f = this.file;

      // Xóa input và file đã chọn
      this.question = '';
      this.resetFileInput();

      // Thêm tin nhắn user (text + ảnh preview) vào giao diện
      // Tạo URL tạm thời cho ảnh để hiển thị ngay
      const imagePreviewUrl = URL.createObjectURL(f);
      this.messages.push({
        role: 'user',
        content: [ // Gửi dạng mảng để MessageBubble hiển thị ảnh
          { type: 'text', text: q },
          { type: 'image_url', image_url: { url: imagePreviewUrl } }
        ]
      });
      this.$nextTick(()=> this.scrollToBottom());

      // Bắt đầu stream từ backend
      await this.streamChatImage(q, f); // Hàm stream giữ nguyên

      // Thu hồi URL tạm thời sau khi dùng xong (tránh memory leak)
      URL.revokeObjectURL(imagePreviewUrl);
    },

    // Use fetch + ReadableStream to receive streamed response
    async streamChatText(question){
      if (!this.sessionId) return;

      this.sending = true
      this.isStreaming = true
      this.streamText = ''

      const authStore = useAuthStore();
      const token = authStore.token;
      if (!token) {
        this.messages.push({ role: 'assistant', content: 'Lỗi: Bạn chưa đăng nhập hoặc phiên đăng nhập đã hết hạn.' });
        this.sending = false;
        this.isStreaming = false;
        this.scrollToBottom();
        authStore.logout(); // Tùy chọn: Tự động logout nếu không có token
        return;
      }

      try{
        const BASE = '/api'
        const url = `${BASE}/chat/text`
        const form = new FormData()
        form.append('question', question)
        form.append('session_id', this.sessionId)

        const resp = await fetch(url, {
          method: 'POST',
          body: form,
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })
        if(!resp.ok){
          const txt = await resp.text()
          throw new Error(txt || 'Request failed')
        }

        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let done=false
        let full=''
        while(!done){
          const { value, done: d } = await reader.read()
          done = d
          if(value){
            const chunk = decoder.decode(value)
            full += chunk
            this.streamText = full
            await this.$nextTick(()=> this.scrollToBottom())
          }
        }

        // push assistant final
        this.messages.push({ role: 'assistant', content: full })
        this.isStreaming = false
        this.sending = false
        this.streamText = ''
        this.scrollToBottom()
      }catch(err){
        console.error(err)
        this.messages.push({ role: 'assistant', content: `Error: ${err.message}` })
        this.isStreaming = false
        this.sending = false
        this.scrollToBottom()
      }finally {
        this.sending = false;
        this.isStreaming = false;
        await this.$nextTick(()=> this.scrollToBottom())
      }
    },

    // streaming image endpoint
    async streamChatImage(question, file){
      if (!this.sessionId) return;

      this.sending = true
      this.isStreaming = true
      this.streamText = ''

      const authStore = useAuthStore();
      const token = authStore.token;
      if (!token) {
        this.messages.push({ role: 'assistant', content: 'Lỗi: Bạn chưa đăng nhập hoặc phiên đăng nhập đã hết hạn.' });
        this.sending = false;
        this.isStreaming = false;
        this.scrollToBottom();
        authStore.logout();
        return;
      }

      try{
        const BASE = '/api'
        const url = `${BASE}/chat/image`
        const form = new FormData()
        form.append('question', question)
        form.append('file', file, file.name)
        form.append('session_id', this.sessionId)

        const resp = await fetch(url, {
          method:'POST',
          body: form,
          headers: {
              'Authorization': `Bearer ${token}`
            }
        })
        if(!resp.ok){
          const txt = await resp.text();
          if (resp.status === 401) {
             throw new Error("Xác thực thất bại. Vui lòng đăng nhập lại.");
             authStore.logout();
          }
          throw new Error(txt || `Request failed with status ${resp.status}`);
        }

        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let done=false
        let full=''
        while(!done){
          const { value, done: d } = await reader.read()
          done = d
          if(value){
            const chunk = decoder.decode(value)
            full += chunk
            this.streamText = full
            await this.$nextTick(()=> this.scrollToBottom())
          }
        }
        this.messages.push({ role:'assistant', content: full })
        this.isStreaming=false
        this.sending=false
        this.streamText=''
        this.scrollToBottom()
      }catch(err){
        console.error(err)
        this.messages.push({ role: 'assistant', content: `Error: ${err.message}` })
        this.isStreaming=false
        this.sending=false
        this.scrollToBottom()
      }finally {
        this.sending = false;
        this.isStreaming = false;
        await this.$nextTick(() => this.scrollToBottom());
      }
    },

    scrollToBottom(){
      this.$nextTick(()=>{
        const el = this.$refs.historyEl
        if(el) el.scrollTop = el.scrollHeight + 200
      })
    },

    goHome(){
      console.log("ChatWindow: Emitting deselect-session");
      this.$emit('deselect-session');
    }
  },
  mounted(){
    // Load initial session if provided
    console.log("ChatWindow mounted with initialSessionId:", this.initialSessionId);
    if(this.sessionId) this.loadSession(this.sessionId)
  },
  watch: {
    initialSessionId(newId, oldId) {
      console.log(`ChatWindow watched initialSessionId change from ${oldId} to ${newId}`);
      // Cập nhật sessionId nội bộ của component
      this.sessionId = newId;
      // Tải session mới (hoặc xóa messages nếu newId là null)
      this.loadSession(newId);
    }
  }
}
</script>

<style scoped>
/* Thêm style cho màn hình chào mừng */
.welcome-screen {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  color: var(--text-secondary);
  padding: 42px;
  /* Thêm hiệu ứng nền nhẹ */
  background: radial-gradient(circle at top center, rgba(37, 42, 51, 0.5) 0%, transparent 60%);
  overflow: hidden; /* Ẩn phần gradient tràn ra ngoài */
}

.welcome-screen h2 {
  color: var(--text-primary);
  margin-bottom: 20px; /* Tăng khoảng cách */
  font-weight: 600;    /* Đậm hơn */
  font-size: 1.75rem; /* Lớn hơn */
  letter-spacing: 0.5px;
}

.welcome-screen p {
  max-width: 500px; /* Rộng hơn chút */
  line-height: 1.8;   /* Giãn dòng */
  font-size: 1rem;    /* Cỡ chữ to hơn */
  margin-bottom: 40px; /* Khoảng cách với icon */
  margin-top: 10px;
}

.welcome-icon {
    font-size: 5rem; /* Icon to hơn */
    margin-top: 20px;
    opacity: 0.4; /* Mờ hơn chút */
    /* Thêm animation nhẹ (tùy chọn) */
    animation: float 4s ease-in-out infinite;
}

/* Animation cho icon (tùy chọn) */
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

/* Đường kẻ phân cách nhẹ (tùy chọn) */
.welcome-screen::before {
    content: '';
    position: absolute;
    top: 15%;
    left: 50%;
    transform: translateX(-50%);
    width: 100px;
    height: 2px;
    background: linear-gradient(to right, transparent, var(--border-color), transparent);
    opacity: 0.5;
}

/* Đảm bảo history và input-area không hiển thị khi không có session */
/* (Đã xử lý bằng v-else trong template) */

/* Style cho input bị disable (nếu cần rõ hơn) */
input:disabled, button:disabled {
  opacity: 0.5; /* Giảm độ sáng */
  cursor: not-allowed; /* Đổi con trỏ */
  /* background-color: #2a2d34 !important; */ /* Tùy chọn: đổi màu nền */
}
label.file-label[for="file-input"]:has(+ input[type="file"]:disabled) {
  opacity: 0.5;
  cursor: not-allowed;
}

.clickable-title {
  cursor: pointer;
  transition: opacity 0.2s ease;
}
.clickable-title:hover {
  opacity: 0.8;
}

.header-title {
  display: flex; /* Sử dụng flexbox để căn chỉnh logo và text */
  align-items: center; /* Căn giữa theo chiều dọc */
  gap: 10px; /* Khoảng cách giữa logo và text */
}

.header-logo {
  height: 32px; /* Điều chỉnh chiều cao logo */
  width: auto;   /* Chiều rộng tự động theo tỷ lệ */
  object-fit: contain; /* Đảm bảo logo không bị méo */
}

.clickable-title { /* Style cũ để click vào text */
  cursor: pointer;
  transition: opacity 0.2s ease;
}
.clickable-title:hover {
  opacity: 0.8;
}

.header-controls {
    display: flex;
    align-items: center;
    gap: 16px;
}
.profile-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background-color: var(--bg-tertiary);
    color: var(--text-secondary);
    font-size: 1.2rem;
    text-decoration: none;
    transition: background-color 0.2s, color 0.2s;
    border: 1px solid transparent;
}
.profile-button:hover {
    background-color: #374151;
    color: var(--text-primary);
    border-color: var(--border-color);
}
</style>