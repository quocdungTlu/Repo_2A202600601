"""Tải HotpotQA (distractor/validation) từ HuggingFace datasets-server và
convert sang format QAExample của lab.

Dùng:
    python scripts/build_hotpot_dataset.py --n 120 --out data/hotpot_dev.json
"""
from __future__ import annotations
import argparse
import json
import time
import urllib.request
from pathlib import Path

API = "https://datasets-server.huggingface.co/rows"
DATASET = "hotpotqa/hotpot_qa"
CONFIG = "distractor"
SPLIT = "validation"
VALID_LEVELS = {"easy", "medium", "hard"}


def fetch_rows(n: int) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while len(rows) < n:
        length = min(100, n - len(rows))
        url = f"{API}?dataset={DATASET.replace('/', '%2F')}&config={CONFIG}&split={SPLIT}&offset={offset}&length={length}"
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        batch = [item["row"] for item in data.get("rows", [])]
        if not batch:
            break
        rows.extend(batch)
        offset += length
        time.sleep(0.3)  # lịch sự với API
    return rows[:n]


def convert(row: dict, idx: int) -> dict:
    titles = row["context"]["title"]
    sentences = row["context"]["sentences"]
    para_by_title = {t: "".join(s).strip() for t, s in zip(titles, sentences)}

    # Lấy các đoạn gold theo supporting_facts; khớp title gần đúng nếu cần.
    gold_titles = list(dict.fromkeys(row.get("supporting_facts", {}).get("title", [])))
    context: list[dict] = []
    for gt in gold_titles:
        text = para_by_title.get(gt)
        if text is None:  # title supporting không khớp tuyệt đối -> tìm prefix
            for t, txt in para_by_title.items():
                if t.startswith(gt) or gt.startswith(t):
                    text = txt
                    break
        if text:
            context.append({"title": gt, "text": text})

    # Fallback: nếu chưa đủ 2 đoạn, bổ sung từ context đầu tiên.
    if len(context) < 2:
        for t, txt in para_by_title.items():
            if all(c["title"] != t for c in context):
                context.append({"title": t, "text": txt})
            if len(context) >= 2:
                break

    level = row.get("level", "medium")
    if level not in VALID_LEVELS:
        level = "medium"

    return {
        "qid": row.get("id") or f"hq{idx}",
        "difficulty": level,
        "question": row["question"].strip(),
        "gold_answer": str(row["answer"]).strip(),
        "context": context,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--out", default="data/hotpot_dev.json")
    args = ap.parse_args()

    print(f"Fetching {args.n} rows from HuggingFace ({DATASET}/{CONFIG}/{SPLIT}) ...")
    rows = fetch_rows(args.n)
    examples = [convert(r, i) for i, r in enumerate(rows)]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(examples, ensure_ascii=False, indent=2), encoding="utf-8")

    levels = {}
    for e in examples:
        levels[e["difficulty"]] = levels.get(e["difficulty"], 0) + 1
    print(f"Saved {len(examples)} examples -> {out}")
    print(f"Difficulty breakdown: {levels}")


if __name__ == "__main__":
    main()
