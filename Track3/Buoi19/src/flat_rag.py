"""Flat RAG baseline — ChromaDB + sentence-transformers embedding.

Pipeline (dataset văn bản thô EV):
  1. Đọc 70 file .txt, làm sạch boilerplate, chunk thành đoạn ~800 từ.
  2. Embed bằng all-MiniLM-L6-v2 (chạy offline, không tốn token LLM).
  3. Query: embed câu hỏi -> top-k cosine -> ghép context -> LLM trả lời.
"""

import os
import glob
import re

import chromadb
from chromadb.utils import embedding_functions

import config
from llm import LLM, UsageTracker
from extract_text import parse_doc

COLLECTION = "lab19_flat_rag_ev"
DB_DIR = os.path.join(config.ROOT_DIR, ".chroma_flat")

CHUNK_WORDS = 250       # số từ mỗi chunk
CHUNK_OVERLAP = 40      # số từ overlap giữa các chunk


def _chunk(text: str, size=CHUNK_WORDS, overlap=CHUNK_OVERLAP):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + size]))
        i += size - overlap
    return chunks


# ----------------------------- document builder -----------------------------
def _build_docs() -> list[dict]:
    """Đọc 70 file .txt, chunk mỗi doc thành nhiều đoạn embed."""
    docs = []
    paths = sorted(
        glob.glob(os.path.join(config.DATASET_DIR, "*.txt")),
        key=lambda p: int(re.search(r"(\d+)", os.path.basename(p)).group(1)),
    )
    for path in paths:
        doc_id = os.path.basename(path)
        parsed = parse_doc(path)
        # ghép title + snippet + content để chunk có ngữ cảnh
        header = f"{parsed['title']}. {parsed['snippet']} ".strip()
        full = (header + " " + parsed["content"]).strip()
        for j, ch in enumerate(_chunk(full)):
            if ch.strip():
                docs.append({
                    "text": ch,
                    "meta": {"source": doc_id, "chunk": j, "title": parsed["title"][:120]},
                })
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
            "You are a precise analyst of the US electric vehicle (EV) industry. "
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
    print(f"Indexed {n} chunks.")
    q = "Which companies does Tesla compete with?"
    r = rag.query(q)
    print("Q:", q)
    print("A:", r["answer"])
