<template>
  <div :class="['msg', roleClass]">

    <div class="msg-logo">
      <span v-if="role === 'user'">🧑‍💻</span> <span v-else>🤖</span>
    </div>

    <div class="msg-content">

      <div v-if="isArrayContent">
        <div v-for="(part, idx) in content" :key="idx">

          <template v-if="part?.type === 'text'">
            <div v-html="renderMarkdown(part.text)"></div>
          </template>

          <template v-else-if="part?.type === 'image_url'">
            <img :src="part.image_url.url" class="msg-image" alt="Xem trước ảnh người dùng" />
          </template>

          <template v-else>
            <div>{{ renderMarkdown(part) }}</div>
          </template>

        </div>
      </div>

      <div v-else v-html="content"></div>

    </div>

  </div>
</template>

<script>
import { marked } from 'marked';

export default {
  name: "MessageBubble",
  props: {
    role: { type: String, required: true }, // 'user' hoặc 'assistant'
    content: { type: [String, Array], required: true } // Nội dung có thể là chuỗi hoặc mảng
  },
  computed: {
    // Xác định class CSS dựa trên vai trò
    roleClass() {
      return this.role === 'user' ? 'user' : 'assistant'
    },
    // Kiểm tra xem content có phải là mảng không
    isArrayContent() {
      return Array.isArray(this.content)
    }
  },
  methods: {
    // Hàm render markdown (nếu bạn muốn hỗ trợ)
    renderMarkdown(text) {
      if (typeof text !== 'string') return '';
      // Cấu hình marked (tùy chọn)
      marked.setOptions({
        breaks: false, // Chuyển đổi dấu xuống dòng thành <br>
        gfm: true,    // Hỗ trợ GitHub Flavored Markdown
        // Bạn có thể thêm các tùy chọn khác tại đây
      });
      try {
        const cleanedText = text.replace(/ {2,}/g, ' ').replace(/\n{3,}/g, '\n\n'); // Loại bỏ khoảng trắng/xuống dòng thừa
        return marked.parse(cleanedText);
      } catch (e) {
        console.error("Markdown parsing error:", e);
        return text; // Trả về text gốc nếu lỗi
      }
    }
  }
}
</script>

<style scoped>
/* Thêm style scoped nếu cần, ví dụ cho ảnh */
.msg-image {
  max-width: 100%; /* Đảm bảo ảnh nằm gọn trong bong bóng */
  max-height: 400px; /* Giới hạn chiều cao ảnh */
  border-radius: var(--border-radius-base); /* Bo góc ảnh */
  margin-top: 10px; /* Khoảng cách với text (nếu có) */
  display: block; /* Đảm bảo ảnh không bị inline */
}
</style>