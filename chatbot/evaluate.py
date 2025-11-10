import asyncio
import logging

from datasets import Dataset

from chatbot.query_rag import (
    GLOBAL_RETRIEVER,
    TEXT_LLM,
    format_docs, RAG_PROMPT_TEMPLATE
)
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_recall,
    context_precision
)
from ragas.llms import llm_factory

logging.basicConfig(level=logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.ERROR)
logging.getLogger("cohere").setLevel(logging.ERROR)

# --- Tạo bộ dữ liệu đánh giá ---
dataset_list = [
    # --- TT07.01.I - Kinh doanh phan mem ---
    {
        "question": "Mục đích của thủ tục kinh doanh phần mềm là gì?",
        "ground_truth": "Hướng dẫn thực hiện hoạt động kinh doanh các sản phẩm, dịch vụ phần mềm tại CUSC."
    },
    {
        "question": "Ai là người lập thủ tục TT07.01.1 (Kinh doanh phần mềm)?",
        "ground_truth": "Trần Thị Ngọc Liễu."
    },
    {
        "question": "Khi nào thì thực hiện báo giá cho khách hàng?",
        "ground_truth": "Việc báo giá được thực hiện sau khi tiếp nhận yêu cầu và xác định rằng yêu cầu đó không cần mời thầu."
    },
    {
        "question": "Thời gian tối đa để báo giá cho sản phẩm mới là bao lâu?",
        "ground_truth": "Thời gian tối đa là 384 giờ (16 ngày, trừ T7, CN) kể từ khi nhận đủ thông tin của khách hàng."
    },
    {
        "question": "Hồ sơ pháp lý như hợp đồng được lưu trữ trong bao lâu?",
        "ground_truth": "Hồ sơ pháp lý (hợp đồng, phụ lục, nghiệm thu thanh lý) được lưu trữ 10 năm."
    },
    # --- TT07.05.I - Kiem dinh ---
    {
        "question": "Mục đích của thủ tục kiểm định TT07.05.I là gì?",
        "ground_truth": "Hướng dẫn thực hiện hoạt động kiểm định phần mềm tại CUSC."
    },
    {
        "question": "Ai là người phê duyệt thủ tục kiểm định (TT07.05.1)?",
        "ground_truth": "Giám đốc Lê Hoàng Thảo."
    },
    {
        "question": "Thế nào là kiểm định hỗ trợ?",
        "ground_truth": "Đó là trường hợp kiểm định khi kế hoạch dự án không có giai đoạn kiểm định chính thức, có thể bỏ qua bước lập kế hoạch và thiết kế kiểm định."
    },
    {
        "question": "Môi trường kiểm định có được phép cài đặt chung với môi trường dự án không?",
        "ground_truth": "Không. Môi trường kiểm định phải độc lập với môi trường đang thực hiện dự án."
    },
    {
        "question": "Biên bản kiểm định (BM07.20.L) được lưu ở đâu?",
        "ground_truth": "Được lưu vào thư mục kiểm định trong cây thư mục dự án."
    },
    # --- TT07.10 - Ho tro ky thuat ---
    {
        "question": "Mục đích của thủ tục hỗ trợ kỹ thuật (TT07.10) là gì?",
        "ground_truth": "Hướng dẫn thực hiện các hoạt động hỗ trợ kỹ thuật."
    },
    {
        "question": "Nhóm hỗ trợ kỹ thuật bao gồm những mảng quản lý nào?",
        "ground_truth": "Bao gồm 4 mảng: Quản lý cấu hình, Quản lý hệ thống, Quản lý hosting – domain, và Quản lý tài sản - thiết bị."
    },
    {
        "question": "Khi nào thì tài khoản của một cán bộ bị vô hiệu hóa (disable)?",
        "ground_truth": "Khi nhận được thông tin cán bộ đó nghỉ việc, đi học, tạm nghỉ, hoặc các trường hợp không còn công tác tại BP."
    },
    {
        "question": "Ai chịu trách nhiệm sao lưu dữ liệu của các dự án trong Bộ phận?",
        "ground_truth": "Cán bộ quản lý hệ thống."
    },
    # --- TT07.11 - Cham soc khach hang ---
    {
        "question": "Mục đích của thủ tục chăm sóc khách hàng (TT07.11) là gì?",
        "ground_truth": "Hướng dẫn thực hiện các hoạt động CSKH."
    },
    {
        "question": "Ai là người lập thủ tục TT07.11/PM/CUSC?",
        "ground_truth": "TRẦN THỊ NGỌC LIỄU."
    },
    {
        "question": "Phiếu bảo hành (BM07.85/PM/CUSC) được lập khi nào?",
        "ground_truth": "Được lập khi xác định thời gian bắt đầu chuyển sang giai đoạn bảo hành."
    },
    {
        "question": "Khi nào CUSC gửi thông báo hết hạn bảo hành cho khách hàng?",
        "ground_truth": "02 tuần trước khi hết hạn bảo hành."
    },
    {
        "question": "Khoảng cách tối đa giữa 2 lần thu thập phiếu ý kiến khách hàng là bao lâu?",
        "ground_truth": "Tối đa 6 tháng phải thực hiện thu thập."
    },
    # --- TT07.04 - Quan tri va thuc hien du an ---
    {
        "question": "Mục đích của thủ tục quản trị và thực hiện dự án (TT07.04) là gì?",
        "ground_truth": "Hướng dẫn quản trị và thực hiện một cách hiệu quả và tối ưu nhất đối với các dự án phần mềm tại CUSC."
    },
    {
        "question": "Thủ tục Quản trị dự án (TT07.04) có áp dụng cho nhóm ITO không?",
        "ground_truth": "Không, thủ tục này áp dụng cho tất cả dự án hình thành tại BPPM (trừ các dự án thuộc Nhóm ITO)."
    },
    {
        "question": "Ai là người chịu trách nhiệm quản lý phiên bản (version control) của sản phẩm dự án?",
        "ground_truth": "Trưởng dự án chịu trách nhiệm quản lý phiên bản và lưu trữ sản phẩm dự án."
    },
    {
        "question": "Kế hoạch dự án tổng thể sử dụng biểu mẫu (BM) nào?",
        "ground_truth": "Sử dụng mẫu BM07.01/PM/CUSC."
    },
    {
        "question": "Việc xem xét code (code review) giữa các thành viên được ghi nhận vào biểu mẫu nào?",
        "ground_truth": "Ghi kết quả vào biên bản xem xét (BM07.14/PM/CUSC)."
    },
    {
        "question": "Giai đoạn triển khai dự án bao gồm mấy bước chính?",
        "ground_truth": "Bao gồm 7 bước: Lập kế hoạch triển khai, Cài đặt phần mềm, Đào tạo người dùng, Vận hành thử/kiểm thử, Bàn giao/vận hành chính thức, Tổng hợp kết quả triển khai, và Lưu hồ sơ."
    },
    # --- TT07.02 - Hoach dinh ---
    {
        "question": "Mục đích của thủ tục hoạch định (TT07.02) là gì?",
        "ground_truth": "Hướng dẫn thực hiện công việc hoạch định, phân công, báo cáo và đánh giá chỉ tiêu Bộ phận Phần mềm."
    },
    {
        "question": "Việc báo cáo hoạt động của Nhóm Kiểm định được thực hiện theo thủ tục nào?",
        "ground_truth": "Thực hiện theo hướng dẫn chi tiết trong Thủ tục Kiểm định (TT07.05/PM/CUSC)."
    },
    {
        "question": "Việc phân công và báo cáo công việc có thể được ghi nhận qua những phương tiện nào?",
        "ground_truth": "Qua nhiều phương tiện, bao gồm: văn bản (kế hoạch, biên bản họp), công cụ (redmine), hồ sơ đánh giá NSLĐ, email, hoặc chỉ đạo trực tiếp."
    },
    # --- QT07 - Phat trien phan mem ---
    {
        "question": "Mục đích của quá trình QT07 - Phát triển phần mềm là gì?",
        "ground_truth": "Mô tả các hoạt động trong quá trình phát triển phần mềm."
    },
    {
        "question": "Quá trình QT07 bao gồm những thủ tục (TT) chính nào?",
        "ground_truth": "Bao gồm: Hoạch định (TT07.02), Kinh doanh (TT07.01), Quản lý Nhóm dự án (TT07.03), Quản trị và thực hiện dự án (TT07.04), Kiểm định (TT07.05), Hỗ trợ kỹ thuật (TT07.06), và Chăm sóc khách hàng (TT07.07)."
    },
    {
        "question": "Thủ tục quản lý hosting-domain nằm trong quy trình nào?",
        "ground_truth": "Nằm trong Thủ tục Hỗ trợ kỹ thuật (TT07.06/PM/CUSC)."
    },
    {
        "question": "Ai là người lưu trữ hồ sơ dự án?",
        "ground_truth": "Trưởng dự án và NV Quản lý cấu hình."
    },
    {
        "question": "Hồ sơ dự án được lưu trữ vĩnh viễn ở đâu?",
        "ground_truth": "Hồ sơ file được lưu vĩnh viễn trong thư mục dự án trên server."
    },
]

