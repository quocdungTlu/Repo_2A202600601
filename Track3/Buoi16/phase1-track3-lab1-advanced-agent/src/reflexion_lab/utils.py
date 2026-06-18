from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Iterable
from .schemas import QAExample, RunRecord

def normalize_answer(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text

def load_dataset(path: str | Path) -> list[QAExample]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [QAExample.model_validate(item) for item in raw]


_VALID_LEVELS = {"easy", "medium", "hard"}


def _coerce_context(ctx) -> list[dict]:
    """Chuẩn hoá context về [{title, text}] từ nhiều format khác nhau."""
    out: list[dict] = []
    if isinstance(ctx, dict) and "title" in ctx and "sentences" in ctx:
        # raw HotpotQA: {"title": [...], "sentences": [[...], ...]}
        for t, s in zip(ctx["title"], ctx["sentences"]):
            out.append({"title": str(t), "text": "".join(s) if isinstance(s, list) else str(s)})
    elif isinstance(ctx, list):
        for item in ctx:
            if isinstance(item, dict):
                title = item.get("title", "")
                text = item.get("text")
                if text is None:  # raw có thể là {"title":..,"sentences":[...]}
                    sents = item.get("sentences", [])
                    text = "".join(sents) if isinstance(sents, list) else str(sents)
                out.append({"title": str(title), "text": str(text)})
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                # raw HotpotQA dạng [title, [sent1, sent2, ...]]
                title, sents = item[0], item[1]
                text = "".join(sents) if isinstance(sents, list) else str(sents)
                out.append({"title": str(title), "text": text})
    return out


def load_dataset_flexible(path: str | Path) -> list[QAExample]:
    """Loader chịu lỗi cho Golden Test Set: chấp nhận QAExample chuẩn,
    raw HotpotQA, thiếu difficulty/gold_answer/qid/context. Không bao giờ crash
    vì 1 field lệch — điền mặc định an toàn để agent vẫn chạy được."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):  # có thể bọc trong {"data": [...]} hoặc {"examples": [...]}
        raw = raw.get("data") or raw.get("examples") or raw.get("questions") or [raw]

    examples: list[QAExample] = []
    for i, item in enumerate(raw):
        qid = str(item.get("qid") or item.get("id") or item.get("_id") or f"g{i}")
        level = item.get("difficulty") or item.get("level") or "hard"
        if level not in _VALID_LEVELS:
            level = "hard"
        question = str(item.get("question") or item.get("query") or "").strip()
        gold = item.get("gold_answer")
        if gold is None:
            gold = item.get("answer", "")  # raw HotpotQA dùng "answer"; blind set có thể rỗng
        context = _coerce_context(item.get("context", []))
        examples.append(QAExample(qid=qid, difficulty=level, question=question, gold_answer=str(gold), context=context))
    return examples

def save_jsonl(path: str | Path, records: Iterable[RunRecord]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")
