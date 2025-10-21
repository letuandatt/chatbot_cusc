import os
import io
import base64

from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CohereRerank
from langchain_chroma import Chroma
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from dotenv import load_dotenv
from PIL import Image

# Tải các biến môi trường từ file .env
load_dotenv()


# --- CÁC HÀM TIỆN ÍCH VÀ CẤU HÌNH ---

def image_to_base64(image_path):
    """Chuyển đổi file ảnh sang chuỗi base64."""
    try:
        with Image.open(image_path) as img:
            # Chuyển đổi ảnh sang RGB để đảm bảo tương thích
            if img.mode != 'RGB':
                img = img.convert('RGB')
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG")  # Lưu dưới dạng JPEG để nhất quán
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"Lỗi xử lý ảnh: {e}")
        return None


def initialize_llm():
    """Khởi tạo mô hình ngôn ngữ lớn (LLM)."""
    # Sử dụng model hỗ trợ cả text và image
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
        temperature=0.1,  # Tăng nhẹ để câu trả lời tự nhiên hơn
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )


# --- LOGIC XỬ LÝ QUERY VĂN BẢN (RAG) ---

PROMPT_TEMPLATE_RAG = """
Bạn là trợ lý AI trả lời các câu hỏi về quy trình, thủ tục nội bộ tại CUSC.

Sử dụng những thông tin trong ngữ cảnh bên dưới để trả lời câu hỏi của người dùng một cách chi tiết, chính xác và đầy đủ.
Mỗi chunk context sẽ có metadata như: Tên văn bản (ten_van_ban), Mã hiệu (ma_hieu).

Hãy trả lời bằng tiếng Việt, với định dạng đẹp và dễ đọc:
- Dùng gạch đầu dòng (-) hoặc đánh số nếu có nhiều thông tin.
- Luôn trích dẫn nguồn ở cuối mỗi ý chính, dựa trên metadata của chunk tương ứng: Ví dụ "(Nguồn: [tên văn bản từ metadata], mã hiệu: [mã hiệu từ metadata])". Nếu nhiều chunk, hãy trích dẫn từng cái phù hợp.
- Không được bịa đặt câu trả lời, chỉ dựa vào ngữ cảnh được cung cấp. Nếu không tìm thấy thông tin phù hợp, hãy ghi "Không tìm thấy thông tin phù hợp với câu hỏi của bạn."

Ngữ cảnh:
{context}

Câu hỏi: {question}

Câu trả lời chi tiết:
"""


def handle_text_query(llm, query_text):
    """Xử lý câu hỏi chỉ có văn bản bằng pipeline RAG."""
    print("--- 🔍 Đang xử lý câu hỏi văn bản bằng RAG ---")

    # 1. Khởi tạo embedding model
    embedding_model = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )

    # 2. Khởi tạo Chroma DB
    db = Chroma(
        persist_directory="vectorstores/chroma_db_1",
        embedding_function=embedding_model,
        collection_name="docs_cusc"
    )

    # 3. Thiết lập Retriever và Reranker
    base_retriever = db.as_retriever(search_kwargs={"k": 40})
    base_compressor = CohereRerank(
        top_n=6,  # Giữ lại 5 kết quả relevant nhất
        model="rerank-multilingual-v3.0",
        cohere_api_key=os.getenv("COHERE_API_KEY")
    )
    retriever = ContextualCompressionRetriever(
        base_compressor=base_compressor,
        base_retriever=base_retriever,
    )

    def format_docs(docs):
        return "\n\n".join([
            f"Nội dung Chunk: {doc.page_content}\n"
            f"Metadata: (Tên văn bản: {doc.metadata.get('ten_van_ban', 'N/A')}, Mã hiệu: {doc.metadata.get('ma_hieu', 'N/A')})"
            for doc in docs
        ])

    # 4. Xây dựng và thực thi chuỗi RAG
    prompt = PromptTemplate.from_template(PROMPT_TEMPLATE_RAG)
    rag_chain = (
        {"context": lambda x: format_docs(retriever.invoke(x)), "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    # 5. Stream kết quả
    full_response = ""
    for chunk in rag_chain.stream(query_text):
        full_response += chunk
        print(chunk, end="", flush=True)
    print("\n")  # In dòng mới sau khi kết thúc


# --- LOGIC XỬ LÝ QUERY ĐA PHƯƠNG THỨC (TEXT + IMAGE) ---

PROMPT_TEMPLATE_VISION = """
Bạn là một trợ lý AI thông minh. Dựa vào hình ảnh và câu hỏi được cung cấp, hãy đưa ra câu trả lời chi tiết, chính xác và hữu ích.
Trả lời bằng tiếng Việt.

Câu hỏi: {question}

Câu trả lời:
"""


def handle_multimodal_query(llm, query_text, image_path):
    """Xử lý câu hỏi có cả văn bản và hình ảnh."""
    print(f"--- 🖼️ Đang xử lý câu hỏi với ảnh: {os.path.basename(image_path)} ---")

    # 1. Chuẩn bị dữ liệu ảnh
    image_base64 = image_to_base64(image_path)
    if not image_base64:
        print("Không thể xử lý ảnh. Vui lòng kiểm tra lại đường dẫn hoặc định dạng file.")
        return

    image_data = {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
    }

    # 2. Tạo prompt
    prompt_text = PROMPT_TEMPLATE_VISION.format(question=query_text)

    # 3. Tạo message và gọi LLM
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt_text},
            image_data
        ]
    )

    # 4. Stream kết quả
    full_response = ""
    for chunk in llm.stream([message]):
        content = chunk.content
        full_response += content
        print(content, end="", flush=True)
    print("\n")  # In dòng mới sau khi kết thúc


# --- HÀM CHÍNH ĐIỀU PHỐI ---

def main():
    """Hàm chính để chạy chatbot."""
    llm = initialize_llm()
    print("🤖 Chatbot CUSC đã sẵn sàng. Nhập 'exit' để thoát.")

    while True:
        # 1. Nhận câu hỏi từ người dùng
        query_text = input("\n👤 Bạn hỏi: ")
        if query_text.lower() == 'exit':
            break

        # 2. Hỏi đường dẫn ảnh (tùy chọn)
        image_path = input("🖼️ Nhập đường dẫn ảnh (hoặc nhấn Enter để bỏ qua): ").strip()

        print("\n💡 Trả lời:")

        # 3. Điều hướng logic xử lý
        if image_path and os.path.exists(image_path):
            handle_multimodal_query(llm, query_text, image_path)
        elif image_path:
            print(f"⚠️ Lỗi: Không tìm thấy file ảnh tại '{image_path}'")
            print(f"Vui lòng xem lại file ảnh!")
            continue
        else:
            handle_text_query(llm, query_text)


if __name__ == '__main__':
    main()
