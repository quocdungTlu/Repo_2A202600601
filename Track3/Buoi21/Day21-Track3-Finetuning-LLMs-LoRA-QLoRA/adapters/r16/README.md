---
base_model: unsloth/Qwen2.5-3B-bnb-4bit
library_name: peft
tags:
  - lora
  - qlora
  - peft
  - unsloth
  - qwen2.5
  - vietnamese
  - instruction-tuning
language:
  - vi
license: apache-2.0
datasets:
  - 5CD-AI/Vietnamese-alpaca-gpt4-gg-translated
pipeline_tag: text-generation
---

# Qwen2.5-3B · Vietnamese Alpaca LoRA (r=16) — Lab 21

LoRA adapter fine-tune trên **Qwen2.5-3B** (4-bit QLoRA) với tập Vietnamese-Alpaca, làm trong **Lab 21 — AICB-P2T3 (Fine-tuning LLMs · LoRA/QLoRA)**.

## Chi tiết

| | |
|---|---|
| **Base model** | `unsloth/Qwen2.5-3B-bnb-4bit` (4-bit NF4) |
| **Method** | QLoRA · PEFT LoRA |
| **Rank / alpha** | r=16 / α=32 |
| **Target modules** | `q_proj`, `v_proj` |
| **Dataset** | `5CD-AI/Vietnamese-alpaca-gpt4-gg-translated` (200 samples, 180 train / 20 eval) |
| **Train** | 3 epochs · cosine LR=2e-4 · warmup 0.10 · effective batch=8 · adamw_8bit · T4 |
| **Trainable params** | 3,686,400 (~0.12% của base) |
| **Eval perplexity** | 4.554 (eval_loss 1.516) |

## Cách dùng

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base = AutoModelForCausalLM.from_pretrained("unsloth/Qwen2.5-3B-bnb-4bit", device_map="auto")
tok  = AutoTokenizer.from_pretrained("unsloth/Qwen2.5-3B-bnb-4bit")
model = PeftModel.from_pretrained(base, "QuocDung201102/qwen2.5-3b-vi-lab21-r16")

prompt = "### Instruction:\nGiải thích machine learning cho người mới.\n\n### Response:\n"
print(tok.decode(model.generate(**tok(prompt, return_tensors="pt").to(model.device),
                                max_new_tokens=200)[0], skip_special_tokens=True))
```

## Rank experiment (trên cùng dataset)

| Rank | Params | Perplexity |
|------|--------|-----------|
| 8 | 1.84M | 4.748 |
| **16** | **3.69M** | **4.554** |
| 64 | 14.75M | 4.379 |

→ r=16 cho ROI tốt nhất; diminishing returns rõ sau r=16. Xem REPORT đầy đủ trong repo lab.
