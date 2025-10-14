import os
import nest_asyncio
import re

from llama_parse import LlamaParse
from dotenv import load_dotenv

nest_asyncio.apply()

load_dotenv()

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

            cleaned_content = fix_first_roman_headings(full_md_content)

            output_filename = f"{base_name}.md"
            output_path = os.path.join(save_dir, output_filename)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(cleaned_content)

            print(f"Saved to {output_path}")


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
