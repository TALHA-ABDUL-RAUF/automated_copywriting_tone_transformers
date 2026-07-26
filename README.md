# Automated Copywriting & Tone Transformer

Generative AI Engineering  Project 2 (DecodeLabs)
LLM Provider: **Groq** (OpenAI-compatible API)

---

## 1. What this project is

A prompt-compilation engine that turns a raw product description into
platform-tailored, tone-controlled marketing copy on demand (real-time)
or at scale (batch).

It is **not** "a script that calls an LLM." It is three separable
concerns wired together the way a production system would be:

```
Input (CLI/CSV) → Prompt Compiler → Router → [Real-time | Batch] → Pydantic-validated Output
```

## 2. Folder structure

```
copywriting_tone_transformer/
├── README.md
├── requirements.txt
├── .env.example
├── main.py                  # single entry point (CLI)
├── data/
│   └── sample_products.csv  # example bulk input for the batch pipeline
└── src/
    ├── __init__.py
    ├── config.py             # env loading + platform constraint rules
    ├── schemas.py            # Pydantic output models (structured, validated)
    ├── prompt_engine.py      # the "Master Instruction Template" compiler
    ├── async_pipeline.py     # real-time path: asyncio + Semaphore + retry
    ├── batch_pipeline.py     # bulk path: Groq Batch API (JSONL upload → poll → fetch)
    └── cli.py                # argparse — the entry point users actually touch
```

Why this shape, not one big `script.py`:

| File                  | Single Responsibility                                  | Why it's separate                                                           |
| --------------------- | ------------------------------------------------------ | --------------------------------------------------------------------------- |
| `schemas.py`        | Defines the*contract* of what "done" looks like      | The model can hallucinate structure; the schema can't                       |
| `prompt_engine.py`  | Compiles variables into the frozen brand-safe template | So the brand voice/rules live in ONE place, not scattered across call sites |
| `config.py`         | Platform character limits, model name, defaults        | So a platform rule change (e.g. X's limit changes) is a one-line edit       |
| `async_pipeline.py` | Fast path for a handful of live requests               | Optimizes for latency                                                       |
| `batch_pipeline.py` | Slow path for thousands of requests                    | Optimizes for cost (50% cheaper on Groq) and throughput                     |
| `cli.py`            | User-facing surface                                    | Keeps argument parsing out of business logic                                |

This separation is the actual "engineering" DecodeLabs is grading —
anyone can call `client.chat.completions.create()` once. Structuring it
so the same prompt-compiler feeds *both* a live app and a bulk job
without being rewritten is the point.

## 3. Setup

```bash
cd copywriting_tone_transformer
python -m venv venv && source venv/bin/activate     # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env       # then paste your GROQ_API_KEY inside
```

## 4. Usage

### A) Real-time — generate copy for one product, one platform

```bash
python main.py generate \
  --product "Aether Wireless Earbuds" \
  --description "Noise-cancelling earbuds with 30-hour battery life." \
  --platform instagram \
  --tone witty \
  --temperature 0.8
```

### B) Real-time — generate for ALL platforms concurrently (async fan-out)

```bash
python main.py generate-all \
  --product "Aether Wireless Earbuds" \
  --description "Noise-cancelling earbuds with 30-hour battery life." \
  --tone professional
```

### C) Bulk — submit a CSV of products as a Groq Batch job (50% cheaper)

```bash
python main.py batch-submit --input data/sample_products.csv
# ... prints a batch_id, wait 24h-7d window ...
python main.py batch-status --batch-id <batch_id>
python main.py batch-fetch  --batch-id <batch_id> --output outputs/results.jsonl
```

## 5. Key concepts this project exercises

- **Dynamic prompt template compilation** — `prompt_engine.py` uses
  f-strings to inject `product_name`, `platform`, `tone`, `description`
  into a locked master template, with platform-specific hard
  constraints (e.g. X/Twitter → 280 chars) appended conditionally.
- **Inference parameter tuning** — `temperature` / `top_p` are exposed
  as CLI flags, not hardcoded, because creative variance is a business
  decision (LinkedIn ≠ Instagram).
- **Structured output validation** — every response is parsed into a
  `MarketingCopy` Pydantic model before being accepted. If the model
  returns malformed JSON, we retry rather than silently pass garbage
  downstream.
- **Concurrency control** — `asyncio.Semaphore` caps simultaneous
  in-flight requests so we don't trip Groq's rate limits; `tenacity`
  adds exponential backoff with jitter for transient failures.
- **Batch vs. real-time tradeoff** — real-time trades cost for
  latency; batch trades latency (up to 7 days) for a 50% cost cut and
  a separate, much larger rate-limit pool. This project implements
  *both* so you can reason about when to use each.
