"""Bước 2 — Construction: Dựng Knowledge Graph bằng NetworkX.

- Load triples từ outputs/triples.json (kết quả extract.py).
- Normalize/dedup thực thể: lowercase + trim -> canonical form.
- Chỉ đưa triple kind="edge" vào đồ thị; kind="attr" gắn vào node data.
- Lưu graph dưới dạng pickle + vẽ PNG bằng Matplotlib (Deliverable #2).
"""

import json
import re
import pickle
import os
import unicodedata

import networkx as nx
import matplotlib
matplotlib.use("Agg")   # không cần GUI khi chạy script
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

import config


# ----------------------------- dedup / normalization -----------------------------
# Alias map: các tên thường gặp khác nhau của cùng một thực thể
ALIAS_MAP = {
    "openai":           "OpenAI",
    "open ai":          "OpenAI",
    "openai inc":       "OpenAI",
    "anthropic":        "Anthropic",
    "anthropic inc":    "Anthropic",
    "google":           "Google",
    "google deepmind":  "Google",
    "deepmind":         "Google",
    "meta":             "Meta",
    "meta ai":          "Meta",
    "microsoft":        "Microsoft",
    "amazon":           "Amazon",
    "amazon aws":       "Amazon",
    "nvidia":           "Nvidia",
    "nvidia corporation": "Nvidia",
    "nvidia corp":      "Nvidia",
    "nvidea":           "Nvidia",
    "softbank":         "SoftBank",
    "softbank group":   "SoftBank",
    "xai":              "xAI",
    "x.ai":             "xAI",
    "mistral":          "Mistral AI",
    "mistral ai":       "Mistral AI",
    "deepseek":         "DeepSeek",
    "minimax":          "MiniMax",
    "z.ai":             "Z.ai",
    "khosla ventures":  "Khosla Ventures",
    "khosla":           "Khosla Ventures",
    "sequoia":          "Sequoia Capital",
    "sequoia capital":  "Sequoia Capital",
    "a16z":             "a16z",
    "andreessen horowitz": "a16z",
    "fidelity":         "Fidelity",
    "fidelity management": "Fidelity",
    "mgx":              "MGX",
    "t. rowe price":    "T. Rowe Price",
    "t rowe price":     "T. Rowe Price",
    "rowe":             "T. Rowe Price",
    "d1 capital":       "D1 Capital",
    "d1 capital partners": "D1 Capital",
    "tiger global":     "Tiger Global",
    "general catalyst": "General Catalyst",
    "lightspeed":       "Lightspeed",
    "coatue":           "Coatue",
    "dragoneer":        "Dragoneer",
    "spark capital":    "Spark Capital",
    "chatgpt":          "ChatGPT",
    "language":         "Language",
    "video":            "Video",
}


def canonicalize(name: str) -> str:
    name = name.strip()
    key = unicodedata.normalize("NFKC", name).lower()
    key = re.sub(r"\s+", " ", key)
    return ALIAS_MAP.get(key, name)


# ----------------------------- build graph -----------------------------
# Nhóm màu cho từng loại node
COMPANY_NAMES = {"OpenAI","Anthropic","Google","Mistral AI","xAI","DeepSeek","Meta","Z.ai","MiniMax"}
INVESTOR_RELS = {"INVESTED_IN"}
DOMAIN_RELS   = {"WORKS_ON"}
PRODUCT_RELS  = {"HAS_PRODUCT", "HAS_DIVISION"}

def _node_color(G, node):
    if node in COMPANY_NAMES:
        return "#4C72B0"          # xanh dương — AI companies
    for _, _, d in G.in_edges(node, data=True):
        if d.get("rel") in INVESTOR_RELS:
            return "#DD8452"      # cam — investors (có cạnh đầu tư ra ngoài)
    for _, _, d in G.out_edges(node, data=True):
        if d.get("rel") in INVESTOR_RELS:
            return "#DD8452"
        if d.get("rel") in DOMAIN_RELS:
            return "#55A868"      # xanh lá — domains
        if d.get("rel") in PRODUCT_RELS:
            return "#C44E52"      # đỏ — products/divisions
    return "#8172B2"              # tím — khác


def build_graph(triples_path: str | None = None) -> nx.DiGraph:
    path = triples_path or config.TRIPLES_PATH
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    G = nx.DiGraph()

    # Gắn attr vào node trước (pass 1)
    for t in data["triples"]:
        if t["kind"] == "attr":
            subj = canonicalize(t["subject"])
            G.add_node(subj)
            G.nodes[subj][t["relation"]] = t["object"]

    # Thêm edge (pass 2) — chỉ kind="edge"
    for t in data["triples"]:
        if t["kind"] == "edge":
            s = canonicalize(t["subject"])
            o = canonicalize(t["object"])
            if s == o:
                continue
            if G.has_edge(s, o):
                # nếu cạnh đã tồn tại thì giữ cạnh đầu, bỏ trùng
                continue
            G.add_edge(s, o, rel=t["relation"], source=t.get("source", ""))

    return G


