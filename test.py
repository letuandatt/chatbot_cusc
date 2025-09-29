from llama_parse import LlamaParse
import os
from dotenv import load_dotenv

load_dotenv()

parser = LlamaParse(
        api_key=os.getenv("LLAMA_CLOUD_API_KEY"),
        parse_mode="parse_page_with_agent",
        model="anthropic-sonnet-4.0",
        high_res_ocr=True,
        adaptive_long_table=True,
        outlined_table_extraction=True,
        output_tables_as_HTML=True,
        result_type="json"
)

fp = 'data/QT07 - Phat trien phan mem.pdf'

documents = parser.load_data(fp)
[print(document.get_content()) for document in documents]
