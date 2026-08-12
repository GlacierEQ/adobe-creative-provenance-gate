from __future__ import annotations

from creative_provenance_gate import (
    CreativeProvenanceGate,
    CreativeProvenanceGateRequest,
    Decision,
    RightsStatus,
    SourceAssetClaim,
    TransformClaim,
)


def test_affiliation_claim_fails_closed() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    req = CreativeProvenanceGateRequest(
        subject_id="portfolio",
        payload={"affiliation_claim": "official production system"},
        budget=1.0,
        now=1000.0,
    )
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "unauthorized_affiliation_claim" in receipt.reasons


def test_output_cannot_jump_outside_lineage() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    source = SourceAssetClaim.from_content("source", b"source", rights=RightsStatus.OWNED)
    req = CreativeProvenanceGateRequest(
        subject_id="x",
        budget=1.0,
        now=1000.0,
        sources=(source,),
        output_sha256="f" * 64,
    )
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "output_not_in_lineage" in receipt.reasons


def test_transform_cannot_disguise_non_noop_same_digest() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    source = SourceAssetClaim.from_content("source", b"source", rights=RightsStatus.OWNED)
    t = TransformClaim(
        operation="crop",
        input_sha256=(source.sha256,),
        output_sha256=source.sha256,
        tool_id="cropper/1",
        cost=0.1,
    )
    req = CreativeProvenanceGateRequest(
        subject_id="x",
        budget=1.0,
        now=1000.0,
        sources=(source,),
        transforms=(t,),
        output_sha256=source.sha256,
    )
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "silent_mutation_or_noop:0" in receipt.reasons


def test_malformed_digest_never_crashes_open() -> None:
    mech = CreativeProvenanceGate(clock=lambda: 1000.0)
    source = SourceAssetClaim(
        asset_id="source",
        sha256="not-a-digest",
        rights=RightsStatus.OWNED,
    )
    req = CreativeProvenanceGateRequest(
        subject_id="x",
        budget=1.0,
        now=1000.0,
        sources=(source,),
        output_sha256="not-a-digest",
    )
    receipt = mech.evaluate(req)
    assert receipt.decision is Decision.REFUSE
    assert "source_digest_invalid:source" in receipt.reasons
    assert "output_digest_invalid" in receipt.reasons
