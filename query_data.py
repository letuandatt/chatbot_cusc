from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CohereRerank
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from dotenv import load_dotenv

import os


load_dotenv()

PROMPT_TEMPLATE = """
Bạn là trợ lý AI trả lời các câu hỏi về quy trình, thủ tục nội bộ tại CUSC.

Sử dụng những thông tin trong ngữ cảnh bên dưới để trả lời câu hỏi của người dùng một cách chi tiết, chính xác và đầy đủ. 
Mỗi chunk context sẽ có metadata như: Tên văn bản (ten_van_ban), Mã hiệu (ma_hieu).

Hãy trả lời bằng tiếng Việt, với định dạng đẹp và dễ đọc:
- Dùng gạch đầu dòng (-) hoặc đánh số nếu có nhiều thông tin.
- Luôn cite nguồn ở cuối mỗi ý chính, dựa trên metadata của chunk tương ứng: Ví dụ "(Nguồn: [tên văn bản từ metadata], mã hiệu: [mã hiệu từ metadata])". Nếu multiple chunk, cite từng cái phù hợp.
- Không được bịa câu trả lời, chỉ dựa vào ngữ cảnh được cung cấp. Nếu không tìm thấy thông tin phù hợp, hãy ghi "Không tìm thấy thông tin phù hợp với câu hỏi của bạn. Vui lòng kiểm tra lại câu hỏi hoặc cung cấp thêm chi tiết."
- Ưu tiên thông tin từ các chunk relevant nhất.

Ngữ cảnh:
{context}

Câu hỏi: {question}

Câu trả lời chi tiết:
"""

def main():
    # Khởi tạo embedding model
    embedding_model = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )

    # Khởi tạo db
    db = Chroma(
        persist_directory="vectorstores/chroma_db",
        embedding_function=embedding_model,
        collection_name="docs_cusc"
    )

    # Retriever cơ bản
    base_retriever = db.as_retriever(search_kwargs={"k": 45})
    base_compressor = CohereRerank(
        top_n=10,
        model="rerank-multilingual-v3.0",
        cohere_api_key=os.getenv("COHERE_API_KEY")
    )

    retriever = ContextualCompressionRetriever(
        base_compressor=base_compressor,
        base_retriever=base_retriever,
    )

    def format_docs(docs):
        return "\n\n".join([
            f"Chunk: {doc.page_content}"
            f"Metadata: Tên văn bản: {doc.metadata.get('ten_van_ban', 'N/A')}, Mã hiệu: {doc.metadata.get('ma_hieu', 'N/A')}"
            for doc in docs
        ])

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
        temperature=0.1,
        convert_system_message_to_human=True,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )

    query_text = input("Enter your query: ")
    # print(format_docs(base_retriever.invoke(query_text)))

    prompt = PromptTemplate(
        template=PROMPT_TEMPLATE,
        input_variables=["context", "question"]
    )

    qa_chain = (
        {"context": lambda x: format_docs(retriever.invoke(x)), "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    full_response = ""
    for chunk in qa_chain.stream(query_text):
        full_response += chunk
        print(chunk, end="", flush=True)


main()
