"""Chạy agent trên Golden Test Set NHANH NHẤT có thể và xuất sản phẩm để nộp.

Tối ưu cho 15 phút cuối buổi: 1 lệnh duy nhất, chạy SONG SONG, loader chịu lỗi.

    python submit_golden.py --dataset data/golden.json --out-dir outputs/golden --workers 10

Sản phẩm trong out-dir:
  - report.json / report.md   -> nộp & tự chấm (autograde.py)
  - predictions.json          -> [{qid, question, predicted_answer}] (agent Reflexion)
  - react_runs.jsonl / reflexion_runs.jsonl
"""
from __future__ import annotations
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich import print

load_dotenv()
from src.reflexion_lab import llm
from src.reflexion_lab.agents import run_pair
from src.reflexion_lab.reporting import build_report, save_report
from src.reflexion_lab.schemas import RunRecord
from src.reflexion_lab.utils import load_dataset_flexible, save_jsonl

app = typer.Typer(add_completion=False)


def _safe_pair(example, max_attempts: int):
    """Chạy 1 example; nếu lỗi bất ngờ -> trả record degraded (không sập cả run)."""
    try:
        return run_pair(example, max_attempts=max_attempts)
    except Exception as e:  # noqa: BLE001 - cố ý nuốt mọi lỗi để giữ run sống
        base = dict(qid=example.qid, question=example.question, gold_answer=example.gold_answer,
                    predicted_answer="", is_correct=False, token_estimate=0, latency_ms=0,
                    failure_mode="wrong_final_answer")
        print(f"[yellow]WARN[/yellow] {example.qid}: {type(e).__name__}: {str(e)[:80]}")
        return (RunRecord(agent_type="react", attempts=1, **base),
                RunRecord(agent_type="reflexion", attempts=1, **base))


@app.command()
def main(
    dataset: str = "data/golden.json",
    out_dir: str = "outputs/golden",
    reflexion_attempts: int = 3,
    workers: int = 10,
    limit: int = 0,
) -> None:
    examples = load_dataset_flexible(dataset)
    if limit > 0:
        examples = examples[:limit]
    mode = "llm" if llm.llm_enabled() else "mock"
    has_gold = sum(1 for e in examples if e.gold_answer.strip())
    print(f"[cyan]GOLDEN[/cyan] mode={mode.upper()} examples={len(examples)} "
          f"with_gold={has_gold} workers={workers}")

    # Một lượt Reflexion/example -> suy ra cả ReAct (tiết kiệm ~nửa số call ở attempt 1).
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        pairs = list(ex.map(lambda e: _safe_pair(e, reflexion_attempts), examples))
    react_records = [p[0] for p in pairs]
    reflexion_records = [p[1] for p in pairs]
    elapsed = time.time() - t0
    print(f"[green]Done[/green] in {elapsed:.1f}s ({elapsed / max(len(examples), 1):.2f}s/câu)")

    all_records = react_records + reflexion_records
    out_path = Path(out_dir)
    save_jsonl(out_path / "react_runs.jsonl", react_records)
    save_jsonl(out_path / "reflexion_runs.jsonl", reflexion_records)

    # File nộp gọn: dự đoán của agent Reflexion (agent tốt nhất).
    predictions = [{"qid": r.qid, "question": r.question, "predicted_answer": r.predicted_answer} for r in reflexion_records]
    (out_path / "predictions.json").write_text(json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8")

    report = build_report(all_records, dataset_name=Path(dataset).name, mode=mode)
    save_report(report, out_path)
    print(json.dumps(report.summary, indent=2))
    print(f"[green]Saved[/green] {out_path}/report.json  &  predictions.json")


if __name__ == "__main__":
    app()
