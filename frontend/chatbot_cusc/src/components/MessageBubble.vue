<template>
  <div :class="['msg', roleClass]">

<!--    <div class="msg-logo">-->
<!--      <span v-if="role === 'user'">🧑‍💻</span> <span v-else>🤖</span>-->
<!--    </div>-->

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
            <div v-html="renderMarkdown(part)"></div>
          </template>

        </div>
      </div>

      <div v-else v-html="renderMarkdown(content)"></div>
    </div>

  </div>
</template>

<script>
import { marked } from 'marked';
import DOMPurify from 'dompurify';

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
    renderMarkdown(text) {
      if (typeof text !== 'string') return '';

      // Cấu hình marked
      marked.setOptions({
        // breaks: false, // TẮT: Không tự động chuyển \n thành <br>
        gfm: true,    // BẬT: Hỗ trợ GitHub Flavored Markdown (quan trọng cho list, code block)
        pedantic: false, // TẮT: Không quá khắt khe về cú pháp
        sanitize: false, // TẮT: Không dùng bộ sanitize cũ của marked (sẽ dùng DOMPurify)
        smartypants: false // TẮT: Không tự động đổi dấu ngoặc kép, etc.
      });

      try {
        // BƯỚC 1: Làm sạch text thô (loại bỏ khoảng trắng/xuống dòng thừa)
        // - Thay thế 3+ dấu xuống dòng bằng 2 dấu (để giữ lại đoạn văn)
        // - Thay thế 2+ dấu cách bằng 1 dấu cách
        // - Xóa dấu cách ở đầu/cuối mỗi dòng
        const cleanedText = text
            .replace(/\n{3,}/g, '\n\n')
            .replace(/ {2,}/g, ' ')
            .split('\n').map(line => line.trim()).join('\n');

        // BƯỚC 2: Parse Markdown thành HTML
        const rawHtml = marked.parse(cleanedText);

        // BƯỚC 3: Sanitize HTML (Quan trọng để tránh lỗi XSS)
        // Sử dụng DOMPurify để loại bỏ các thẻ/thuộc tính nguy hiểm
        const sanitizedHtml = DOMPurify.sanitize(rawHtml, {
            USE_PROFILES: { html: true } // Cho phép các thẻ HTML an toàn
        });

        return sanitizedHtml;

      } catch (e) {
        console.error("Markdown parsing/sanitizing error:", e);
        // Fallback: Hiển thị text gốc nhưng escape HTML để tránh XSS
        const escapeHtml = (unsafe) => {
           return unsafe
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }
        return escapeHtml(text).replace(/\n/g, '<br>'); // Chỉ thay \n bằng <br> nếu lỗi
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