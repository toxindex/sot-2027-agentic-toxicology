"""`uv run demo` lands here."""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import agent, kg

DEFAULT_QUESTION = (
    "Is oxybenzone (CAS 131-57-7) likely mutagenic, and what does the evidence say?"
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="demo",
        description="Answer a hazard question from public data and a public model, with provenance.",
    )
    parser.add_argument("question", nargs="*", default=None, help="plain-language question containing a CAS number")
    parser.add_argument(
        "--planner",
        default=None,
        choices=["deterministic", "anthropic", "openai"],
        help="default: deterministic, which needs no API key",
    )
    parser.add_argument("--json", action="store_true", help="emit the full trace as JSON")
    args = parser.parse_args(argv)
    question = " ".join(args.question) if args.question else DEFAULT_QUESTION

    started = time.time()
    result = agent.answer(question, planner=args.planner)
    if args.json:
        payload = result.to_dict()
        payload["elapsed_seconds"] = round(time.time() - started, 2)
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(result.render())
        print(f"\n{len(result.facts)} facts, {len(result.steps)} tool calls, "
              f"{time.time() - started:.1f}s, {kg.cached_bytes() / 1e6:.1f} MB cached locally.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
