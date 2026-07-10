from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .graph import run_direct, run_graph


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TCR agent prototype.")
    parser.add_argument("--input", required=True, help="Path to a project input JSON file.")
    parser.add_argument("--direct", action="store_true", help="Run TestAgent directly without LangGraph.")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    try:
        state = run_direct(data) if args.direct else run_graph(data)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