print(f"Đã tạo bộ dữ liệu {len(dataset_list)} câu hỏi/câu trả lời.")

# --- Tạo chain RAG ---
rag_chain = (
    {
        "context": RunnablePassthrough() | (lambda x: format_docs(GLOBAL_RETRIEVER.invoke(x["question"]))),
        "question": RunnablePassthrough() | (lambda x: x["question"]),
        "chat_history": lambda x: [],
    }
    | RAG_PROMPT_TEMPLATE
    | TEXT_LLM
    | StrOutputParser()
)

print("Đã tái tạo chain RAG để đánh giá.")

# --- Hàm đánh giá ---
async def run_evaluation():
    print("\n--- BẮT ĐẦU CHẠY ĐÁNH GIÁ (GENERATING ANSWERS) ---")

    generated_answers = []

    def sync_get_contexts(question):
        return GLOBAL_RETRIEVER.invoke(question)

    def sync_get_answer(question, context):
        return rag_chain.invoke({
            "question": question,
            "chat_history": [],
            "context": format_docs(context)
        })

    for i, item in enumerate(dataset_list):
        question = item["question"]
        print(f"Đang xử lý câu hỏi {i+1}/{len(dataset_list)}: {question[:50]}...")

        try:
            retrieved_docs = await asyncio.to_thread(sync_get_contexts, question)
            contexts = [doc.page_content for doc in retrieved_docs]

            answer = await asyncio.to_thread(sync_get_answer, question, retrieved_docs)

            generated_answers.append({
                "question": question,
                "ground_truth": item["ground_truth"],
                "generated_answer": answer,
                "contexts": contexts
            })
        except Exception as ex:
            print(f"Lỗi khi xử lý câu hỏi '{question}': {ex}")
            generated_answers.append({
                "question": question,
                "ground_truth": item["ground_truth"],
                "answer": f"LỖI: {ex}",
                "contexts": []
            })

    print("--- HOÀN TẤT GENERATE ANSWERS ---")

    dataset = Dataset.from_list(generated_answers)

    eval_llm = llm_factory(model="gpt-4o")

    metrics = [
        faithfulness,
        answer_relevancy,
        context_recall,
        context_precision
    ]

    print(f"\n--- BẮT ĐẦU ĐÁNH GIÁ VỚI RAGAS (LLM: gpt-4o) ---")

    result = evaluate(
        dataset,
        metrics=metrics,
        llm=eval_llm,
    )

    print("--- HOÀN TẤT ĐÁNH GIÁ ---")

    print("\n\n--- KẾT QUẢ ĐÁNH GIÁ RAGAS ---")
    print(result)

    df = result.to_pandas()
    print("\n--- CHI TIẾT (DẠNG BẢNG) ---")
    print(df.to_string())

    df.to_csv("ragas_evaluation_results.csv", index=False, encoding="utf-8-sig")
    print("\nĐã lưu kết quả chi tiết vào file 'ragas_evaluation_results.csv'")

if __name__ == '__main__':
    asyncio.run(run_evaluation())