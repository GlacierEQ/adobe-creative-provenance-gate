from __future__ import annotations

from dataclasses import replace

from creative_provenance_gate import (
    CreativeProvenanceGate,
    CreativeProvenanceGateRequest,
    Decision,
)


def _request(**overrides):
    payload = {
        "sources": [
            {
                "id": "brand-logo",
                "content": "vector-logo-v1",
                "rights": "owned",
                "mime": "image/svg+xml",
            }
        ],
        "transforms": [
            {
                "op": "crop",
                "tool": "editor",
                "version": "1",
                "params": {"x": 8, "y": 8},
                "preserves_editability": True,
            }
        ],
        "output": {"format": "psd", "editable": True},
    }
    payload.update(overrides.pop("payload", {}))
    return CreativeProvenanceGateRequest(subject_id="campaign-asset", payload=payload, budget=1.0, **overrides)


def test_builds_content_addressed_manifest() -> None:
    receipt = CreativeProvenanceGate().evaluate(_request())
    assert receipt.decision is Decision.ALLOW
    assert receipt.reasons == ("provenance_bound",)
    assert len(receipt.digest) == 64
    assert receipt.metrics["source_count"] == 1
    assert receipt.metrics["transform_count"] == 1
    assert receipt.metrics["rights_verified"] is True
    assert receipt.manifest["sources"][0]["sha256"]
    assert "content" not in receipt.manifest["sources"][0]
    assert receipt.manifest["chain"][-1] != receipt.manifest["source_root"]


def test_same_request_is_deterministic() -> None:
    mech = CreativeProvenanceGate()
    first = mech.evaluate(_request())
    second = mech.evaluate(_request())
    assert first.digest == second.digest
    assert first.manifest == second.manifest


def test_tampering_is_detected() -> None:
    mech = CreativeProvenanceGate()
    req = _request()
    receipt = mech.evaluate(req)
    mutated = _request(payload={
        "sources": [{"id": "brand-logo", "content": "vector-logo-v2", "rights": "owned"}],
        "transforms": req.payload["transforms"],
        "output": req.payload["output"],
    })
    verification = mech.verify(mutated, receipt)
    assert verification["ok"] is False
    assert verification["digest"] != receipt.digest


def test_refuses_unverified_rights() -> None:
    req = _request(payload={
        "sources": [{"id": "stock", "content": "pixels", "rights": "unknown"}],
        "transforms": [],
        "output": {"format": "png", "editable": False},
    })
    receipt = CreativeProvenanceGate().evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "source_stock_rights_unverified" in receipt.reasons


def test_generative_transform_requires_model_identity() -> None:
    req = _request(payload={
        "sources": [{"id": "photo", "content": "pixels", "rights": "owned"}],
        "transforms": [{"op": "generative_fill", "tool": "creative-tool"}],
        "output": {"format": "psd", "editable": True},
    })
    receipt = CreativeProvenanceGate().evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "transform_0_model_missing" in receipt.reasons


def test_refuses_destructive_step_claiming_editable_output() -> None:
    req = _request(payload={
        "sources": [{"id": "photo", "content": "pixels", "rights": "licensed", "license_id": "L-42"}],
        "transforms": [{"op": "flatten", "tool": "editor", "preserves_editability": False}],
        "output": {"format": "psd", "editable": True},
    })
    receipt = CreativeProvenanceGate().evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "editable_output_has_destructive_transform" in receipt.reasons


def test_refuses_invalid_envelope() -> None:
    receipt = CreativeProvenanceGate().evaluate(
        CreativeProvenanceGateRequest(subject_id=" ", payload={}, budget=0.0)
    )
    assert receipt.decision is Decision.REFUSE
    assert "subject_id_missing" in receipt.reasons
    assert "budget_non_positive" in receipt.reasons
    assert "sources_missing" in receipt.reasons
    assert "output_format_missing" in receipt.reasons
