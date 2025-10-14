import os
import nest_asyncio
import re

from llama_parse import LlamaParse
from dotenv import load_dotenv

nest_asyncio.apply()

load_dotenv()

system_prompt_ = """
Bạn là một chuyên gia chuyển đổi PDF sang Markdown. Nhiệm vụ của bạn là trích xuất NỘI DUNG CHÍNH của tài liệu một cách sạch sẽ và chính xác tuyệt đối.

**QUY TẮC BẮT BUỘC:**

1.  **NỘI DUNG CẦN LOẠI BỎ HOÀN TOÀN:** KHÔNG ĐƯỢC trích xuất bất kỳ dòng nào chứa các thông tin lặp lại ở đầu và cuối trang (header/footer). // Các nội dung này bao gồm, nhưng không giới hạn ở:
    <examples_to_remove>
        - TRƯỜNG ĐẠI HỌC CẦN THƠ
        - TRUNG TÂM CÔNG NGHỆ PHẦN MỀM
        - CUSC
        - ISO 9001:2015
        - software
        - Cantho University Software Center
        - Sổ tay Phần mềm
        - Quá trình Phát triển Phần mềm
        - Dòng chứa mã hiệu và số trang (ví dụ: "TT07.02/PM/CUSC, V2.0 Trang 2/5")
    </examples_to_remove>

2.  **TẬP TRUNG VÀO NỘI DUNG CHÍNH:** Chỉ trích xuất phần thân của văn bản, bao gồm:
    - Tên của tài liệu (Sử dụng # làm phân cấp)
    - Tiêu đề chính của tài liệu.
    - Các mục La Mã (I, II, III...).
    - Bảng biểu (giữ nguyên định dạng Markdown hoặc HTML).
    - Lưu đồ (chuyển thành mã Mermaid nếu có thể).
    - Các đoạn văn mô tả quy trình, thủ tục.

3.  **ĐỊNH DẠNG ĐẶC BIỆT:**
    - Với các mục La Mã từ V trở đi, hãy thêm tên văn bản vào sau tiêu đề.
      Ví dụ: Nếu tên văn bản là "THỦ TỤC HOẠCH ĐỊNH", thì mục "VI. NỘI DUNG" phải trở thành "VI. NỘI DUNG THỦ TỤC HOẠCH ĐỊNH".

Không được trích xuất thiếu thông tin.
"""

def llama_parse_md(data_dir):
    parser = LlamaParse(
        api_key=os.getenv("LLAMA_CLOUD_API_KEY"),
        parse_mode="parse_page_with_agent",
        model="anthropic-sonnet-4.5",
        output_tables_as_HTML=True,
        merge_tables_across_pages_in_markdown=True,
        compact_markdown_table=True,
        language="vi",
        high_res_ocr=True,
        adaptive_long_table=True,
        outlined_table_extraction=True,
        result_type="markdown",
        specialized_chart_parsing_efficient=True
    )

    save_dir = "data/after_parse"

    for file in os.listdir(data_dir):
        full_path = os.path.join(data_dir, file)
        if os.path.isdir(full_path):
            continue

        if file.endswith(".pdf"):
            print(f"Parsing {file}")

            base_name, _ = os.path.splitext(file)

            documents = parser.load_data(full_path)

            full_md_content = "\n\n".join([doc.get_content() for doc in documents])

            # cleaned_content = post_process_markdown(full_md_content)
            #
            # doc_name = get_document_name(cleaned_content)
            #
            # cleaned_content = add_doc_name_to_roman(cleaned_content, doc_name)

            cleaned_content = fix_first_roman_headings(full_md_content)

            output_filename = f"{base_name}.md"
            output_path = os.path.join(save_dir, output_filename)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(cleaned_content)

            print(f"Saved to {output_path}")


