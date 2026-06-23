"""GraphRAG query engine — duyệt 2-hop trên NetworkX knowledge graph.

Pipeline:
  1. Trích thực thể từ câu hỏi (entity linking đơn giản: fuzzy match tên node).
  2. ego_graph(G, entity, radius=GRAPH_HOPS) -> lấy tất cả node + cạnh trong 2-hop.
  3. Textualize subgraph thành đoạn văn ngắn (ngữ cảnh cấu trúc).
  4. Đưa ngữ cảnh đó cho LLM trả lời.
"""

import json
import re

import networkx as nx

import config
from graph_build import load_graph, canonicalize, hub_nodes
from llm import LLM, UsageTracker

# ----------------------------- entity linking -----------------------------
def _best_match(query_text: str, G: nx.DiGraph) -> list[str]:
    """Trả về danh sách node khớp tốt nhất với query (không phân biệt hoa thường)."""
    q_lower = query_text.lower()
    nodes = list(G.nodes())
    hits = []
    # ưu tiên match chính xác canonical name
    for n in nodes:
        if canonicalize(n).lower() in q_lower or n.lower() in q_lower:
            hits.append(n)
    if hits:
        return hits
    # fallback: bất kỳ token nào trong tên node xuất hiện trong câu hỏi
    for n in nodes:
        for token in re.split(r"\W+", n.lower()):
            if len(token) >= 4 and token in q_lower:
                hits.append(n)
                break
    return list(dict.fromkeys(hits))  # dedup giữ thứ tự


# ----------------------------- context builder (Textualization) -----------------------------
def _node_summary(G: nx.DiGraph, node: str) -> str:
    """Mô tả ngắn về một node dựa trên thuộc tính và cạnh."""
    attrs = G.nodes[node]
    parts = [f"[{node}]"]
    for k, v in attrs.items():
        parts.append(f"{k}: {v}")
    return " | ".join(parts)


MAX_CONTEXT_EDGES = 120  # trần số cạnh đưa vào context (đồ thị lớn → tránh nổ token)


def _textualize_subgraph(G: nx.DiGraph, seed_nodes: list[str]) -> str:
    """Duyệt ego_graph radius=GRAPH_HOPS quanh seed_nodes, chuyển thành text.

    Với đồ thị lớn, ego 2-hop từ một hub có thể gồm hàng trăm node. Ta ưu tiên các
    cạnh gần seed (theo khoảng cách BFS) và cắt còn MAX_CONTEXT_EDGES cạnh.
    """
    subgraph_nodes = set(seed_nodes)
    # khoảng cách ngắn nhất tới seed gần nhất (để xếp ưu tiên)
    dist: dict = {}
    for seed in seed_nodes:
        if seed in G:
            ego = nx.ego_graph(G, seed, radius=config.GRAPH_HOPS, undirected=True)
            subgraph_nodes.update(ego.nodes())
            lengths = nx.single_source_shortest_path_length(
                G.to_undirected(as_view=True), seed, cutoff=config.GRAPH_HOPS
            )
            for n, d in lengths.items():
                dist[n] = min(dist.get(n, 99), d)

    if not subgraph_nodes:
        return ""

    H = G.subgraph(subgraph_nodes)

    # xếp cạnh theo độ gần seed rồi cắt
    edges = list(H.edges(data=True))
    edges.sort(key=lambda e: dist.get(e[0], 99) + dist.get(e[1], 99))
    edges = edges[:MAX_CONTEXT_EDGES]

    lines = []
    # Thuộc tính node của seed (nếu có)
    for n in seed_nodes:
        if n in H and H.nodes[n]:
            lines.append(_node_summary(H, n))
    if lines:
        lines.append("")
    # Quan hệ (cạnh) — đã xếp ưu tiên
    for u, v, d in edges:
        rel = d.get("rel", "RELATED_TO")
        lines.append(f"{u} --[{rel}]--> {v}")

    return "\n".join(lines)


# ----------------------------- GraphRAG query -----------------------------
SYSTEM_PROMPT = (
    "You are a precise analyst of the US electric vehicle (EV) industry with access to a "
    "structured knowledge graph. "
    "The context below contains relationship triples (entity --[RELATION]--> entity) extracted "
    "from a corpus of EV-industry documents. Answer the question using ONLY this context. "
    "Trace multi-hop connections explicitly when needed. "
    "If the context does not contain enough information, say 'I don't know based on the graph data.' "
    "Be concise (1-4 sentences)."
)


class GraphRAG:
    def __init__(self, tracker: UsageTracker | None = None, G: nx.DiGraph | None = None):
        self.tracker = tracker or UsageTracker()
        self.G = G or load_graph()
        self._llm = LLM(tracker=self.tracker)

    def query(self, question: str) -> dict:
        seed_nodes = _best_match(question, self.G)

        # fallback: nếu không match được node nào, lấy các hub bậc cao nhất
        if not seed_nodes:
            seed_nodes = hub_nodes(self.G, top_n=10)

        context = _textualize_subgraph(self.G, seed_nodes)
        user = f"Knowledge graph context:\n{context}\n\nQuestion: {question}"
        answer = self._llm.chat(SYSTEM_PROMPT, user, stage="graph_rag_answer", max_tokens=500)

        return {
            "answer": answer,
            "seed_nodes": seed_nodes,
            "context_length": len(context),
            "method": "graph_rag",
        }


if __name__ == "__main__":
    rag = GraphRAG()
    q = "Who invested in both OpenAI and Anthropic?"
    r = rag.query(q)
    print(f"Q: {q}")
    print(f"Seed nodes: {r['seed_nodes']}")
    print(f"A: {r['answer']}")
