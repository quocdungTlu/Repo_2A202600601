"""
Mock LLM — dung chung cho tat ca vi du.
Khong can API key that. Tra loi gia lap de focus vao deployment concept.
"""
import time
import random


MOCK_RESPONSES = {
    "default": [
        "Day la cau tra loi tu AI agent (mock). Trong production, day se la response tu OpenAI/Anthropic.",
        "Agent dang hoat dong tot! (mock response) Hoi them cau hoi di nhe.",
        "Toi la AI agent duoc deploy len cloud. Cau hoi cua ban da duoc nhan.",
    ],
    "docker": ["Container la cach dong goi app de chay o moi noi. Build once, run anywhere!"],
    "deploy": ["Deployment la qua trinh dua code tu may ban len server de nguoi khac dung duoc."],
    "health": ["Agent dang hoat dong binh thuong. All systems operational."],
}


def ask(question: str, delay: float = 0.1) -> str:
    time.sleep(delay + random.uniform(0, 0.05))
    question_lower = question.lower()
    for keyword, responses in MOCK_RESPONSES.items():
        if keyword in question_lower:
            return random.choice(responses)
    return random.choice(MOCK_RESPONSES["default"])


def ask_stream(question: str):
    response = ask(question)
    for word in response.split():
        time.sleep(0.05)
        yield word + " "
