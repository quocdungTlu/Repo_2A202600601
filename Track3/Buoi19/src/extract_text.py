"""Bước 1 — Indexing (dataset văn bản thô): trích Triples bằng LLM.

Khác với extract.py (parse CSV có cấu trúc), module này xử lý 70 file .txt giáo viên
cấp — văn bản web scraping về ngành xe điện (EV) Mỹ. Đây là kịch bản entity/relation
extraction từ "văn bản thô" đúng như đề lab mô tả.

Quy trình mỗi doc:
  1. Parse các trường Query / Title / Link / Snippet / Full Content.
  2. Làm sạch boilerplate (cookie, mailing list, navigation).
  3. Cắt còn MAX_DOC_CHARS ký tự (kiểm soát token).
  4. LLM trích list {subject, relation, object} (relation dạng UPPER_SNAKE).
  5. Cache theo hash nội dung.
"""

import os
import re
import glob
import json

import config
from llm import LLM, UsageTracker

# Các dòng boilerplate thường gặp cần loại bỏ
BOILERPLATE_PATTERNS = [
    r"We use cookies.*",
    r"This website uses cookies.*",
    r"Essential cookies.*",
    r"We use Google Analytics.*",
    r"Join our mailing list.*",
    r"Find out more\.?",
    r"Contact Us",
    r"Download",
    r"^\s*$",
]
_BOILER_RE = re.compile("|".join(f"({p})" for p in BOILERPLATE_PATTERNS), re.IGNORECASE)


def parse_doc(path: str) -> dict:
    """Tách Query/Title/Link/Snippet/Full Content từ một file .txt."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    fields = {"query": "", "title": "", "link": "", "snippet": "", "content": ""}
    m = re.search(r"^Query:\s*(.*)$", raw, re.MULTILINE)
    if m:
        fields["query"] = m.group(1).strip()
    m = re.search(r"^Title:\s*(.*)$", raw, re.MULTILINE)
    if m:
        fields["title"] = m.group(1).strip()
    m = re.search(r"^Link:\s*(.*)$", raw, re.MULTILINE)
    if m:
        fields["link"] = m.group(1).strip()
    m = re.search(r"^Snippet:\s*(.*)$", raw, re.MULTILINE)
    if m:
        fields["snippet"] = m.group(1).strip()

    # Full Content: lấy phần sau "Full Content:"
    idx = raw.find("Full Content:")
    content = raw[idx + len("Full Content:"):] if idx != -1 else raw
    fields["content"] = clean_content(content)
    return fields


def clean_content(text: str) -> str:
    """Loại boilerplate + nén khoảng trắng, cắt còn MAX_DOC_CHARS."""
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if _BOILER_RE.fullmatch(line):
            continue
        lines.append(line)
    cleaned = " ".join(lines)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[: config.MAX_DOC_CHARS]


# ----------------------------- LLM extraction -----------------------------
EXTRACT_SYS = (
    "You are a precise knowledge-graph extraction engine for the US electric vehicle (EV) industry.\n"
    "Extract relationships where BOTH subject and object are NAMED ENTITIES — i.e. specific "
    "companies, people, organizations, government bodies, vehicle models/products, locations, "
    "or named policies/regulations.\n"
    "STRICT RULES:\n"
    "1. Subject and object must be short canonical entity names (e.g. 'Tesla', 'Nikola Corporation', "
    "'Elon Musk', 'California', 'ZEV Regulation', 'Inflation Reduction Act', 'Model 3'). "
    "Max ~5 words, NO embedded statistics, years, or parenthetical numbers in the name.\n"
    "2. Do NOT create nodes for raw numbers, percentages, or statistics. Skip metric-only facts.\n"
    "3. Use ONLY these canonical relations: PRODUCES, SELLS, COMPETES_WITH, PARTNERS_WITH, "
    "INVESTED_IN, ACQUIRED, SUPPLIES, CEO_OF, FOUNDED, HEADQUARTERED_IN, OPERATES_IN, "
    "LOCATED_IN, REGULATES, SUBJECT_TO, SUPPORTS, MANUFACTURES, RIVAL_OF, SUBSIDIARY_OF, "
    "ANALYZES, REPORTED_ON, MENTIONS.\n"
    "Return ONLY JSON: {\"triples\": [{\"subject\": \"...\", \"relation\": \"...\", \"object\": \"...\"}]}.\n"
    "Extract at most 12 high-quality entity-to-entity triples. If none, return {\"triples\": []}."
)


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    a, b = text.find("{"), text.rfind("}")
    if a != -1 and b != -1:
        text = text[a : b + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def extract_from_doc(llm: LLM, doc: dict, doc_id: str) -> list[dict]:
    if not doc["content"].strip():
        return []
    header = f"Title: {doc['title']}\nTopic query: {doc['query']}\n\n"
    user = header + "Document:\n" + doc["content"]
    out = _parse_json(llm.chat(EXTRACT_SYS, user, stage="extract_text", max_tokens=2000))
    triples = []
    for t in out.get("triples", []) or []:
        s = str(t.get("subject", "")).strip()
        r = str(t.get("relation", "")).strip().upper().replace(" ", "_")
        o = str(t.get("object", "")).strip()
        if s and r and o and s.lower() != o.lower():
            triples.append({"subject": s, "relation": r, "object": o,
                            "kind": "edge", "source": doc_id})
    return triples


# ----------------------------- orchestrator -----------------------------
def build_triples_from_text(limit: int | None = None, use_cache: bool = True):
    tracker = UsageTracker()
    llm = LLM(tracker=tracker, use_cache=use_cache)

    paths = sorted(
        glob.glob(os.path.join(config.DATASET_DIR, "*.txt")),
        key=lambda p: int(re.search(r"(\d+)", os.path.basename(p)).group(1)),
    )
    if limit:
        paths = paths[:limit]

    all_triples = []
    entities = set()
    for i, path in enumerate(paths, 1):
        doc_id = os.path.basename(path)
        doc = parse_doc(path)
        triples = extract_from_doc(llm, doc, doc_id)
        all_triples.extend(triples)
        for t in triples:
            entities.add(t["subject"])
            entities.add(t["object"])
        if i % 10 == 0 or i == len(paths):
            print(f"  [{i:02d}/{len(paths)}] {doc_id}: +{len(triples)} triples "
                  f"(total {len(all_triples)}, {tracker.total_tokens} tok)")

    payload = {
        "source": "dataset (70 raw text docs - EV industry)",
        "entities": sorted(entities),
        "triples": all_triples,
        "counts": {"docs": len(paths), "triples": len(all_triples),
                   "entities": len(entities)},
        "usage": tracker.to_dict(),
    }
    with open(config.TRIPLES_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tracker.save()
    return payload


if __name__ == "__main__":
    import sys
    limit = None
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])
    p = build_triples_from_text(limit=limit)
    print("\nDocs     :", p["counts"]["docs"])
    print("Triples  :", p["counts"]["triples"])
    print("Entities :", p["counts"]["entities"])
    print("Usage    :", json.dumps(p["usage"], indent=2))
    print("Saved ->", config.TRIPLES_PATH)