# ----------------------------- visualization -----------------------------
def draw_graph(G: nx.DiGraph, out_path: str | None = None) -> str:
    out_path = out_path or config.GRAPH_IMG_PATH

    # Tách subgraph để không vẽ quá rậm: chỉ lấy node có ít nhất 1 cạnh
    nodes_with_edges = [n for n in G.nodes() if G.degree(n) > 0]
    H = G.subgraph(nodes_with_edges).copy()

    fig, ax = plt.subplots(figsize=(22, 16))
    ax.set_facecolor("#F8F9FA")
    fig.patch.set_facecolor("#F8F9FA")

    pos = nx.spring_layout(H, seed=42, k=2.2)

    colors = [_node_color(G, n) for n in H.nodes()]
    sizes  = [1800 if n in COMPANY_NAMES else 900 for n in H.nodes()]

    nx.draw_networkx_nodes(H, pos, node_color=colors, node_size=sizes, alpha=0.92, ax=ax)
    nx.draw_networkx_labels(H, pos, font_size=7, font_weight="bold", ax=ax)

    # Vẽ edge theo loại quan hệ
    rel_styles = {
        "INVESTED_IN":  ("#DD8452", "-",  2.0),
        "HAS_PRODUCT":  ("#C44E52", "--", 1.5),
        "WORKS_ON":     ("#55A868", ":",  1.5),
        "HAS_DIVISION": ("#8172B2", "--", 1.2),
    }
    default_style = ("#999999", "-", 0.8)
    for rel, (color, style, width) in rel_styles.items():
        edges = [(u, v) for u, v, d in H.edges(data=True) if d.get("rel") == rel]
        if edges:
            nx.draw_networkx_edges(H, pos, edgelist=edges, edge_color=color,
                                   style=style, width=width, arrows=True,
                                   arrowsize=18, connectionstyle="arc3,rad=0.1", ax=ax)
    other_edges = [(u, v) for u, v, d in H.edges(data=True) if d.get("rel") not in rel_styles]
    if other_edges:
        nx.draw_networkx_edges(H, pos, edgelist=other_edges,
                               edge_color=default_style[0], width=default_style[2],
                               arrows=True, arrowsize=12,
                               connectionstyle="arc3,rad=0.1", ax=ax)

    # Nhãn cạnh (chỉ cho INVESTED_IN để không bị rối)
    invest_labels = {(u, v): "INVESTED_IN" for u, v, d in H.edges(data=True) if d.get("rel") == "INVESTED_IN"}
    nx.draw_networkx_edge_labels(H, pos, invest_labels, font_size=5.5,
                                 font_color="#DD8452", ax=ax)

    # Legend
    legend_items = [
        mpatches.Patch(color="#4C72B0", label="AI Company"),
        mpatches.Patch(color="#DD8452", label="Investor (→ INVESTED_IN)"),
        mpatches.Patch(color="#55A868", label="Domain (WORKS_ON)"),
        mpatches.Patch(color="#C44E52", label="Product (HAS_PRODUCT)"),
        mpatches.Patch(color="#8172B2", label="Division / Other"),
    ]
    ax.legend(handles=legend_items, loc="upper left", fontsize=9,
              framealpha=0.9, fancybox=True)

    ax.set_title("Knowledge Graph — AI Companies Corpus (Lab Day 19)", fontsize=14, pad=20)
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    return out_path


# ----------------------------- persistence -----------------------------
def save_graph(G: nx.DiGraph, path: str | None = None):
    path = path or config.GRAPH_PATH
    with open(path, "wb") as f:
        pickle.dump(G, f)


def load_graph(path: str | None = None) -> nx.DiGraph:
    path = path or config.GRAPH_PATH
    with open(path, "rb") as f:
        return pickle.load(f)


# ----------------------------- stats -----------------------------
def print_stats(G: nx.DiGraph):
    print(f"Nodes : {G.number_of_nodes()}")
    print(f"Edges : {G.number_of_edges()}")
    rel_counts: dict[str, int] = {}
    for _, _, d in G.edges(data=True):
        rel_counts[d.get("rel", "?")] = rel_counts.get(d.get("rel", "?"), 0) + 1
    for rel, cnt in sorted(rel_counts.items(), key=lambda x: -x[1]):
        print(f"  {rel:<22} {cnt:3d}")


if __name__ == "__main__":
    G = build_graph()
    print_stats(G)
    save_graph(G)
    img = draw_graph(G)
    print(f"Graph PNG saved -> {img}")
    print(f"Graph pickle   -> {config.GRAPH_PATH}")
