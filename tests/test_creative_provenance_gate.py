from __future__ import annotations

from creative_provenance_gate import (
    CreativeProvenanceGate,
    CreativeProvenanceGateReceipt,
    CreativeProvenanceGateRequest,
    Decision,
    RightsStatus,
    SourceAssetClaim,
    TransformClaim,
)


def build_valid_request() -> CreativeProvenanceGateRequest:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    logo = mech.source_claim(
        "brand-logo",
        b"logo:v3",
        rights=RightsStatus.OWNED,
        metadata={"owner": "portfolio"},
    )
    photo = mech.source_claim(
        "hero-photo",
        b"photo:licensed:42",
        rights=RightsStatus.LICENSED,
    )
    composite = b"composite:logo:v3+photo:licensed:42"
    transform = mech.transform_claim(
        "compose",
        [logo, photo],
        composite,
        tool_id="layer-compositor/1",
        params={"layout": "hero"},
        cost=0.25,
        preserves_editability=True,
    )
    return CreativeProvenanceGateRequest(
        subject_id="campaign-hero",
        payload={"tags": ["brand-safe", "editable"], "campaign": "portfolio"},
        budget=1.0,
        grant_id="local-demo",
        not_after=2000.0,
        now=1000.0,
        sources=(logo, photo),
        transforms=(transform,),
        output_sha256=mech.content_digest(composite),
        requires_editable=True,
        brand_rules={
            "required_tags": ["brand-safe"],
            "forbidden_tags": ["unapproved"],
            "required_metadata": {"campaign": "portfolio"},
        },
    )


def test_real_provenance_allow_path() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    req = build_valid_request()
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.ALLOW
    assert receipt.reasons == ("provenance_verified",)
    assert receipt.metrics["verified"] is True
    assert receipt.metrics["source_count"] == 2
    assert receipt.metrics["transform_count"] == 1
    assert receipt.metrics["total_cost"] == 0.25
    assert receipt.lineage["terminal_output"] == req.output_sha256
    assert len(receipt.digest) == 64


def test_content_change_changes_receipt_and_output() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    a = build_valid_request()
    altered_output = b"composite:DIFFERENT"
    t = mech.transform_claim(
        "compose",
        list(a.sources),
        altered_output,
        tool_id="layer-compositor/1",
        params={"layout": "hero"},
        cost=0.25,
    )
    b = CreativeProvenanceGateRequest(
        **{**a.__dict__, "transforms": (t,), "output_sha256": mech.content_digest(altered_output)}
    )
    ra = mech.evaluate(a)
    rb = mech.evaluate(b)
    assert ra.decision is Decision.ALLOW
    assert rb.decision is Decision.ALLOW
    assert ra.digest != rb.digest
    assert ra.metrics["provenance_digest"] != rb.metrics["provenance_digest"]


def test_unknown_lineage_input_refuses() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    req = build_valid_request()
    bad = TransformClaim(
        operation="compose",
        input_sha256=("0" * 64,),
        output_sha256=req.transforms[0].output_sha256,
        tool_id="layer-compositor/1",
        cost=0.1,
    )
    mutated = CreativeProvenanceGateRequest(
        **{**req.__dict__, "transforms": (bad,)}
    )
    receipt = mech.evaluate(mutated)
    assert receipt.decision is Decision.REFUSE
    assert any(r.startswith("lineage_input_unknown") for r in receipt.reasons)


def test_restricted_rights_refuse() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    source = SourceAssetClaim.from_content(
        "unknown-stock",
        b"stock",
        rights=RightsStatus.RESTRICTED,
    )
    req = CreativeProvenanceGateRequest(
        subject_id="x",
        budget=1.0,
        now=1000.0,
        sources=(source,),
        output_sha256=source.sha256,
    )
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert any(r.startswith("source_rights_refused") for r in receipt.reasons)


def test_derivative_rights_refuse() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    source = SourceAssetClaim.from_content(
        "no-derivatives",
        b"licensed",
        rights=RightsStatus.LICENSED,
        allow_derivatives=False,
    )
    t = TransformClaim.from_content(
        "crop",
        [source],
        b"cropped",
        tool_id="cropper/1",
        cost=0.1,
    )
    req = CreativeProvenanceGateRequest(
        subject_id="x",
        budget=1.0,
        now=1000.0,
        sources=(source,),
        transforms=(t,),
        output_sha256=t.output_sha256,
    )
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "derivatives_not_allowed:no-derivatives" in receipt.reasons


def test_generative_transform_requires_model_identity() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    source = SourceAssetClaim.from_content("prompt", b"a mountain", rights=RightsStatus.OWNED)
    t = TransformClaim.from_content(
        "text_to_image",
        [source],
        b"generated-image",
        tool_id="generator/1",
        model_id=None,
        cost=0.1,
    )
    req = CreativeProvenanceGateRequest(
        subject_id="generated",
        budget=1.0,
        now=1000.0,
        sources=(source,),
        transforms=(t,),
        output_sha256=t.output_sha256,
    )
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "generative_model_missing:0" in receipt.reasons


def test_budget_exceeded_refuses() -> None:
    req = build_valid_request()
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    req = CreativeProvenanceGateRequest(**{**req.__dict__, "budget": 0.1})
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "budget_exceeded" in receipt.reasons


def test_expired_authority_refuses() -> None:
    req = build_valid_request()
    mech = CreativeProvenanceGate(clock=lambda: 3000.0)
    req = CreativeProvenanceGateRequest(**{**req.__dict__, "now": 3000.0})
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "grant_expired" in receipt.reasons


def test_editability_loss_refuses_when_required() -> None:
    req = build_valid_request()
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    t = TransformClaim(
        **{**req.transforms[0].__dict__, "preserves_editability": False}
    )
    req = CreativeProvenanceGateRequest(**{**req.__dict__, "transforms": (t,)})
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "editability_lost" in receipt.reasons


def test_brand_rule_violation_refuses() -> None:
    req = build_valid_request()
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    req = CreativeProvenanceGateRequest(
        **{**req.__dict__, "payload": {"tags": ["unapproved"], "campaign": "portfolio"}}
    )
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "brand_required_tag_missing:brand-safe" in receipt.reasons
    assert "brand_forbidden_tag:unapproved" in receipt.reasons


def test_legacy_envelope_stays_compatible_but_is_labeled() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    receipt = mech.evaluate(
        CreativeProvenanceGateRequest(subject_id="legacy", payload={"x": 1}, budget=1.0, now=1000.0)
    )
    assert receipt.decision is Decision.ALLOW
    assert receipt.reasons == ("legacy_envelope_verified",)
    assert receipt.metrics["provenance_mode"] is False


def test_receipt_tamper_detection() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    req = build_valid_request()
    receipt = mech.evaluate(req)
    ok, reason = mech.verify_receipt(req, receipt)
    assert ok is True
    assert reason is None

    tampered = CreativeProvenanceGateReceipt(
        decision=receipt.decision,
        reasons=receipt.reasons,
        digest=receipt.digest,
        metrics={**receipt.metrics, "total_cost": 0.0},
        lineage=receipt.lineage,
    )
    ok, reason = mech.verify_receipt(req, tampered)
    assert ok is False
    assert reason == "RECEIPT_CONTENT_MISMATCH"
