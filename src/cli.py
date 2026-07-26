"""
cli.py
------
The user-facing surface. argparse captures raw input; this file
translates it into calls against the prompt engine and pipelines.
No business logic lives here — it's purely a routing/formatting layer.
"""

import argparse
import asyncio
import csv
import json

from src.config import PLATFORM_RULES, DEFAULT_TEMPERATURE, DEFAULT_TOP_P
from src.schemas import GenerationRequest, BatchJobRecord
from src.async_pipeline import generate_one, generate_many
from src.batch_pipeline import build_jsonl, submit_batch, check_status, fetch_results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="copywriting-engine",
        description="Automated Copywriting & Tone Transformer (Groq-powered)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- generate: single product, single platform ---
    p_gen = sub.add_parser("generate", help="Generate copy for one platform")
    p_gen.add_argument("--product", required=True)
    p_gen.add_argument("--description", required=True)
    p_gen.add_argument("--platform", required=True, choices=list(PLATFORM_RULES.keys()))
    p_gen.add_argument("--tone", required=True)
    p_gen.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    p_gen.add_argument("--top-p", type=float, default=DEFAULT_TOP_P)

    # --- generate-all: single product, every platform, concurrently ---
    p_all = sub.add_parser("generate-all", help="Generate copy for ALL platforms concurrently")
    p_all.add_argument("--product", required=True)
    p_all.add_argument("--description", required=True)
    p_all.add_argument("--tone", required=True)
    p_all.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)

    # --- batch-submit: CSV of many products -> Groq Batch API ---
    p_bsub = sub.add_parser("batch-submit", help="Submit a CSV of products as a Groq batch job")
    p_bsub.add_argument("--input", required=True, help="Path to CSV with columns: product_name,description,platform,tone")
    p_bsub.add_argument("--completion-window", default="24h")

    # --- batch-status ---
    p_bstat = sub.add_parser("batch-status", help="Check a batch job's status")
    p_bstat.add_argument("--batch-id", required=True)

    # --- batch-fetch ---
    p_bfetch = sub.add_parser("batch-fetch", help="Download a completed batch job's results")
    p_bfetch.add_argument("--batch-id", required=True)
    p_bfetch.add_argument("--output", default="outputs/results.jsonl")

    return parser


def _print_copy(copy) -> None:
    print(json.dumps(copy.model_dump(), indent=2))


def cmd_generate(args: argparse.Namespace) -> None:
    request = GenerationRequest(
        product_name=args.product,
        description=args.description,
        platform=args.platform,
        tone=args.tone,
        temperature=args.temperature,
        top_p=args.top_p,
    )
    result = asyncio.run(generate_one(request))
    _print_copy(result)


def cmd_generate_all(args: argparse.Namespace) -> None:
    requests = [
        GenerationRequest(
            product_name=args.product,
            description=args.description,
            platform=platform,
            tone=args.tone,
            temperature=args.temperature,
        )
        for platform in PLATFORM_RULES.keys()
    ]
    results = asyncio.run(generate_many(requests))
    for r in results:
        _print_copy(r)
        print("-" * 40)


def cmd_batch_submit(args: argparse.Namespace) -> None:
    records = []
    with open(args.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(BatchJobRecord(**row))

    jsonl_path = build_jsonl(records, out_path="outputs/batch_input.jsonl")
    batch_id = submit_batch(jsonl_path, completion_window=args.completion_window)
    print(f"Batch submitted. batch_id = {batch_id}")
    print("Save this ID — use `batch-status` and `batch-fetch` to check on it later.")


def cmd_batch_status(args: argparse.Namespace) -> None:
    info = check_status(args.batch_id)
    print(json.dumps(info, indent=2, default=str))


def cmd_batch_fetch(args: argparse.Namespace) -> None:
    path = fetch_results(args.batch_id, args.output)
    print(f"Results written to {path}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "generate": cmd_generate,
        "generate-all": cmd_generate_all,
        "batch-submit": cmd_batch_submit,
        "batch-status": cmd_batch_status,
        "batch-fetch": cmd_batch_fetch,
    }
    dispatch[args.command](args)
