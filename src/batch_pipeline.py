"""
batch_pipeline.py
------------------
The BULK path. Used when latency doesn't matter (overnight jobs,
processing thousands of products) and cost/throughput does.

Groq's Batch API (confirmed live, OpenAI-compatible surface):
  1. Build a JSONL file — one line per request, each with a custom_id.
  2. Upload it with purpose="batch".
  3. Create a batch job pointing at that file (24h-7d completion window).
  4. Poll the batch until status == "completed".
  5. Download the output file and parse results.

This mirrors "openbatch" / BatchCollector from the blueprint, but talks
directly to Groq's native batches.create() — no extra wrapper needed
since Groq's SDK already exposes this cleanly.
"""

import json
import time
from pathlib import Path

from groq import Groq

from src.config import GROQ_API_KEY, GROQ_MODEL
from src.prompt_engine import compile_master_prompt
from src.schemas import BatchJobRecord, GenerationRequest

_client: Groq | None = None


def get_client() -> Groq:
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def build_jsonl(records: list[BatchJobRecord], out_path: str) -> str:
    """Compiles every CSV row into one JSONL line using the SAME prompt
    engine as the real-time pipeline, so brand voice never drifts
    between the two execution paths."""
    lines = []
    for i, rec in enumerate(records):
        req = GenerationRequest(
            product_name=rec.product_name,
            description=rec.description,
            platform=rec.platform,
            tone=rec.tone,
        )
        system_prompt, user_prompt = compile_master_prompt(req)

        lines.append(
            {
                "custom_id": f"req-{i}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": GROQ_MODEL,
                    "temperature": req.temperature,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            }
        )

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")

    return out_path


def submit_batch(jsonl_path: str, completion_window: str = "24h") -> str:
    """Uploads the JSONL file and creates a batch job. Returns batch_id."""
    client = get_client()

    with open(jsonl_path, "rb") as f:
        uploaded = client.files.create(file=f, purpose="batch")

    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window=completion_window,
    )
    return batch.id


def check_status(batch_id: str) -> dict:
    """Returns the current status dict for a batch job."""
    client = get_client()
    batch = client.batches.retrieve(batch_id)
    return {
        "id": batch.id,
        "status": batch.status,
        "request_counts": getattr(batch, "request_counts", None),
        "output_file_id": getattr(batch, "output_file_id", None),
    }


def wait_for_completion(batch_id: str, poll_seconds: int = 30, timeout_seconds: int = 3600) -> dict:
    """Polls until the batch is completed/failed/expired, or timeout is hit.
    NOTE: In production you would NOT block synchronously for up to 7 days —
    you'd persist the batch_id and check back later (e.g. via a cron job or
    webhook). This helper exists for short local testing windows only."""
    elapsed = 0
    while elapsed < timeout_seconds:
        info = check_status(batch_id)
        if info["status"] in ("completed", "failed", "expired", "cancelled"):
            return info
        time.sleep(poll_seconds)
        elapsed += poll_seconds
    raise TimeoutError(f"Batch {batch_id} did not complete within {timeout_seconds}s")


def fetch_results(batch_id: str, output_path: str) -> str:
    """Downloads and saves the completed batch's output JSONL."""
    client = get_client()
    info = check_status(batch_id)

    if info["status"] != "completed":
        raise RuntimeError(f"Batch {batch_id} is not completed yet (status={info['status']})")

    output_file_id = info["output_file_id"]
    content = client.files.content(output_file_id)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    content.write_to_file(output_path)
    return output_path
