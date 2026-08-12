from __future__ import annotations

from creative_provenance_gate import CreativeProvenanceGate, CreativeProvenanceGateRequest, Decision


def _evaluate(payload):
    return CreativeProvenanceGate().evaluate(
        CreativeProvenanceGateRequest(subject_id="asset", payload=payload, budget=1.0)
    )


def test_source_order_does_not_change_root() -> None:
    a = {"id": "a", "content": "A", "rights": "owned"}
    b = {"id": "b", "content": "B", "rights": "licensed", "license_id": "L"}
    common = {"transforms": [], "output": {"format": "png", "editable": False}}
    first = _evaluate({"sources": [a, b], **common})
    second = _evaluate({"sources": [b, a], **common})
    assert first.decision is Decision.ALLOW
    assert first.manifest["source_root"] == second.manifest["source_root"]
    assert first.digest == second.digest


def test_transform_order_changes_chain() -> None:
    source = {"id": "a", "content": "A", "rights": "owned"}
    crop = {"op": "crop", "tool": "editor", "params": {"x": 1}}
    rotate = {"op": "rotate", "tool": "editor", "params": {"deg": 90}}
    output = {"format": "psd", "editable": True}
    first = _evaluate({"sources": [source], "transforms": [crop, rotate], "output": output})
    second = _evaluate({"sources": [source], "transforms": [rotate, crop], "output": output})
    assert first.decision is Decision.ALLOW
    assert first.digest != second.digest
    assert first.manifest["chain"][-1] != second.manifest["chain"][-1]


def test_rejects_invalid_supplied_hash() -> None:
    receipt = _evaluate({
        "sources": [{"id": "a", "sha256": "not-a-hash", "rights": "owned"}],
        "transforms": [],
        "output": {"format": "png", "editable": False},
    })
    assert receipt.decision is Decision.REFUSE
    assert "source_a_sha256_invalid" in receipt.reasons


def test_rejects_duplicate_source_identity() -> None:
    receipt = _evaluate({
        "sources": [
            {"id": "same", "content": "A", "rights": "owned"},
            {"id": "same", "content": "B", "rights": "owned"},
        ],
        "transforms": [],
        "output": {"format": "png", "editable": False},
    })
    assert receipt.decision is Decision.REFUSE
    assert "source_same_duplicate" in receipt.reasons


def test_content_never_leaks_into_manifest() -> None:
    secret_content = "source-bytes-that-must-not-be-embedded"
    receipt = _evaluate({
        "sources": [{"id": "a", "content": secret_content, "rights": "owned"}],
        "transforms": [],
        "output": {"format": "png", "editable": False},
    })
    assert receipt.decision is Decision.ALLOW
    assert secret_content not in str(receipt.manifest)


def test_cc0_is_valid_rights_claim() -> None:
    receipt = _evaluate({
        "sources": [{"id": "public", "content": "A", "rights": "cc0"}],
        "transforms": [],
        "output": {"format": "png", "editable": False},
    })
    assert receipt.decision is Decision.ALLOW
    assert receipt.metrics["rights_verified"] is True
