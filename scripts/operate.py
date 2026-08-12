#!/usr/bin/env python3
"""Run the creative provenance engine against a JSON workflow description."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creative_provenance_gate import (  # noqa: E402
    CreativeProvenanceGate,
    CreativeProvenanceGateRequest,
    Decision,
)


DEMO = {
    "subject_id": "demo-campaign-asset",
    "budget": 1.0,
    "grant_id": "local-demo",
    "payload": {
        "sources": [
            {
                "id": "brand-mark",
                "content": "demo-vector-source",
                "rights": "owned",
                "mime": "image/svg+xml",
            }
        ],
        "transforms": [
            {
                "op": "generative_fill",
                "tool": "creative-editor",
                "model": "demo-model-v1",
                "params": {"prompt_digest": "demo"},
                "preserves_editability": True,
            }
        ],
        "output": {"format": "psd", "editable": True, "profile": "display-p3"},
    },
}


def _load(path: str | None) -> dict:
    if path is None:
        return DEMO
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("input JSON must be an object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a deterministic creative provenance receipt")
    parser.add_argument("--input", help="JSON request file; uses a built-in demo when omitted")
    parser.add_argument("--output", help="optional path to write the receipt JSON")
    args = parser.parse_args()

    data = _load(args.input)
    request = CreativeProvenanceGateRequest(
        subject_id=str(data.get("subject_id", "")),
        payload=data.get("payload", {}),
        budget=float(data.get("budget", 1.0)),
        grant_id=data.get("grant_id"),
        not_after=data.get("not_after"),
    )
    receipt = CreativeProvenanceGate().evaluate(request)
    rendered = json.dumps(receipt.as_dict(), indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if receipt.decision is Decision.ALLOW else 2


if __name__ == "__main__":
    raise SystemExit(main())
