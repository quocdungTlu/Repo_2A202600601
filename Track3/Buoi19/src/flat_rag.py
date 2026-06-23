"""Flat RAG baseline — ChromaDB + sentence-transformers embedding.

Pipeline:
  1. Textualize mỗi row CSV thành một "document" ngắn.
  2. Embed bằng all-MiniLM-L6-v2 (chạy offline, không tốn token LLM).
  3. Query: embed câu hỏi -> top-k cosine -> ghép context -> LLM trả lời.
"""

import os
import csv
import json

import chromadb
from chromadb.utils import embedding_functions

import config
from llm import LLM, UsageTracker

COLLECTION = "lab19_flat_rag"
DB_DIR = os.path.join(config.ROOT_DIR, ".chroma_flat")
csv.field_size_limit(10_000_000)


def _rows(fname):
    with open(os.path.join(config.DATA_DIR, fname), encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ----------------------------- document builder -----------------------------
def _build_docs() -> list[dict]:
    """Chuyển mỗi row CSV thành chuỗi text + metadata."""
    docs = []

    def add(text, meta):
        text = text.strip()
        if text:
            docs.append({"text": text, "meta": meta})

    for r in _rows("ai_companies.csv"):
        name = r.get("Name", "").strip()
        parts = [f"{name} is an AI company."]
        if r.get("Founding date"):
            parts.append(f"Founded: {r['Founding date'][:4]}.")
        if r.get("Company type"):
            parts.append(f"Type: {r['Company type']}.")
        if r.get("Product Domain(s)"):
            parts.append(f"Domains: {r['Product Domain(s)']}.")
        add(" ".join(parts), {"company": name, "source": "companies"})

    for r in _rows("ai_companies_funding_rounds.csv"):
        if (r.get("Status") or "").strip() != "Closed":
            continue
        comp = r.get("Company", "").strip()
        rid = r.get("Id", "").strip()
        eq = r.get("Funding (equity)", "").strip()
        val = r.get("Valuation (post-money)", "").strip()
        note = (r.get("Graph note") or r.get("Notes") or "")[:300].strip()
        parts = [f"{comp} received funding in round '{rid}'."]
        if eq:
            parts.append(f"Equity: ${float(eq)/1e6:.0f}M." if eq else "")
        if val:
            parts.append(f"Post-money valuation: ${float(val)/1e9:.1f}B.")
        if note:
            parts.append(note)
        add(" ".join(p for p in parts if p), {"company": comp, "source": "funding"})

    for r in _rows("ai_companies_revenue_reports.csv"):
        comp = r.get("Company", "").strip()
        rev = r.get("Annualized revenue (USD)", "").strip()
        date = r.get("Date", "").strip()
        if not rev:
            continue
        try:
            rev_str = f"${float(rev)/1e9:.1f}B"
        except ValueError:
            rev_str = rev
        add(f"{comp} had annualized revenue of {rev_str} as of {date}.",
            {"company": comp, "source": "revenue"})

    for r in _rows("ai_companies_staff_reports.csv"):
        comp = r.get("Company", "").strip()
        staff = r.get("Staff count", "").strip()
        date = r.get("Date", "").strip()
        div = r.get("Division name", "").strip()
        if not staff:
            continue
        scope = f" (division: {div})" if div else ""
        add(f"{comp}{scope} had {staff} staff as of {date}.",
            {"company": comp, "source": "staff"})

    for r in _rows("ai_companies_usage_reports.csv"):
        comp = r.get("Company", "").strip()
        prod = r.get("Product", "").strip()
        users = r.get("Active users", "").strip()
        period = r.get("Active users time period", "").strip()
        date = r.get("Date", "").strip()
        note = (r.get("Notes") or "")[:200].strip()
        if not users:
            continue
        try:
            u = float(users)
            u_str = f"{u/1e6:.0f}M {period}" if period else f"{u/1e6:.0f}M"
        except ValueError:
            u_str = users
        parts = [f"{comp}'s product {prod} had {u_str} active users as of {date}."]
        if note:
            parts.append(note[:100])
        add(" ".join(parts), {"company": comp, "source": "usage"})

    for r in _rows("ai_companies_compute_spend.csv"):
        comp = r.get("Company", "").strip()
        amt = r.get("Total compute spend", "").strip() or r.get("Amount", "").strip()
        date = r.get("Date", "").strip()
        cat = r.get("Category", "").strip()
        note = (r.get("Notes") or "")[:200].strip()
        if not amt:
            continue
        try:
            amt_str = f"${float(amt)/1e9:.1f}B"
        except ValueError:
            amt_str = amt
        parts = [f"{comp} spent {amt_str} on compute ({cat}) as of {date}."]
        if note:
            parts.append(note[:100])
        add(" ".join(parts), {"company": comp, "source": "compute"})

    return docs


# ----------------------------- indexing -----------------------------
class FlatRAG:
    def __init__(self, tracker: UsageTracker | None = None):
        self.tracker = tracker or UsageTracker()
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=config.EMBEDDING_MODEL
        )
        client = chromadb.PersistentClient(path=DB_DIR)
        self.col = client.get_or_create_collection(COLLECTION, embedding_function=ef)
        self._llm = LLM(tracker=self.tracker)

    def index(self, force=False):
        if not force and self.col.count() > 0:
            return self.col.count()
        docs = _build_docs()
        self.col.delete(where={"source": {"$ne": "__never__"}}) if self.col.count() > 0 else None
        ids, texts, metas = [], [], []
        for i, d in enumerate(docs):
            ids.append(f"doc_{i}")
            texts.append(d["text"])
            metas.append(d["meta"])
        self.col.add(ids=ids, documents=texts, metadatas=metas)
        return len(docs)

    def query(self, question: str) -> dict:
        results = self.col.query(
            query_texts=[question],
            n_results=config.FLAT_TOP_K,
        )
        chunks = results["documents"][0]
        context = "\n".join(f"- {c}" for c in chunks)
        system = (
            "You are a precise AI industry analyst. "
            "Answer the question using ONLY the provided context snippets. "
            "If the context does not contain enough information, say 'I don't know based on the given data.' "
            "Be concise (1-3 sentences)."
        )
        user = f"Context:\n{context}\n\nQuestion: {question}"
        answer = self._llm.chat(system, user, stage="flat_rag_answer", max_tokens=400)
        return {
            "answer": answer,
            "context_chunks": chunks,
            "method": "flat_rag",
        }


if __name__ == "__main__":
    rag = FlatRAG()
    n = rag.index()
    print(f"Indexed {n} documents.")
    r = rag.query("Who invested in both OpenAI and Anthropic?")
    print("Q: Who invested in both OpenAI and Anthropic?")
    print("A:", r["answer"])