def is_inside_table(lines, current_index):
    """
    Kiểm tra xem dòng hiện tại có nằm trong bảng HTML hoặc Markdown không
    """
    # Kiểm tra trong phạm vi ±10 dòng
    start = max(0, current_index - 10)
    end = min(len(lines), current_index + 10)

    context = '\n'.join(lines[start:end])

    # Kiểm tra HTML table
    if '<table>' in context or '</table>' in context:
        # Đếm số thẻ mở và đóng trước vị trí hiện tại
        before_context = '\n'.join(lines[start:current_index + 1])
        open_tags = before_context.count('<table>')
        close_tags = before_context.count('</table>')

        if open_tags > close_tags:
            return True

    # Kiểm tra Markdown table (có dấu | ở đầu hoặc cuối dòng)
    current_line = lines[current_index].strip()
    if current_line.startswith('|') or current_line.endswith('|'):
        return True

    # Kiểm tra dòng phân cách bảng markdown (|---|---|)
    for i in range(max(0, current_index - 3), min(len(lines), current_index + 3)):
        if re.match(r'^\|[\s\-:|]+\|$', lines[i].strip()):
            return True

    # Kiểm tra xem có nằm trong thẻ <td> hay <tr> không
    if '<td>' in current_line or '</td>' in current_line or \
            '<tr>' in current_line or '</tr>' in current_line:
        return True

    return False

def is_footer_line(line, prev_line='', next_line=''):
    """
    Xác định xem một dòng có phải là footer không dựa vào ngữ cảnh
    Footer thường:
    - Đứng độc lập (không có nội dung phía trước/sau gần)
    - Có nhiều khoảng trắng padding
    - Có pattern đặc trưng: mã + số trang
    """
    line_stripped = line.strip()

    # Footer pattern: mã tài liệu + khoảng trắng dài + số trang
    # VD: "TT07.01.I                                                              Trang 3/11"
    if re.search(r'(TT|QT|HD)\d+\.\d+\.[A-Z]+\s{10,}(Trang\s+)?\d+/\d+', line, re.IGNORECASE):
        return True

    # Footer pattern: chỉ có mã + khoảng trắng thừa ở cuối dòng
    if re.match(r'^(TT|QT|HD)\d+\.\d+\.[A-Z]+\s{10,}$', line, re.IGNORECASE):
        return True

    # Footer pattern: "Quá trình Phát triển Phần mềm" đứng độc lập
    if re.match(r'^Quá trình (Phát triển|phát triển) (Phần mềm|phần mềm)\s*$', line_stripped, re.IGNORECASE):
        # Kiểm tra nếu dòng trước và sau đều trống hoặc là dòng ngắn
        if (not prev_line.strip() or len(prev_line.strip()) < 20) and \
                (not next_line.strip() or len(next_line.strip()) < 20):
            return True

    return False

def post_process_markdown(content):
    """
        Hậu xử lý nội dung Markdown để loại bỏ header/footer và thông tin nhiễu
        với khả năng phân biệt ngữ cảnh trong bảng
    """

    # Danh sách các pattern LUÔN loại bỏ (không phụ thuộc ngữ cảnh)
    always_remove_patterns = [
        # Header cơ bản
        re.compile(r'^#?\s*TRƯỜNG ĐẠI HỌC CẦN THƠ\s*$', re.IGNORECASE | re.MULTILINE),
        re.compile(r'^#?\s*TRUNG TÂM CÔNG NGHỆ PHẦN MỀM\s*$', re.IGNORECASE | re.MULTILINE),
        re.compile(r'CUSC[®]?\s*ISO\s*9001:2015', re.IGNORECASE),
        re.compile(r'Cantho University Software Center', re.IGNORECASE),
        re.compile(r'Sổ tay Phần mềm', re.IGNORECASE),
        re.compile(r'Quá trình Phát triển Phần mềm', re.IGNORECASE),

        # Tag page header/footer
        re.compile(r'<\s*/?\s*page_(header|footer)\s*>', re.IGNORECASE),

        # Footer kiểu mã + Trang X/Y
        re.compile(
            r'(TT|QT|HD)\d+\.\d+(?:\.[A-Z]+)?(?:/PM/CUSC)?(?:,\s*V?\d+(?:\.\d+)?)?\s+Trang\s*\d+\s*/\s*\d+',
            re.IGNORECASE
        ),

        # Chỉ có "Trang X/Y"
        re.compile(r'^Trang\s*\d+\s*/\s*\d+\s*$', re.IGNORECASE | re.MULTILINE),

        # Mã hiệu đơn lẻ
        re.compile(r'^(TT|QT|HD)\d+\.\d+(?:\.[A-Z]+)?(?:/PM/CUSC)?(?:,\s*V?\d+(?:\.\d+)?)?\s*$', re.IGNORECASE),

        # Phiên bản đơn lẻ
        re.compile(r'V\d+\.\d+', re.IGNORECASE),

        # Ngày áp dụng
        re.compile(r'Ngày áp dụng\s*:\s*\d{1,2}/\d{1,2}/\d{4}', re.IGNORECASE),
    ]

    lines = content.split('\n')
    filtered_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            if filtered_lines and filtered_lines[-1].strip():
                filtered_lines.append('')
            continue

        # Bỏ các pattern cố định
        if any(p.search(line) for p in always_remove_patterns):
            continue

        prev_line = lines[i - 1] if i > 0 else ''
        next_line = lines[i + 1] if i < len(lines) - 1 else ''

        # Nếu là footer nhưng KHÔNG nằm trong bảng thì bỏ qua
        if is_footer_line(line, prev_line, next_line) and not is_inside_table(lines, i):
            continue

        # Bỏ dòng chỉ toàn ký tự trang trí hoặc số
        if re.match(r'^[\s\-_=*#]+$', stripped) or re.match(r'^\d+\s*$', stripped):
            continue

        filtered_lines.append(line)

    # Dọn sạch thẻ <page_header> / <page_footer>
    content_no_page_tags = [
        l for l in filtered_lines
        if not re.search(r'<\s*/?\s*page_(header|footer)\s*>', l.strip(), re.IGNORECASE)
    ]

    # Gộp và làm sạch
    cleaned_content = '\n'.join(content_no_page_tags)
    cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
    cleaned_content = re.sub(r'[ \t]+$', '', cleaned_content, flags=re.MULTILINE)
    cleaned_content = re.sub(r'^#+\s*$', '', cleaned_content, flags=re.MULTILINE)
    return cleaned_content.strip()


