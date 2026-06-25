# Lab 21 — Links

**Học viên**: Lương Quốc Dũng — 2A202600601
**Submission option**: B (GitHub + HuggingFace Hub)

## 🤗 HuggingFace Hub — LoRA adapter (r=16, best ROI)

- **Adapter (public, verifiable)**: https://huggingface.co/QuocDung201102/qwen2.5-3b-vi-lab21-r16
- **Base model**: https://huggingface.co/unsloth/Qwen2.5-3B-bnb-4bit
- **Dataset**: https://huggingface.co/datasets/5CD-AI/Vietnamese-alpaca-gpt4-gg-translated

Tải nhanh để verify:
```python
from peft import PeftModel
from transformers import AutoModelForCausalLM
base = AutoModelForCausalLM.from_pretrained("unsloth/Qwen2.5-3B-bnb-4bit", device_map="auto")
model = PeftModel.from_pretrained(base, "QuocDung201102/qwen2.5-3b-vi-lab21-r16")
```

## 📦 Nội dung submission

- `REPORT.md` — evaluation report (6 sections)
- `notebook.ipynb` — Lab21 notebook (stripped outputs)
- `results/` — `rank_experiment_summary.csv`, `qualitative_comparison.csv`, `loss_curve.png`
- `adapters/r16/` — adapter local backup (cũng đã push HF Hub ở trên)
