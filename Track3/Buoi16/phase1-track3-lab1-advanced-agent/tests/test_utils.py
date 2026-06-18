import json

from src.reflexion_lab.utils import load_dataset_flexible, normalize_answer


def test_normalize_answer():
    assert normalize_answer("Oxford University!") == "oxford university"


def test_flexible_loader_raw_hotpot(tmp_path):
    """Loader nhận raw HotpotQA: context [title,[sents]], _id, answer, thiếu level."""
    raw = [{"_id": "r1", "question": "Q?", "answer": "Paris",
            "context": [["City", ["Paris is in France."]]]}]
    p = tmp_path / "raw.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    ex = load_dataset_flexible(p)
    assert len(ex) == 1
    assert ex[0].qid == "r1" and ex[0].gold_answer == "Paris"
    assert ex[0].difficulty == "hard"  # thiếu level -> mặc định
    assert ex[0].context[0].text == "Paris is in France."


def test_flexible_loader_wrapped_and_bad_difficulty(tmp_path):
    """Loader nhận {"data":[...]} và difficulty không hợp lệ -> ép về hard."""
    wrapped = {"data": [{"qid": "w1", "difficulty": "extreme", "question": "Q?",
                          "gold_answer": "Z", "context": [{"title": "T", "text": "t"}]}]}
    p = tmp_path / "w.json"
    p.write_text(json.dumps(wrapped), encoding="utf-8")
    ex = load_dataset_flexible(p)
    assert len(ex) == 1 and ex[0].difficulty == "hard"


def test_flexible_loader_missing_gold(tmp_path):
    """Blind set không có gold_answer -> rỗng, không crash."""
    p = tmp_path / "blind.json"
    p.write_text(json.dumps([{"qid": "b1", "question": "Q?", "context": []}]), encoding="utf-8")
    ex = load_dataset_flexible(p)
    assert ex[0].gold_answer == ""


def test_clean_answer():
    from src.reflexion_lab.mock_runtime import _clean_answer
    assert _clean_answer("The answer is Paris.") == "Paris"
    assert _clean_answer('"Oxford University"') == "Oxford University"
    assert _clean_answer("Answer: yes\nbecause...") == "yes"
    assert _clean_answer("") == ""


def test_run_pair_react_is_reflexion_first_attempt():
    """ReAct phải bằng attempt-1 của Reflexion (mock mode)."""
    from src.reflexion_lab.agents import run_pair
    from src.reflexion_lab.schemas import QAExample
    ex = QAExample(qid="hp1", difficulty="easy", question="Q?", gold_answer="A",
                   context=[{"title": "T", "text": "t"}])
    react, reflexion = run_pair(ex, max_attempts=3)
    assert react.agent_type == "react" and reflexion.agent_type == "reflexion"
    assert react.attempts == 1
    assert react.predicted_answer == reflexion.traces[0].answer
