import os
import nest_asyncio

from llama_parse import LlamaParse
from dotenv import load_dotenv
from create_database import create_data

nest_asyncio.apply()

load_dotenv()

def llama_parse_md(data_dir):
    parser = LlamaParse(
        api_key=os.getenv("LLAMA_CLOUD_API_KEY"),
        parse_mode="parse_page_with_agent",
        model="anthropic-sonnet-4.0",
        high_res_ocr=True,
        adaptive_long_table=True,
        outlined_table_extraction=True,
        output_tables_as_HTML=True,
        language="vi",
        result_type="markdown"
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

            output_filename = f"{base_name}.md"
            output_path = os.path.join(save_dir, output_filename)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(full_md_content)

            print(f"Saved to {output_path}")

    create_data()
