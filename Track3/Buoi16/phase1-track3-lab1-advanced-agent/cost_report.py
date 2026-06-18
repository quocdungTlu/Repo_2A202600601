"""Dựng bảng so sánh benchmark + bảng tính chi phí (cost) từ kết quả đã chạy.

Đọc react_runs.jsonl & reflexion_runs.jsonl trong out-dir, in bảng Markdown và
lưu BENCHMARK.md. Giá mặc định theo gpt-4.1-nano ($/1M token).

    python cost_report.py --runs-dir outputs/hotpot_llm
    python cost_report.py --runs-dir outputs/hotpot_llm --price-in 0.10 --price-out 0.40 --project 1000
"""
from __future__ import annotations
import json
from pathlib import Path
from statistics import mean

import typer

app = typer.Typer(add_completion=False)


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _agg(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {}
    pt = sum(r.get("prompt_tokens", 0) for r in rows)
    ct = sum(r.get("completion_tokens", 0) for r in rows)
    tt = sum(r.get("token_estimate", 0) for r in rows)
    return {
        "n": n,
        "em": mean(1.0 if r["is_correct"] else 0.0 for r in rows),
        "avg_attempts": mean(r["attempts"] for r in rows),
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": tt,
        "avg_tokens": tt / n,
        "avg_latency_ms": mean(r["latency_ms"] for r in rows),
    }


def _cost(a: dict, price_in: float, price_out: float) -> float:
    return a["prompt_tokens"] / 1e6 * price_in + a["completion_tokens"] / 1e6 * price_out


@app.command()
def main(
    runs_dir: str = "outputs/hotpot_llm",
    price_in: float = 0.10,   # $/1M input tokens (gpt-4.1-nano)
    price_out: float = 0.40,  # $/1M output tokens
    model: str = "gpt-4.1-nano",
    project: int = 1000,      # ước phóng chi phí lên N câu hỏi
) -> None:
    d = Path(runs_dir)
    react = _agg(_load(d / "react_runs.jsonl"))
    reflexion = _agg(_load(d / "reflexion_runs.jsonl"))
    if not react or not reflexion:
        raise typer.BadParameter(f"Không tìm thấy runs trong {runs_dir} (cần react_runs.jsonl & reflexion_runs.jsonl)")

    c_react = _cost(react, price_in, price_out)
    c_refl = _cost(reflexion, price_in, price_out)
    n = react["n"]

    lines: list[str] = []
    lines.append(f"# Lab 16 — Benchmark & Cost ({model})\n")
    lines.append(f"Dữ liệu: {n} câu hỏi · giá `{model}` = ${price_in}/1M in, ${price_out}/1M out\n")

    # --- Bảng benchmark ---
    lines.append("## So sánh ReAct vs Reflexion\n")
    lines.append("| Metric | ReAct | Reflexion | Delta |")
    lines.append("|---|---:|---:|---:|")
    def row(name, k, fmt="{:.3f}"):
        rv, fv = react[k], reflexion[k]
        return f"| {name} | {fmt.format(rv)} | {fmt.format(fv)} | {fmt.format(fv - rv)} |"
    lines.append(row("Exact Match (EM)", "em"))
    lines.append(row("Avg attempts", "avg_attempts", "{:.2f}"))
    lines.append(row("Avg tokens/câu", "avg_tokens", "{:.0f}"))
    lines.append(row("Avg latency (ms)", "avg_latency_ms", "{:.0f}"))
    lines.append(f"| Tổng prompt tokens | {react['prompt_tokens']:,} | {reflexion['prompt_tokens']:,} | {reflexion['prompt_tokens']-react['prompt_tokens']:,} |")
    lines.append(f"| Tổng completion tokens | {react['completion_tokens']:,} | {reflexion['completion_tokens']:,} | {reflexion['completion_tokens']-react['completion_tokens']:,} |")
    lines.append("")

    # --- Bảng cost ---
    lines.append("## Bảng tính chi phí (cost)\n")
    lines.append(f"| | ReAct | Reflexion |")
    lines.append("|---|---:|---:|")
    lines.append(f"| Input tokens | {react['prompt_tokens']:,} | {reflexion['prompt_tokens']:,} |")
    lines.append(f"| Output tokens | {react['completion_tokens']:,} | {reflexion['completion_tokens']:,} |")
    lines.append(f"| Cost input ($) | {react['prompt_tokens']/1e6*price_in:.5f} | {reflexion['prompt_tokens']/1e6*price_in:.5f} |")
    lines.append(f"| Cost output ($) | {react['completion_tokens']/1e6*price_out:.5f} | {reflexion['completion_tokens']/1e6*price_out:.5f} |")
    lines.append(f"| **Tổng cost ({n} câu)** | **${c_react:.5f}** | **${c_refl:.5f}** |")
    lines.append(f"| Cost / câu | ${c_react/n:.6f} | ${c_refl/n:.6f} |")
    lines.append(f"| Cost / câu đúng | ${c_react/max(react['em']*n,1e-9):.6f} | ${c_refl/max(reflexion['em']*n,1e-9):.6f} |")
    lines.append(f"| Ước phóng {project:,} câu | ${c_react/n*project:.2f} | ${c_refl/n*project:.2f} |")
    lines.append("")

    # --- Kết luận ---
    em_gain = reflexion["em"] - react["em"]
    extra_cost = c_refl - c_react
    lines.append("## Nhận xét\n")
    lines.append(
        f"- Reflexion tăng EM **{em_gain:+.1%}** (từ {react['em']:.1%} lên {reflexion['em']:.1%}) "
        f"nhưng tốn thêm **${extra_cost:.5f}** ({(c_refl/c_react-1)*100:.0f}% chi phí) trên {n} câu."
    )
    if em_gain > 0:
        lines.append(f"- Chi phí cho mỗi điểm EM tăng thêm: ~${extra_cost/(em_gain*n):.6f} / câu được sửa đúng.")
    lines.append(
        f"- Output tokens rất nhỏ so với input (câu trả lời ngắn) → chi phí chủ yếu do **input/context**; "
        f"giảm context thừa là cách rẻ hoá hiệu quả nhất."
    )

    md = "\n".join(lines)
    out = Path(runs_dir) / "BENCHMARK.md"
    out.write_text(md, encoding="utf-8")
    # cũng lưu bản chính ở repo root để dễ xem/nộp
    Path("BENCHMARK.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[saved] {out} & BENCHMARK.md")


if __name__ == "__main__":
    app()
