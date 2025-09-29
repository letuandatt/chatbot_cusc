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

Hãy trả lời bằng tiếng Việt, với định dạng đẹp và dễ đọc:

- Dùng gạch đầu dòng (-) hoặc đánh số nếu có nhiều thông tin.
- Không được bịa câu trả lời, chỉ dựa vào ngữ cảnh được cung cấp. Nếu không tìm thấy thông tin phù hợp, hãy ghi "Không tìm thấy thông tin phù hợp với câu hỏi của bạn. Vui lòng kiểm tra lại câu hỏi."
- Cố gắng đưa ra nguồn văn bản được trích xuất, thông tin nguồn là: Tên văn bản, mã tài liệu (số hiệu), ngày có hiệu lực

Ngữ cảnh:
{context}

Câu hỏi:
{question}

Câu trả lời chi tiết:
"""

def main():
    embedding_model = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )
    db = Chroma(
        persist_directory="vectorstores/chroma_db",
        embedding_function=embedding_model
    )
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
        temperature=0.1,
        convert_system_message_to_human=True,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )

    query_text = input("Enter your query: ")

    results = db.similarity_search_with_relevance_scores(query_text, k=10)
    print(results)
    if len(results) == 0:
        print("No results found.")
        return

    context = "\n\n---\n\n".join([doc.page_content for doc, _score in results])
    print(context)
    prompt = PromptTemplate(
        template=PROMPT_TEMPLATE,
        input_variables=["context", "question"]
    )

    qa_chain = (
        {"context": lambda x: context, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    result = qa_chain.invoke(query_text)
    print(result)


main()