def get_document_name(content):
    """
    Lấy tên văn bản từ dòng đầu tiên
    """
    lines = content.split('\n')

    for line in lines:
        line = line.strip()
        if line:
            # Bỏ dấu # nếu có
            name = re.sub(r'^#+\s*', '', line)
            return name

    return ""


def add_doc_name_to_roman(content, doc_name):
    """
    Bước 2: Thêm tên văn bản vào các mục V, VI, VII...
    """
    lines = content.split('\n')
    result_lines = []

    # Các số La Mã từ V trở đi
    romans = ['V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII', 'XIII', 'XIV', 'XV']

    for line in lines:
        modified = False

        for roman in romans:
            # Pattern 1: ## VI. HỒ SƠ
            match = re.match(rf'^(##?\s*)({roman})\.\s+(.+)$', line.strip())
            if match:
                prefix = match.group(1)  # ##
                roman_num = match.group(2)  # VI
                title = match.group(3)  # HỒ SƠ

                # Kiểm tra đã có tên chưa
                if doc_name.upper() not in title.upper():
                    result_lines.append(f"{prefix}{roman_num}. {title} {doc_name}")
                    modified = True
                    break

            # Pattern 2: VI. HỒ SƠ (không có ##)
            match = re.match(rf'^({roman})\.\s+(.+)$', line.strip())
            if match:
                roman_num = match.group(1)
                title = match.group(2)

                if doc_name.upper() not in title.upper():
                    result_lines.append(f"{roman_num}. {title} {doc_name}")
                    modified = True
                    break

        if not modified:
            result_lines.append(line)

    return '\n'.join(result_lines)

def fix_first_roman_headings(content: str) -> str:
    """
    Sửa 4 mục La Mã đầu tiên (I, II, III, IV) về cấp heading # thay vì ##.
    """
    lines = content.split('\n')
    fixed_lines = []

    # Danh sách 4 số La Mã cần fix
    roman_numerals = ['I', 'II', 'III', 'IV']
    fixed_count = {r: False for r in roman_numerals}

    for line in lines:
        stripped = line.strip()
        line_fixed = False

        # Kiểm tra từng số La Mã
        for roman in roman_numerals:
            if fixed_count[roman]:
                continue

            # Pattern: Bắt ## hoặc # ở đầu, theo sau là số La Mã và tiêu đề
            # Sử dụng raw string và escape đúng cách
            pattern_str = r'^##?\s*' + roman + r'\.\s*(.+)$'

            match = re.match(pattern_str, stripped, re.UNICODE)

            if match:
                title = match.group(1).strip()
                fixed_lines.append(f"# {roman}. {title}")
                fixed_count[roman] = True
                line_fixed = True
                break

        if not line_fixed:
            fixed_lines.append(line)

    total_fixed = sum(fixed_count.values())
    print(f"✅ Đã chỉnh {total_fixed} tiêu đề La Mã đầu (I–IV) về cấp #")
    return '\n'.join(fixed_lines)
