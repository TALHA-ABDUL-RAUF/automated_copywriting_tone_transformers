"""
batch_simulation.py
--------------------
FALLBACK for accounts without Groq Batch API access (free tier returns
403 'Not available for your plan' on client.files.create()).

This module proves the SAME concept as batch_pipeline.py — bulk
processing of many (product, platform, tone) rows from a CSV — but
routes every request through the real-time chat.completions endpoint
instead of the paid Batch API. It reuses the exact same prompt_engine
and Pydantic schema as everything else, so brand voice and validation
never drift between paths.

Key difference from batch_pipeline.py:
  - batch_pipeline.py  -> Groq Batch API (async job, 24h-7d window, 50% cheaper, paid tier only)
  - batch_simulation.py -> asyncio.gather + Semaphore over the SAME real-time
                            endpoint used by async_pipeline.py (runs immediately,
                            full price, works on ANY tier)

This is the honest engineering tradeoff to document: true batch
processing needs a paid tier; this simulation demonstrates the same
bulk-orchestration pattern without that dependency.
"""

import asyncio
import csv
import json
from pathlib import Path

from src.async_pipeline import generate_one
from src.schemas import BatchJobRecord, GenerationRequest, MarketingCopy


def load_records(csv_path: str) -> list[BatchJobRecord]:
    records: list[BatchJobRecord] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(BatchJobRecord(**row))
    return records


async def run_simulation(csv_path: str, output_path: str) -> list[MarketingCopy]:
    """
    Reads a CSV of (product_name, description, platform, tone) rows,
    fans them out concurrently through the SAME semaphore-guarded,
    retry-protected pipeline used for real-time generation, and writes
    every validated result to a JSONL file.

    This mirrors what the real Batch API would give you at the end —
    a completed output file — just without the 24h wait or the cost
    discount, since it runs on-demand against the sync endpoint.
    """
    records = load_records(csv_path)

    requests = [
        GenerationRequest(
            product_name=r.product_name,
            description=r.description,
            platform=r.platform,
            tone=r.tone,
        )
        for r in records
    ]

    print(f"Simulating bulk batch for {len(requests)} rows "
          f"(concurrent, semaphore-limited, real-time endpoint)...")

    tasks = [generate_one(req) for req in requests]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final: list[MarketingCopy] = []
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as out_f:
        for req, result in zip(requests, results):
            if isinstance(result, Exception):
                copy = MarketingCopy(
                    headline="[GENERATION FAILED]",
                    body=str(result),
                    call_to_action="",
                    hashtags=[],
                    platform=req.platform,
                    tone=req.tone,
                ).finalize()
            else:
                copy = result

            final.append(copy)
            out_f.write(json.dumps(copy.model_dump()) + "\n")

    print(f"Done. {len(final)} results written to {output_path}")
    return final
