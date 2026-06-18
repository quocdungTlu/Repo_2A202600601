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
from src.reflexion_lab.agents import ReActAgent, ReflexionAgent
from src.reflexion_lab.reporting import build_report, save_report
from src.reflexion_lab.utils import load_dataset_flexible, save_jsonl

app = typer.Typer(add_completion=False)


def _run_all(agent, examples, workers: int):
    """Chạy agent trên tất cả example song song, GIỮ NGUYÊN THỨ TỰ."""
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(agent.run, examples))


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

    t0 = time.time()
    react_records = _run_all(ReActAgent(), examples, workers)
    reflexion_records = _run_all(ReflexionAgent(max_attempts=reflexion_attempts), examples, workers)
    elapsed = time.time() - t0
    print(f"[green]Done[/green] in {elapsed:.1f}s")

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
