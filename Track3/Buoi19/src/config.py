"""Cấu hình dùng chung cho Lab Day 19 — GraphRAG.

LLM đi qua antco gateway (OpenAI-compatible). Gateway yêu cầu header
User-Agent tùy biến nên ta dựng OpenAI client với http_client riêng.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM / antco gateway ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")  # Fireworks: https://api.fireworks.ai/inference/v1
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-nano")

# --- Đường dẫn ---
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(ROOT_DIR, "dataset", "dataset")  # 70 file .txt giáo viên cấp
OUTPUT_DIR = os.path.join(ROOT_DIR, "outputs")
CACHE_DIR = os.path.join(ROOT_DIR, ".cache")

# Giới hạn ký tự content mỗi doc khi đưa vào LLM trích triples (kiểm soát token)
MAX_DOC_CHARS = 6000          # kích thước 1 chunk extraction (và cap cho flat_rag)
FULL_DOC_CHARS = 24000        # cap tổng content dùng cho extraction (doc dài sẽ chunk)
MAX_EXTRACT_CHUNKS = 4        # số chunk tối đa LLM trích / doc (kiểm soát chi phí)

# File trung gian / kết quả
TRIPLES_PATH = os.path.join(OUTPUT_DIR, "triples.json")
GRAPH_PATH = os.path.join(OUTPUT_DIR, "graph.gpickle")
GRAPH_IMG_PATH = os.path.join(OUTPUT_DIR, "knowledge_graph.png")
BENCH_RESULTS_PATH = os.path.join(OUTPUT_DIR, "benchmark_results.csv")
COST_REPORT_PATH = os.path.join(OUTPUT_DIR, "cost_report.md")
USAGE_LOG_PATH = os.path.join(OUTPUT_DIR, "llm_usage.json")

for _d in (OUTPUT_DIR, CACHE_DIR):
    os.makedirs(_d, exist_ok=True)

# --- Embedding cho Flat RAG ---
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
FLAT_TOP_K = 5

# --- GraphRAG ---
GRAPH_HOPS = 2  # bán kính duyệt đồ thị quanh thực thể truy vấn


def make_openai_client():
    """OpenAI client — hỗ trợ cả OpenAI thật lẫn custom gateway (antco/Fireworks).

    Lưu ý: openai SDK đọc biến env OPENAI_BASE_URL ngay cả khi pass api_key tường minh.
    Nếu OPENAI_BASE_URL="" (rỗng), SDK dùng nó thành base URL không hợp lệ → lỗi connection.
    Giải pháp: unset biến env đó khi rỗng trước khi khởi tạo client.
    """
    import os
    from openai import OpenAI
    import httpx

    if not OPENAI_BASE_URL:
        os.environ.pop("OPENAI_BASE_URL", None)

    kwargs: dict = {"api_key": OPENAI_API_KEY}
    if OPENAI_BASE_URL:
        kwargs["base_url"] = OPENAI_BASE_URL
        kwargs["http_client"] = httpx.Client(
            headers={"User-Agent": "python-httpx/0.27.0"},
            timeout=60.0,
        )
    return OpenAI(**kwargs)
