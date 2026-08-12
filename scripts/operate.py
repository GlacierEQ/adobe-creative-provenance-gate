#!/usr/bin/env python3
"""Run a concrete creative-lineage verification demo."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from creative_provenance_gate import (  # noqa: E402
    CreativeProvenanceGate,
    CreativeProvenanceGateRequest,
    Decision,
    RightsStatus,
)


def main() -> int:
    mech = CreativeProvenanceGate(clock=lambda: 1_000.0)

    logo = mech.source_claim(
        "brand-logo",
        b"vector-logo:v3",
        rights=RightsStatus.OWNED,
        metadata={"format": "svg", "editable": True},
    )
    photo = mech.source_claim(
        "licensed-photo",
        b"licensed-photo:asset-42",
        rights=RightsStatus.LICENSED,
        metadata={"license": "demo-license-42"},
    )

    layered_output = b"layered-hero:vector-logo:v3+licensed-photo:asset-42"
    compose = mech.transform_claim(
        "compose",
        [logo, photo],
        layered_output,
        tool_id="layer-compositor/1.0",
        params={"layout": "hero", "layers": 2},
        cost=0.20,
        preserves_editability=True,
    )

    request = CreativeProvenanceGateRequest(
        subject_id="portfolio-hero-v1",
        payload={"tags": ["brand-safe", "editable"], "campaign": "portfolio"},
        budget=1.00,
        grant_id="local-demo-grant",
        not_after=2_000.0,
        now=1_000.0,
        sources=(logo, photo),
        transforms=(compose,),
        output_sha256=mech.content_digest(layered_output),
        requires_editable=True,
        brand_rules={
            "required_tags": ["brand-safe", "editable"],
            "forbidden_tags": ["unapproved"],
            "required_metadata": {"campaign": "portfolio"},
        },
    )

    receipt = mech.evaluate(request)
    verified, verify_reason = mech.verify_receipt(request, receipt)
    output = receipt.as_dict()
    output["receipt_verified"] = verified
    output["verification_reason"] = verify_reason

    print(json.dumps(output, indent=2, sort_keys=True))
    if receipt.decision is not Decision.ALLOW or not verified:
        return 2
    if output["lineage"]["terminal_output"] != request.output_sha256:
        return 3
    if output["metrics"]["source_count"] != 2 or output["metrics"]["transform_count"] != 1:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
