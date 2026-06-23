"""Bước 2 — Construction: Dựng Knowledge Graph bằng NetworkX (domain-agnostic).

- Load triples từ outputs/triples.json (extract.py hoặc extract_text.py).
- Dedup thực thể GENERIC: chuẩn hóa (bỏ hậu tố công ty, gộp hoa/thường, gom biến thể)
  -> chọn canonical = surface form xuất hiện nhiều nhất.
- Mỗi triple kind="edge" thành cạnh; kind="attr" gắn vào node data.
- Lưu graph (pickle) + vẽ PNG bằng Matplotlib (Deliverable #2).
"""

import json
import re
import pickle
import unicodedata
from collections import Counter, defaultdict

import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

import config

# Hậu tố pháp nhân thường gặp -> loại khi so khớp dedup
_CORP_SUFFIXES = [
    "incorporated", "inc", "corporation", "corp", "company", "co",
    "ltd", "limited", "llc", "lp", "plc", "group", "holdings",
    "motors", "automotive", "ag", "sa", "nv",
]
_SUFFIX_RE = re.compile(
    r"[,\.]?\s+(" + "|".join(_CORP_SUFFIXES) + r")\.?$", re.IGNORECASE
)


def _norm_key(name: str) -> str:
    """Khóa chuẩn hóa để gom các biến thể của cùng một thực thể."""
    s = unicodedata.normalize("NFKC", name).strip()
    s = re.sub(r"\s+", " ", s)
    prev = None
    while prev != s:                       # lột nhiều hậu tố: "Tesla Motors Inc" -> "Tesla"
        prev = s
        s = _SUFFIX_RE.sub("", s).strip()
    s = s.lower()
    s = re.sub(r"[^\w\s]", "", s)           # bỏ dấu câu
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Bản đồ canonical toàn cục, dựng trong build_graph
_CANON_MAP: dict[str, str] = {}


def canonicalize(name: str) -> str:
    """Trả về canonical form của một entity (sau khi _CANON_MAP đã dựng)."""
    if not name:
        return name
    key = _norm_key(name)
    return _CANON_MAP.get(key, name.strip())


def _build_canonical_map(entities) -> dict[str, str]:
    """Với mỗi norm_key, chọn surface form phổ biến nhất (tie -> ngắn nhất) làm canonical."""
    groups: dict[str, Counter] = defaultdict(Counter)
    for e in entities:
        e = (e or "").strip()
        if not e:
            continue
        groups[_norm_key(e)][e] += 1
    canon = {}
    for key, counter in groups.items():
        if not key:
            continue
        # ưu tiên xuất hiện nhiều, rồi tên ngắn gọn
        best = sorted(counter.items(), key=lambda kv: (-kv[1], len(kv[0])))[0][0]
        canon[key] = best
    return canon


# ----------------------------- build graph -----------------------------
def build_graph(triples_path: str | None = None) -> nx.DiGraph:
    global _CANON_MAP
    path = triples_path or config.TRIPLES_PATH
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    triples = data["triples"]

    # Pass 0: gom toàn bộ entity (subject + object của edge) -> canonical map
    ent_surface = []
    for t in triples:
        ent_surface.append(t["subject"])
        if t.get("kind", "edge") == "edge":
            ent_surface.append(t["object"])
    _CANON_MAP = _build_canonical_map(ent_surface)

    G = nx.DiGraph()

    # Pass 1: attr -> node data
    for t in triples:
        if t.get("kind") == "attr":
            subj = canonicalize(t["subject"])
            G.add_node(subj)
            G.nodes[subj][t["relation"]] = t["object"]

    # Pass 2: edge
    for t in triples:
        if t.get("kind", "edge") != "edge":
            continue
        s = canonicalize(t["subject"])
        o = canonicalize(t["object"])
        if not s or not o or s == o:
            continue
        if G.has_edge(s, o):
            # gộp nhãn quan hệ nếu khác nhau
            rels = G[s][o].setdefault("rels", set())
            rels.add(t["relation"])
            continue
        G.add_edge(s, o, rel=t["relation"], rels={t["relation"]},
                   source=t.get("source", ""))

    return G


# ----------------------------- visualization -----------------------------
def _degree_palette(G, node, dmax):
    d = G.degree(node)
    if d >= max(5, dmax * 0.5):
        return "#DD8452"   # cam — hub bậc cao
    if d >= 3:
        return "#4C72B0"   # xanh dương — node trung bình
    return "#A6A6A6"       # xám — node biên


