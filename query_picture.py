import os
import io
import base64

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")

def image_to_base64(image_path):
    with Image.open(image_path) as img:
        buffered = io.BytesIO()
        img.save(buffered, format=img.format)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")


llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",
    temperature=0.1,
    convert_system_message_to_human=True,
    google_api_key=api_key
)

# Prompt mặc định (nếu user không hỏi gì cụ thể)
default_prompt = """
Bạn là trợ lý AI hỗ trợ việc đọc và mô tả vấn đề trong bức ảnh đầu vào.

Hãy mô tả nội dung, ngữ cảnh hoặc bất kỳ chi tiết quan trọng nào bạn nhận thấy trong ảnh.
Trả lời bằng tiếng Việt, rõ ràng và súc tích.

Câu trả lời:
"""

def describe_image(image_path, user_prompt=None):
    """
    - Nếu user_prompt là None: mô tả ảnh.
    - Nếu user_prompt có nội dung: trả lời câu hỏi cụ thể về ảnh.
    """
    try:
        if os.path.exists(image_path):
            image_base64 = image_to_base64(image_path)
            image_data = {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                }
            }
        else:
            image_data = {"type": "image_url", "image_url": {"url": image_path}}

        # Xác định prompt đầu vào
        prompt_text = user_prompt.strip() if user_prompt else default_prompt

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt_text},
                image_data
            ]
        )

        response = llm.invoke([message])
        return response.content

    except Exception as e:
        print(f"Error: {e}")
        return None


if __name__ == '__main__':
    image_path = "C:\\Users\\LE TUAN DAT\\Pictures\\Screenshots\\Screenshot 2025-01-05 110156.png"

    # ✅ TH1: mô tả chung (không có prompt người dùng)
    print("=== Mô tả ảnh chung ===")
    description = describe_image(image_path)
    print(description)

    # ✅ TH2: hỏi cụ thể về ảnh
    print("\n=== Câu hỏi cụ thể ===")
    question = input("Nhập câu hỏi: ")
    answer = describe_image(image_path, user_prompt=question)
    print(answer)
