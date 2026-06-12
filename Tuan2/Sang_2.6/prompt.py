import os
import google.generativeai as genai
from openai import OpenAI

# 1. Khởi tạo OpenAI / Gemini Client
# Thiết lập biến môi trường cho phiên hiện tại trước khi chạy script:
# $env:OPENAI_API_KEY = "your_openai_api_key_here"
# hoặc
# $env:GEMINI_API_KEY = "your_gemini_api_key_here"

def get_openai_api_key():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY chưa được đặt. "
            "Chạy trong PowerShell: $env:OPENAI_API_KEY = \"your_openai_api_key_here\"")
    return api_key


def get_gemini_api_key():
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY hoặc GOOGLE_API_KEY chưa được đặt. "
            "Chạy trong PowerShell: $env:GEMINI_API_KEY = \"your_gemini_api_key_here\"")
    return api_key


def get_api_provider():
    provider = os.environ.get("AI_PROVIDER", "").strip().lower()
    if provider == "openai":
        return "openai"
    if provider == "gemini":
        return "gemini"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    raise RuntimeError(
        "Cần đặt OPENAI_API_KEY hoặc GEMINI_API_KEY/GOOGLE_API_KEY. "
        "Bạn có thể dùng AI_PROVIDER=gemini để ép dùng Gemini.")


OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")

# Mẫu thử nghiệm: Một câu bình luận có cấu trúc phức tạp và từ lóng học đường
comment_text = "Slide lý thuyết hôm nay hơi nặng nha, nhưng bù lại bài Lab thực hành với bạn TA hỗ trợ siêu nhiệt tình luôn, 10 điểm!"

# =====================================================================
# KỸ THUẬT 1: ZERO-SHOT PROMPT (Hỏi thẳng, không làm mẫu)
# =====================================================================
zero_shot_prompt = f"""
Hãy phân tích câu bình luận của sinh viên sau đây.
Trả về kết quả theo định dạng JSON với 3 trường:
1. Sentiment: Tích cực / Tiêu cực / Trung lập
2. Target: Đối tượng được nhắc đến
3. Emotion_Score: Điểm số cảm xúc từ 1 đến 5

Câu bình luận: "{comment_text}"
"""

# =====================================================================
# KỸ THUẬT 2: FEW-SHOT PROMPT (Đưa ra 2 ví dụ mẫu để định hình tư duy)
# =====================================================================
few_shot_prompt = f"""
Hãy phân tích câu bình luận của sinh viên và trả về định dạng JSON gồm (Sentiment, Target, Emotion_Score từ 1-5).

### VÍ DỤ 1
Câu hỏi: "Giảng viên nói nhanh quá em không ghi bài kịp, mong thầy nói chậm lại."
Trả về: {{
    "Sentiment": "Tiêu cực",
    "Target": "Tốc độ giảng dạy của giảng viên",
    "Emotion_Score": 2
}}

### VÍ DỤ 2
Câu hỏi: "Bài tập lớn tuần này tuy dài nhưng giúp em hiểu sâu hơn về kiến trúc Agent."
Trả về: {{
    "Sentiment": "Tích cực",
    "Target": "Bài tập lớn (Assignment)",
    "Emotion_Score": 4
}}

### PHÂN TÍCH CÂU THỰC TẾ
Câu hỏi: "{comment_text}"
Trả về:
"""

# =====================================================================
# 2. Hàm gọi OpenAI / Gemini
# =====================================================================
def get_ai_response(prompt: str) -> str:
    provider = get_api_provider()

    if provider == "openai":
        client = OpenAI(api_key=get_openai_api_key())
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Bạn là một trợ lý giúp phân tích cảm xúc và trả về JSON chính xác."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=350
        )
        return completion.choices[0].message.content.strip()

    genai.configure(api_key=get_gemini_api_key())
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content(
        "Bạn là một trợ lý giúp phân tích cảm xúc và trả về JSON chính xác.\n\n" + prompt
    )
    return response.text.strip()


def generate_demo_results():
    provider = get_api_provider()
    model_used = OPENAI_MODEL if provider == "openai" else GEMINI_MODEL

    zero_result = get_ai_response(zero_shot_prompt)
    few_result = get_ai_response(few_shot_prompt)
    comparison = [
        {
            "criteria": "Ý tưởng cốt lõi",
            "zero_shot": "Ra lệnh trực tiếp, không cho ví dụ.",
            "few_shot": "Cung cấp ví dụ mẫu để định hướng kiểu trả lời."
        },
        {
            "criteria": "Chi phí token",
            "zero_shot": "Thấp hơn vì prompt ngắn.",
            "few_shot": "Cao hơn do kèm ví dụ mẫu."
        },
        {
            "criteria": "Độ chính xác format",
            "zero_shot": "Thấp hơn, dễ sai định dạng JSON.",
            "few_shot": "Cao hơn, dễ trả về đúng cấu trúc."
        },
        {
            "criteria": "Thích hợp khi",
            "zero_shot": "Thử nhanh, không cần mẫu.",
            "few_shot": "Cần đầu ra chuẩn, ổn định hơn."
        }
    ]

    return {
        "provider": provider,
        "model": model_used,
        "comment_text": comment_text,
        "zero_shot_prompt": zero_shot_prompt.strip(),
        "few_shot_prompt": few_shot_prompt.strip(),
        "zero_shot_output": zero_result,
        "few_shot_output": few_result,
        "comparison": comparison
    }


if __name__ == "__main__":
    results = generate_demo_results()
    print(f"Đang dùng provider: {results['provider']}, model: {results['model']}")
    print("⏳ Đang chạy thử nghiệm Zero-shot...")
    print(results["zero_shot_output"])
    print("⏳ Đang chạy thử nghiệm Few-shot...")
    print(results["few_shot_output"])
    print("\n" + "=" * 60)
    print("📊 BẢNG SO SÁNH KẾT QUẢ ĐẦU RA GIỮA ZERO-SHOT VÀ FEW-SHOT")
    print("=" * 60)
    for item in results["comparison"]:
        print(f"{item['criteria']:<30} {item['zero_shot']:<40} {item['few_shot']:<40}")