def draw_graph(G: nx.DiGraph, out_path: str | None = None, top_n: int = 60) -> str:
    """Vẽ subgraph gồm top_n node bậc cao nhất (tránh rối với đồ thị lớn)."""
    out_path = out_path or config.GRAPH_IMG_PATH

    top_nodes = [n for n, _ in sorted(G.degree, key=lambda x: -x[1])[:top_n]]
    H = G.subgraph(top_nodes).copy()
    # bỏ node cô lập sau khi cắt
    H.remove_nodes_from([n for n in list(H.nodes()) if H.degree(n) == 0])

    dmax = max((d for _, d in G.degree), default=1)

    fig, ax = plt.subplots(figsize=(24, 18))
    ax.set_facecolor("#F8F9FA")
    fig.patch.set_facecolor("#F8F9FA")

    pos = nx.spring_layout(H, seed=42, k=1.8, iterations=80)
    colors = [_degree_palette(G, n, dmax) for n in H.nodes()]
    sizes = [300 + 120 * G.degree(n) for n in H.nodes()]

    nx.draw_networkx_nodes(H, pos, node_color=colors, node_size=sizes, alpha=0.9, ax=ax)
    nx.draw_networkx_edges(H, pos, edge_color="#BBBBBB", width=0.8, arrows=True,
                           arrowsize=10, connectionstyle="arc3,rad=0.08", ax=ax)
    nx.draw_networkx_labels(H, pos, font_size=7, font_weight="bold", ax=ax)

    # nhãn cạnh cho các cạnh giữa node bậc cao
    hub = {n for n in H.nodes() if G.degree(n) >= 4}
    edge_labels = {
        (u, v): d.get("rel", "")
        for u, v, d in H.edges(data=True)
        if u in hub or v in hub
    }
    nx.draw_networkx_edge_labels(H, pos, edge_labels, font_size=5,
                                 font_color="#555555", ax=ax)

    legend_items = [
        mpatches.Patch(color="#DD8452", label="Hub (degree cao — thực thể trung tâm)"),
        mpatches.Patch(color="#4C72B0", label="Node trung bình (degree 3-4)"),
        mpatches.Patch(color="#A6A6A6", label="Node biên (degree 1-2)"),
    ]
    ax.legend(handles=legend_items, loc="upper left", fontsize=11,
              framealpha=0.9, fancybox=True)
    ax.set_title(
        f"Knowledge Graph — EV Industry Corpus (top {H.number_of_nodes()} nodes by degree)\n"
        f"Lab Day 19 — full graph: {G.number_of_nodes()} nodes / {G.number_of_edges()} edges",
        fontsize=15, pad=20,
    )
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close()
    return out_path


# ----------------------------- persistence -----------------------------
def save_graph(G: nx.DiGraph, path: str | None = None):
    path = path or config.GRAPH_PATH
    # set không pickle gọn -> đổi 'rels' thành list khi lưu
    H = G.copy()
    for _, _, d in H.edges(data=True):
        if isinstance(d.get("rels"), set):
            d["rels"] = sorted(d["rels"])
    with open(path, "wb") as f:
        pickle.dump(H, f)


def load_graph(path: str | None = None) -> nx.DiGraph:
    path = path or config.GRAPH_PATH
    with open(path, "rb") as f:
        return pickle.load(f)


# ----------------------------- helpers cho GraphRAG -----------------------------
def hub_nodes(G: nx.DiGraph, top_n: int = 15) -> list[str]:
    """Các node bậc cao nhất — dùng làm seed fallback khi không match được entity."""
    return [n for n, _ in sorted(G.degree, key=lambda x: -x[1])[:top_n]]


# ----------------------------- stats -----------------------------
def print_stats(G: nx.DiGraph):
    print(f"Nodes : {G.number_of_nodes()}")
    print(f"Edges : {G.number_of_edges()}")
    rel_counts: dict[str, int] = {}
    for _, _, d in G.edges(data=True):
        rel_counts[d.get("rel", "?")] = rel_counts.get(d.get("rel", "?"), 0) + 1
    print("Top relations:")
    for rel, cnt in sorted(rel_counts.items(), key=lambda x: -x[1])[:12]:
        print(f"  {rel:<20} {cnt:3d}")
    print("Top hub entities:")
    for n, d in sorted(G.degree, key=lambda x: -x[1])[:12]:
        print(f"  {n:<35} degree={d}")


if __name__ == "__main__":
    G = build_graph()
    print_stats(G)
    save_graph(G)
    img = draw_graph(G)
    print(f"\nGraph PNG saved -> {img}")
    print(f"Graph pickle   -> {config.GRAPH_PATH}")
