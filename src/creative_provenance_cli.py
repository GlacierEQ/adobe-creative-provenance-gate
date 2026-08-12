"""JSON command-line interface for the creative provenance engine."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Optional

from creative_provenance_gate import (
    CreativeProvenanceGate,
    CreativeProvenanceGateRequest,
    Decision,
    SourceAssetClaim,
    TransformClaim,
)


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a JSON array")
    return value


def _source(value: Any, index: int) -> SourceAssetClaim:
    item = _object(value, f"sources[{index}]")
    metadata = item.get("metadata", {})
    return SourceAssetClaim(
        asset_id=str(item.get("asset_id", "")),
        sha256=str(item.get("sha256", "")),
        rights=str(item.get("rights", "owned")),
        allow_derivatives=bool(item.get("allow_derivatives", True)),
        editable=bool(item.get("editable", True)),
        metadata=dict(_object(metadata, f"sources[{index}].metadata")),
    )


def _transform(value: Any, index: int) -> TransformClaim:
    item = _object(value, f"transforms[{index}]")
    raw_inputs = _sequence(item.get("input_sha256", []), f"transforms[{index}].input_sha256")
    params = item.get("params", {})
    model_id = item.get("model_id")
    return TransformClaim(
        operation=str(item.get("operation", "")),
        input_sha256=tuple(str(value) for value in raw_inputs),
        output_sha256=str(item.get("output_sha256", "")),
        tool_id=str(item.get("tool_id", "")),
        model_id=str(model_id) if model_id is not None else None,
        params=dict(_object(params, f"transforms[{index}].params")),
        cost=float(item.get("cost", 0.0)),
        preserves_editability=bool(item.get("preserves_editability", True)),
    )


def request_from_mapping(value: Mapping[str, Any]) -> CreativeProvenanceGateRequest:
    payload = dict(_object(value.get("payload", {}), "payload"))
    brand_rules = dict(_object(value.get("brand_rules", {}), "brand_rules"))
    sources = tuple(
        _source(item, index)
        for index, item in enumerate(_sequence(value.get("sources", []), "sources"))
    )
    transforms = tuple(
        _transform(item, index)
        for index, item in enumerate(_sequence(value.get("transforms", []), "transforms"))
    )
    grant_id = value.get("grant_id")
    output_sha256 = value.get("output_sha256")
    not_after = value.get("not_after")
    now = value.get("now")
    return CreativeProvenanceGateRequest(
        subject_id=str(value.get("subject_id", "")),
        payload=payload,
        budget=float(value.get("budget", 1.0)),
        grant_id=str(grant_id) if grant_id is not None else None,
        not_after=float(not_after) if not_after is not None else None,
        now=float(now) if now is not None else None,
        sources=sources,
        transforms=transforms,
        output_sha256=str(output_sha256) if output_sha256 is not None else None,
        requires_editable=bool(value.get("requires_editable", False)),
        brand_rules=brand_rules,
    )


def evaluate_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    gate = CreativeProvenanceGate()
    request = request_from_mapping(value)
    receipt = gate.evaluate(request)
    verified, verification_reason = gate.verify_receipt(request, receipt)
    output = receipt.as_dict()
    output["receipt_verified"] = verified
    output["verification_reason"] = verification_reason
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="creative-provenance",
        description="Verify content-addressed creative lineage and provenance",
    )
    parser.add_argument("--input", type=Path, help="request JSON file; stdin when omitted")
    parser.add_argument("--output", type=Path, help="optional receipt JSON destination")
    parser.add_argument("--pretty", action="store_true", help="pretty-print receipt JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    raw = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
    try:
        parsed = json.loads(raw)
        request = _object(parsed, "request")
        result = evaluate_mapping(request)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        result = {
            "decision": Decision.REFUSE.value,
            "reasons": [f"invalid_request:{exc}"],
            "receipt_verified": False,
            "verification_reason": "REQUEST_PARSE_FAILED",
        }
        encoded = json.dumps(result, indent=2 if args.pretty else None, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 2

    encoded = json.dumps(result, indent=2 if args.pretty else None, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["decision"] == Decision.ALLOW.value and result["receipt_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
