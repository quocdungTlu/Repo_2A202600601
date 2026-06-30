from __future__ import annotations

"""Module 4: RAGAS Evaluation — 4 metrics + failure analysis."""

import os, sys, json
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TEST_SET_PATH, OPENAI_BASE_URL, OPENAI_MODEL


@dataclass
class EvalResult:
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str
    faithfulness: float
    answer_relevancy: float
    context_precision: float
    context_recall: float


def load_test_set(path: str = TEST_SET_PATH) -> list[dict]:
    """Load test set from JSON. (Đã implement sẵn)"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _llm_score(prompt: str, api_key: str, model: str, base_url: str | None = None) -> float:
    """Call LLM and parse a 0.0–1.0 score from response."""
    import json as _json
    from openai import OpenAI
    import httpx
    kwargs: dict = {"api_key": api_key,
                    "http_client": httpx.Client(headers={"User-Agent": "python-httpx/0.27.0"})}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        timeout=30,
    )
    try:
        data = _json.loads(resp.choices[0].message.content)
        score = float(data.get("score", data.get("value", 0.0)))
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.0


def _eval_one(question: str, answer: str, contexts: list[str],
              ground_truth: str, api_key: str, model: str, base_url: str | None) -> EvalResult:
    """Compute 4 RAGAS-like metrics for one question via LLM."""
    ctx_text = "\n---\n".join(contexts) if contexts else "(no context)"

    faithfulness_prompt = (
        f'Context:\n{ctx_text}\n\nAnswer:\n{answer}\n\n'
        'Score how much the answer is ONLY grounded in the context (0=hallucination, 1=fully grounded). '
        'Return JSON {"score": <float 0-1>}.'
    )
    relevancy_prompt = (
        f'Question: {question}\n\nAnswer: {answer}\n\n'
        'Score how directly the answer addresses the question (0=irrelevant, 1=perfectly relevant). '
        'Return JSON {"score": <float 0-1>}.'
    )
    precision_prompt = (
        f'Question: {question}\n\nContexts:\n{ctx_text}\n\n'
        'Score what fraction of these contexts are actually relevant to answering the question '
        '(0=all irrelevant, 1=all relevant). Return JSON {"score": <float 0-1>}.'
    )
    recall_prompt = (
        f'Question: {question}\n\nGround truth: {ground_truth}\n\nContexts:\n{ctx_text}\n\n'
        'Score what fraction of the ground-truth information is covered by the contexts '
        '(0=nothing covered, 1=fully covered). Return JSON {"score": <float 0-1>}.'
    )

    return EvalResult(
        question=question, answer=answer, contexts=contexts, ground_truth=ground_truth,
        faithfulness=_llm_score(faithfulness_prompt, api_key, model, base_url),
        answer_relevancy=_llm_score(relevancy_prompt, api_key, model, base_url),
        context_precision=_llm_score(precision_prompt, api_key, model, base_url),
        context_recall=_llm_score(recall_prompt, api_key, model, base_url),
    )


def evaluate_ragas(questions: list[str], answers: list[str],
                   contexts: list[list[str]], ground_truths: list[str]) -> dict:
    """Run RAGAS evaluation — LLM-based fallback when ragas library is incompatible."""
    zeros = {"faithfulness": 0.0, "answer_relevancy": 0.0,
             "context_precision": 0.0, "context_recall": 0.0, "per_question": []}

    # Try native ragas library first
    try:
        import langchain
        for _attr in ("verbose", "debug", "llm_cache", "callbacks"):
            if not hasattr(langchain, _attr):
                setattr(langchain, _attr, False if _attr != "callbacks" else None)
        try:
            import langchain.pydantic_v1  # noqa: F401
        except (ImportError, ModuleNotFoundError):
            from langchain_core import pydantic_v1 as _pv1
            langchain.pydantic_v1 = _pv1
            import sys as _sys
            _sys.modules["langchain.pydantic_v1"] = _pv1

        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
        from datasets import Dataset
        ragas_kwargs = {}
        if OPENAI_BASE_URL:
            from langchain_openai import ChatOpenAI, OpenAIEmbeddings
            import httpx
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper
            _http = httpx.Client(headers={"User-Agent": "python-httpx/0.27.0"})
            _llm = ChatOpenAI(model=OPENAI_MODEL, base_url=OPENAI_BASE_URL, http_client=_http)
            _emb = OpenAIEmbeddings(base_url=OPENAI_BASE_URL, http_client=_http)
            ragas_kwargs = {"llm": LangchainLLMWrapper(_llm), "embeddings": LangchainEmbeddingsWrapper(_emb)}
        dataset = Dataset.from_dict({
            "question": questions, "answer": answers,
            "contexts": contexts, "ground_truth": ground_truths,
        })
        result = evaluate(dataset, metrics=[faithfulness, answer_relevancy,
                                            context_precision, context_recall], **ragas_kwargs)
        df = result.to_pandas()
        per_question = [
            EvalResult(
                question=row["question"], answer=row["answer"],
                contexts=row["contexts"], ground_truth=row["ground_truth"],
                faithfulness=float(row.get("faithfulness", 0.0) or 0.0),
                answer_relevancy=float(row.get("answer_relevancy", 0.0) or 0.0),
                context_precision=float(row.get("context_precision", 0.0) or 0.0),
                context_recall=float(row.get("context_recall", 0.0) or 0.0),
            )
            for _, row in df.iterrows()
        ]
        return {"faithfulness": float(df["faithfulness"].mean()),
                "answer_relevancy": float(df["answer_relevancy"].mean()),
                "context_precision": float(df["context_precision"].mean()),
                "context_recall": float(df["context_recall"].mean()),
                "per_question": per_question}
    except Exception as e:
        print(f"  ⚠️  RAGAS library failed ({e}), falling back to LLM-based eval...")

    # LLM-based fallback (RAGAS-compatible prompts, direct OpenAI calls)
    from config import OPENAI_API_KEY
    if not OPENAI_API_KEY:
        print("  ⚠️  No OPENAI_API_KEY — skipping evaluation")
        return zeros

    per_question = []
    for i, (q, a, ctx, gt) in enumerate(zip(questions, answers, contexts, ground_truths)):
        try:
            res = _eval_one(q, a, ctx, gt, OPENAI_API_KEY, OPENAI_MODEL,
                            OPENAI_BASE_URL or None)
            per_question.append(res)
            if (i + 1) % 10 == 0:
                print(f"    Evaluated {i+1}/{len(questions)}")
        except Exception as ex:
            print(f"    ⚠️  Q{i+1} eval failed: {ex}")
            per_question.append(EvalResult(q, a, ctx, gt, 0.0, 0.0, 0.0, 0.0))

    def _mean(attr: str) -> float:
        vals = [getattr(r, attr) for r in per_question]
        return sum(vals) / len(vals) if vals else 0.0

    return {
        "faithfulness": _mean("faithfulness"),
        "answer_relevancy": _mean("answer_relevancy"),
        "context_precision": _mean("context_precision"),
        "context_recall": _mean("context_recall"),
        "per_question": per_question,
    }


def failure_analysis(eval_results: list[EvalResult], bottom_n: int = 10) -> list[dict]:
    """Analyze bottom-N worst questions using Diagnostic Tree."""
    diagnostic_tree = {
        "faithfulness": ("LLM hallucinating", "Tighten prompt, lower temperature"),
        "context_recall": ("Missing relevant chunks", "Improve chunking or add BM25"),
        "context_precision": ("Too many irrelevant chunks", "Add reranking or metadata filter"),
        "answer_relevancy": ("Answer doesn't match question", "Improve prompt template"),
    }

    scored = []
    for r in eval_results:
        metrics = {
            "faithfulness": r.faithfulness,
            "context_recall": r.context_recall,
            "context_precision": r.context_precision,
            "answer_relevancy": r.answer_relevancy,
        }
        avg = sum(metrics.values()) / len(metrics)
        worst_metric = min(metrics, key=lambda k: metrics[k])
        scored.append((avg, r, worst_metric, metrics[worst_metric]))

    scored.sort(key=lambda x: x[0])

    results = []
    for avg, r, worst_metric, worst_score in scored[:bottom_n]:
        diagnosis, suggested_fix = diagnostic_tree[worst_metric]
        results.append({
            "question": r.question,
            "worst_metric": worst_metric,
            "score": round(worst_score, 4),
            "avg_score": round(avg, 4),
            "diagnosis": diagnosis,
            "suggested_fix": suggested_fix,
        })
    return results


def save_report(results: dict, failures: list[dict], path: str = "ragas_report.json"):
    """Save evaluation report to JSON. (Đã implement sẵn)"""
    report = {
        "aggregate": {k: v for k, v in results.items() if k != "per_question"},
        "num_questions": len(results.get("per_question", [])),
        "failures": failures,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report saved to {path}")


if __name__ == "__main__":
    test_set = load_test_set()
    print(f"Loaded {len(test_set)} test questions")
    print("Run pipeline.py first to generate answers, then call evaluate_ragas().")
