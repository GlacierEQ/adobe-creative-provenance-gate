"""Deterministic creative provenance engine.

This module implements a content-addressed lineage verifier for creative assets.
It does not render media. It verifies that a declared creative export can be
traced to source assets and ordered transformations without silent mutation,
rights violations, budget overruns, editability loss, or brand-rule drift.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _normalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_normalize(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_normalize(v) for v in value)
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_content(content: bytes | str) -> str:
    """Return a SHA-256 content address for bytes or UTF-8 text."""
    raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    return hashlib.sha256(raw).hexdigest()


def _valid_sha256(value: str) -> bool:
    return bool(_SHA256_RE.fullmatch(value or ""))


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REFUSE = "REFUSE"


class RightsStatus(str, Enum):
    OWNED = "owned"
    LICENSED = "licensed"
    PUBLIC_DOMAIN = "public_domain"
    GENERATED = "generated"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SourceAssetClaim:
    asset_id: str
    sha256: str
    rights: RightsStatus | str = RightsStatus.OWNED
    allow_derivatives: bool = True
    editable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_content(
        cls,
        asset_id: str,
        content: bytes | str,
        *,
        rights: RightsStatus | str = RightsStatus.OWNED,
        allow_derivatives: bool = True,
        editable: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> "SourceAssetClaim":
        return cls(
            asset_id=asset_id,
            sha256=hash_content(content),
            rights=rights,
            allow_derivatives=allow_derivatives,
            editable=editable,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True)
class TransformClaim:
    operation: str
    input_sha256: tuple[str, ...]
    output_sha256: str
    tool_id: str
    model_id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    cost: float = 0.0
    preserves_editability: bool = True

    @classmethod
    def from_content(
        cls,
        operation: str,
        inputs: Sequence[SourceAssetClaim | str],
        output_content: bytes | str,
        *,
        tool_id: str,
        model_id: str | None = None,
        params: Mapping[str, Any] | None = None,
        cost: float = 0.0,
        preserves_editability: bool = True,
    ) -> "TransformClaim":
        digests = tuple(i.sha256 if isinstance(i, SourceAssetClaim) else str(i) for i in inputs)
        return cls(
            operation=operation,
            input_sha256=digests,
            output_sha256=hash_content(output_content),
            tool_id=tool_id,
            model_id=model_id,
            params=dict(params or {}),
            cost=float(cost),
            preserves_editability=preserves_editability,
        )


@dataclass(frozen=True)
class CreativeProvenanceGateRequest:
    """A verifiable creative export envelope.

    Existing callers may continue to provide only subject_id/payload/budget.
    Structured provenance fields add real lineage verification.
    """

    subject_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    budget: float = 1.0
    grant_id: str | None = None
    not_after: float | None = None
    now: float | None = None
    sources: tuple[SourceAssetClaim, ...] = ()
    transforms: tuple[TransformClaim, ...] = ()
    output_sha256: str | None = None
    requires_editable: bool = False
    brand_rules: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreativeProvenanceGateReceipt:
    decision: Decision
    reasons: tuple[str, ...]
    digest: str
    metrics: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "digest": self.digest,
            "metrics": _normalize(self.metrics),
            "lineage": _normalize(self.lineage),
        }


class CreativeProvenanceGate:
    """Verify creative lineage and emit a tamper-evident receipt."""

    MIN_BUDGET = 0.0
    MAX_BUDGET = 1_000_000.0
    MAX_TRANSFORMS = 256
    GENERATIVE_OPERATIONS = frozenset(
        {"generate", "text_to_image", "image_to_image", "inpaint", "outpaint", "generative_fill"}
    )
    PERMITTED_RIGHTS = frozenset(
        {
            RightsStatus.OWNED.value,
            RightsStatus.LICENSED.value,
            RightsStatus.PUBLIC_DOMAIN.value,
            RightsStatus.GENERATED.value,
        }
    )

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.time

    @staticmethod
    def content_digest(content: bytes | str) -> str:
        return hash_content(content)

    @staticmethod
    def source_claim(
        asset_id: str,
        content: bytes | str,
        *,
        rights: RightsStatus | str = RightsStatus.OWNED,
        allow_derivatives: bool = True,
        editable: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> SourceAssetClaim:
        return SourceAssetClaim.from_content(
            asset_id,
            content,
            rights=rights,
            allow_derivatives=allow_derivatives,
            editable=editable,
            metadata=metadata,
        )

    @staticmethod
    def transform_claim(
        operation: str,
        inputs: Sequence[SourceAssetClaim | str],
        output_content: bytes | str,
        *,
        tool_id: str,
        model_id: str | None = None,
        params: Mapping[str, Any] | None = None,
        cost: float = 0.0,
        preserves_editability: bool = True,
    ) -> TransformClaim:
        return TransformClaim.from_content(
            operation,
            inputs,
            output_content,
            tool_id=tool_id,
            model_id=model_id,
            params=params,
            cost=cost,
            preserves_editability=preserves_editability,
        )

    def _validate_brand_rules(self, req: CreativeProvenanceGateRequest, reasons: list[str]) -> None:
        rules = req.brand_rules or {}
        tags = {str(x) for x in req.payload.get("tags", []) if str(x)}
        for tag in rules.get("required_tags", []):
            if str(tag) not in tags:
                reasons.append(f"brand_required_tag_missing:{tag}")
        for tag in rules.get("forbidden_tags", []):
            if str(tag) in tags:
                reasons.append(f"brand_forbidden_tag:{tag}")
        for key, expected in dict(rules.get("required_metadata", {})).items():
            if req.payload.get(key) != expected:
                reasons.append(f"brand_metadata_mismatch:{key}")
        if req.payload.get("affiliation_claim") not in (None, False, "", "independent"):
            reasons.append("unauthorized_affiliation_claim")

    def _analyze_lineage(
        self, req: CreativeProvenanceGateRequest, reasons: list[str]
    ) -> tuple[dict[str, Any], float, bool]:
        available: dict[str, dict[str, Any]] = {}
        source_ids: set[str] = set()
        editable = True

        for idx, source in enumerate(req.sources):
            if not source.asset_id.strip():
                reasons.append(f"source_asset_id_missing:{idx}")
            if source.asset_id in source_ids:
                reasons.append(f"source_asset_id_duplicate:{source.asset_id}")
            source_ids.add(source.asset_id)
            if not _valid_sha256(source.sha256):
                reasons.append(f"source_digest_invalid:{source.asset_id or idx}")

            rights = source.rights.value if isinstance(source.rights, RightsStatus) else str(source.rights)
            if rights not in self.PERMITTED_RIGHTS:
                reasons.append(f"source_rights_refused:{source.asset_id or idx}:{rights}")
            available[source.sha256] = {
                "kind": "source",
                "asset_id": source.asset_id,
                "rights": rights,
                "editable": bool(source.editable),
            }
            editable = editable and bool(source.editable)

        if len(req.transforms) > self.MAX_TRANSFORMS:
            reasons.append("transform_limit_exceeded")

        total_cost = 0.0
        edges: list[dict[str, str]] = []
        transform_nodes: list[dict[str, Any]] = []

        for idx, transform in enumerate(req.transforms):
            op = transform.operation.strip().lower()
            if not op:
                reasons.append(f"transform_operation_missing:{idx}")
            if not transform.tool_id.strip():
                reasons.append(f"transform_tool_missing:{idx}")
            if transform.cost < 0:
                reasons.append(f"transform_cost_negative:{idx}")
            total_cost += max(0.0, transform.cost)

            if not transform.input_sha256:
                reasons.append(f"transform_inputs_missing:{idx}")
            for input_digest in transform.input_sha256:
                if not _valid_sha256(input_digest):
                    reasons.append(f"transform_input_digest_invalid:{idx}")
                elif input_digest not in available:
                    reasons.append(f"lineage_input_unknown:{idx}:{input_digest}")

            if not _valid_sha256(transform.output_sha256):
                reasons.append(f"transform_output_digest_invalid:{idx}")
            if transform.output_sha256 in transform.input_sha256 and op not in {"noop", "metadata_only"}:
                reasons.append(f"silent_mutation_or_noop:{idx}")
            if op in self.GENERATIVE_OPERATIONS and not (transform.model_id or "").strip():
                reasons.append(f"generative_model_missing:{idx}")

            if op not in {"noop", "metadata_only"}:
                for source in req.sources:
                    if source.sha256 in transform.input_sha256 and not source.allow_derivatives:
                        reasons.append(f"derivatives_not_allowed:{source.asset_id}")

            editable = editable and bool(transform.preserves_editability)
            node = {
                "kind": "transform",
                "index": idx,
                "operation": op,
                "tool_id": transform.tool_id,
                "model_id": transform.model_id,
                "inputs": list(transform.input_sha256),
                "output": transform.output_sha256,
                "params_digest": _digest(transform.params),
                "cost": transform.cost,
                "preserves_editability": transform.preserves_editability,
            }
            transform_nodes.append(node)
            for parent in transform.input_sha256:
                edges.append({"from": parent, "to": transform.output_sha256})
            available[transform.output_sha256] = node

        if total_cost > req.budget:
            reasons.append("budget_exceeded")

        output_digest = req.output_sha256
        if output_digest is not None:
            if not _valid_sha256(output_digest):
                reasons.append("output_digest_invalid")
            elif output_digest not in available:
                reasons.append("output_not_in_lineage")
            if req.transforms and output_digest != req.transforms[-1].output_sha256:
                reasons.append("output_not_terminal_transform")

        if req.requires_editable and not editable:
            reasons.append("editability_lost")

        source_nodes = [
            {
                "asset_id": s.asset_id,
                "sha256": s.sha256,
                "rights": s.rights.value if isinstance(s.rights, RightsStatus) else str(s.rights),
                "allow_derivatives": s.allow_derivatives,
                "editable": s.editable,
                "metadata_digest": _digest(s.metadata),
            }
            for s in req.sources
        ]
        lineage = {
            "subject_id": req.subject_id,
            "sources": source_nodes,
            "transforms": transform_nodes,
            "edges": edges,
            "terminal_output": output_digest,
        }
        lineage["provenance_digest"] = _digest(lineage)
        return lineage, total_cost, editable

    def evaluate(self, req: CreativeProvenanceGateRequest) -> CreativeProvenanceGateReceipt:
        reasons: list[str] = []
        if not req.subject_id or not str(req.subject_id).strip():
            reasons.append("subject_id_missing")
        if req.budget <= self.MIN_BUDGET:
            reasons.append("budget_non_positive")
        if req.budget > self.MAX_BUDGET:
            reasons.append("budget_limit_exceeded")

        now = self._clock() if req.now is None else float(req.now)
        if req.not_after is not None and now > float(req.not_after):
            reasons.append("grant_expired")
        if req.grant_id is not None and not str(req.grant_id).strip():
            reasons.append("grant_id_blank")

        self._validate_brand_rules(req, reasons)
        lineage, total_cost, editable = self._analyze_lineage(req, reasons)

        provenance_mode = bool(req.sources or req.transforms or req.output_sha256)
        metrics = {
            "verified": not reasons,
            "provenance_mode": provenance_mode,
            "source_count": len(req.sources),
            "transform_count": len(req.transforms),
            "lineage_depth": len(req.transforms),
            "total_cost": round(total_cost, 8),
            "budget": req.budget,
            "editable": editable,
            "payload_digest": _digest(req.payload),
            "provenance_digest": lineage["provenance_digest"],
        }

        decision = Decision.REFUSE if reasons else Decision.ALLOW
        if not reasons:
            reasons = ["provenance_verified" if provenance_mode else "legacy_envelope_verified"]

        receipt_body = {
            "request": req,
            "decision": decision,
            "reasons": reasons,
            "metrics": metrics,
            "lineage": lineage,
        }
        return CreativeProvenanceGateReceipt(
            decision=decision,
            reasons=tuple(reasons),
            digest=_digest(receipt_body),
            metrics=metrics,
            lineage=lineage,
        )

    def verify_receipt(
        self, req: CreativeProvenanceGateRequest, receipt: CreativeProvenanceGateReceipt
    ) -> tuple[bool, str | None]:
        """Re-evaluate a request and verify the receipt has not been altered."""
        expected = self.evaluate(req)
        if expected.digest != receipt.digest:
            return False, "RECEIPT_DIGEST_MISMATCH"
        if expected.as_dict() != receipt.as_dict():
            return False, "RECEIPT_CONTENT_MISMATCH"
        return True, None

    def lineage_graph(self, req: CreativeProvenanceGateRequest) -> dict[str, Any]:
        """Return the normalized lineage graph, raising on a refused request."""
        receipt = self.evaluate(req)
        if receipt.decision is Decision.REFUSE:
            raise ValueError(",".join(receipt.reasons))
        return dict(receipt.lineage)


Mechanism = CreativeProvenanceGate
