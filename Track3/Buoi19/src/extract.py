"""Bước 1 — Indexing: trích xuất thực thể & quan hệ (Triples) từ AI Company Corpus.

Hybrid:
  (A) Structured  -> trích deterministic từ các trường CSV sạch (founding, revenue,
      staff, valuation, compute, product, division, domain). Không tốn token.
  (B) Notes/văn xuôi -> dùng LLM (Fireworks gpt-oss-120b) trích quan hệ ĐẦU TƯ
      (investor -> company) ẩn trong cột text của bảng funding_rounds. Đây là nguồn
      tạo các cạnh đầu tư chéo giữa các công ty (multi-hop).

Mỗi triple: {subject, relation, object, kind, source}
  kind = "edge" -> cạnh giữa hai thực thể (đưa vào đồ thị, dùng để duyệt multi-hop)
  kind = "attr" -> thuộc tính vô hướng của một thực thể (gắn vào node, không thành node)
"""

import os
import csv
import json
import datetime as dt

import config
from llm import LLM, UsageTracker

csv.field_size_limit(10_000_000)


# ----------------------------- helpers -----------------------------
def _rows(fname):
    with open(os.path.join(config.DATA_DIR, fname), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _fmt_money(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v >= 1e9:
        return f"${v/1e9:.1f}B"
    if v >= 1e6:
        return f"${v/1e6:.0f}M"
    return f"${v:,.0f}"


def _latest(rows, date_key, value_key, filt=None):
    """Lấy bản ghi có ngày mới nhất với value_key không rỗng."""
    best, best_d = None, None
    for r in rows:
        if filt and not filt(r):
            continue
        if not (r.get(value_key) or "").strip():
            continue
        d = _parse_date(r.get(date_key, ""))
        if d is None:
            continue
        if best_d is None or d > best_d:
            best, best_d = r, d
    return best


def _T(subject, relation, obj, kind, source):
    return {"subject": subject, "relation": relation, "object": obj, "kind": kind, "source": source}


# ----------------------------- (A) structured -----------------------------
def extract_structured():
    triples = []
    companies = _rows("ai_companies.csv")
    company_names = [r["Name"].strip() for r in companies if r["Name"].strip()]

    # --- ai_companies.csv: founding date, type, domains ---
    for r in companies:
        name = r["Name"].strip()
        if not name:
            continue
        src = "ai_companies.csv"
        fd = _parse_date(r.get("Founding date", ""))
        if fd:
            triples.append(_T(name, "FOUNDED_IN", str(fd.year), "attr", src))
        ctype = (r.get("Company type") or "").strip()
        if ctype:
            triples.append(_T(name, "COMPANY_TYPE", ctype, "attr", src))
        for dom in (r.get("Product Domain(s)") or "").split(","):
            dom = dom.strip()
            if dom:
                # Domain là thực thể chia sẻ giữa nhiều công ty -> cạnh (bridge multi-hop)
                triples.append(_T(name, "WORKS_ON", dom, "edge", src))

    # --- revenue: lấy doanh thu mới nhất / công ty ---
    rev = _rows("ai_companies_revenue_reports.csv")
    for name in company_names:
        rec = _latest(rev, "Date", "Annualized revenue (USD)", filt=lambda r, n=name: r["Company"].strip() == n)
        if rec:
            m = _fmt_money(rec["Annualized revenue (USD)"])
            if m:
                triples.append(_T(name, "ANNUAL_REVENUE", m, "attr", "ai_companies_revenue_reports.csv"))

    # --- staff: tổng nhân sự mới nhất + các division ---
    staff = _rows("ai_companies_staff_reports.csv")
    for name in company_names:
        comp_rows = [r for r in staff if r["Company"].strip() == name]
        rec = _latest(comp_rows, "Date", "Staff count")
        if rec:
            triples.append(_T(name, "STAFF_COUNT", rec["Staff count"].strip(), "attr", "ai_companies_staff_reports.csv"))
        for div in sorted({(r.get("Division name") or "").strip() for r in comp_rows}):
            if div and div.lower() != name.lower():
                triples.append(_T(name, "HAS_DIVISION", div, "edge", "ai_companies_staff_reports.csv"))

    # --- valuation: post-money mới nhất từ funding rounds ---
    fund = _rows("ai_companies_funding_rounds.csv")
    for name in company_names:
        rec = _latest(
            fund, "Close date", "Valuation (post-money)",
            filt=lambda r, n=name: r["Company"].strip() == n and (r.get("Status") or "").strip() == "Closed",
        )
        if rec:
            m = _fmt_money(rec["Valuation (post-money)"])
            if m:
                triples.append(_T(name, "VALUATION", m, "attr", "ai_companies_funding_rounds.csv"))

    # --- compute spend: tổng mới nhất / công ty ---
    comp = _rows("ai_companies_compute_spend.csv")
    for name in company_names:
        rec = _latest(comp, "Date", "Total compute spend", filt=lambda r, n=name: r["Company"].strip() == n)
        if rec:
            m = _fmt_money(rec["Total compute spend"])
            if m:
                triples.append(_T(name, "COMPUTE_SPEND", m, "attr", "ai_companies_compute_spend.csv"))

    # --- products: từ usage_reports ---
    usage = _rows("ai_companies_usage_reports.csv")
    seen = set()
    for r in usage:
        name = r["Company"].strip()
        prod = (r.get("Product") or "").strip()
        if name and prod and (name, prod) not in seen:
            seen.add((name, prod))
            triples.append(_T(name, "HAS_PRODUCT", prod, "edge", "ai_companies_usage_reports.csv"))

    return triples, company_names


# ----------------------------- (B) LLM trên văn xuôi -----------------------------
EXTRACT_SYS = (
    "You are a precise financial-relation extraction engine. "
    "Given text about a fundraising round for a target company, identify the INVESTORS "
    "(funds, companies, or individuals) that provided capital to the target company. "
    "Return ONLY a compact JSON object: {\"investors\": [\"Name1\", \"Name2\"]}. "
    "Use canonical org names (e.g. 'Nvidia', 'Microsoft', 'a16z'). "
    "Do NOT include the target company itself, round names, dates, dollar amounts, or news outlets. "
    "If no investor is identifiable, return {\"investors\": []}."
)


def _parse_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    a, b = text.find("{"), text.rfind("}")
    if a != -1 and b != -1:
        text = text[a : b + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def extract_investors_llm(llm: LLM):
    """LLM đọc cột text của các vòng gọi vốn ĐÃ ĐÓNG -> cạnh INVESTED_IN (investor->company)."""
    fund = _rows("ai_companies_funding_rounds.csv")
    triples = []
    for r in fund:
        if (r.get("Status") or "").strip() != "Closed":
            continue  # chỉ lấy vòng đã đóng = đầu tư có thật
        company = r["Company"].strip()
        text = " | ".join(
            x for x in [r.get("Id", ""), r.get("Graph note", ""), (r.get("Notes", "") or "")[:600]] if x
        ).strip()
        if not text:
            continue
        user = f"Target company: {company}\nRound text: {text}\n\nExtract investors that funded {company}."
        out = _parse_json(llm.chat(EXTRACT_SYS, user, stage="extract_investors", max_tokens=300))
        for inv in out.get("investors", []) or []:
            inv = str(inv).strip()
            if inv and inv.lower() != company.lower():
                triples.append(_T(inv, "INVESTED_IN", company, "edge", f"funding_rounds:{r.get('Id','').strip()}"))
    return triples


# ----------------------------- orchestrator -----------------------------
def build_triples(use_llm=True, use_cache=True):
    tracker = UsageTracker()
    structured, companies = extract_structured()
    investor_triples = []
    if use_llm:
        llm = LLM(tracker=tracker, use_cache=use_cache)
        investor_triples = extract_investors_llm(llm)

    triples = structured + investor_triples
    payload = {
        "companies": companies,
        "triples": triples,
        "counts": {
            "structured": len(structured),
            "llm_investor": len(investor_triples),
            "total": len(triples),
        },
        "usage": tracker.to_dict(),
    }
    with open(config.TRIPLES_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tracker.save()
    return payload


if __name__ == "__main__":
    import sys

    use_llm = "--no-llm" not in sys.argv
    p = build_triples(use_llm=use_llm)
    print("Companies:", len(p["companies"]))
    print("Triples  :", p["counts"])
    print("Usage    :", json.dumps(p["usage"], indent=2))
    print("Saved ->", config.TRIPLES_PATH)
