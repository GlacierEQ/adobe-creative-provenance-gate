"""Content-addressed creative provenance engine.

This module binds source assets, rights claims, transform steps, and export
properties into a deterministic provenance receipt. It is intentionally
vendor-neutral and uses only the Python standard library.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_ALLOWED_RIGHTS = {"owned", "licensed", "public_domain", "cc0"}
_GENERATIVE_OPS = {"generate", "generative_fill", "style_transfer", "inpaint", "outpaint"}


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _digest(obj: object) -> str:
    return hashlib.sha256(_canonical(obj)).hexdigest()


def _content_digest(value: Any) -> str:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = _canonical(value)
    return hashlib.sha256(raw).hexdigest()


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REFUSE = "REFUSE"


@dataclass(frozen=True)
class CreativeProvenanceGateRequest:
    """Creative operation to bind into a provenance receipt.

    ``payload`` uses a compact, portable schema::

        {
          "sources": [{"id": "logo", "sha256": "...", "rights": "owned"}],
          "transforms": [{"op": "crop", "tool": "editor", "preserves_editability": true}],
          "output": {"format": "psd", "editable": true}
        }

    A source may provide ``content`` instead of ``sha256``; the content is
    hashed and never copied into the resulting manifest.
    """

    subject_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    budget: float = 1.0
    grant_id: str | None = None
    not_after: float | None = None


@dataclass(frozen=True)
class CreativeProvenanceGateReceipt:
    decision: Decision
    reasons: tuple[str, ...]
    digest: str
    metrics: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "digest": self.digest,
            "metrics": self.metrics,
            "manifest": self.manifest,
        }


class CreativeProvenanceGate:
    """Build and verify deterministic creative provenance receipts."""

    MIN_BUDGET: float = 0.0

    @staticmethod
    def _normalize_source(source: Any, index: int) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(source, dict):
            return None, f"source_{index}_not_object"
        source_id = str(source.get("id", "")).strip()
        if not source_id:
            return None, f"source_{index}_id_missing"

        rights = str(source.get("rights", "unknown")).strip().lower()
        if rights not in _ALLOWED_RIGHTS:
            return None, f"source_{source_id}_rights_unverified"

        supplied_sha = source.get("sha256")
        if supplied_sha is not None:
            supplied_sha = str(supplied_sha).lower()
            if not _SHA256.fullmatch(supplied_sha):
                return None, f"source_{source_id}_sha256_invalid"
            sha256 = supplied_sha
        elif "content" in source:
            sha256 = _content_digest(source["content"])
        else:
            return None, f"source_{source_id}_digest_missing"

        normalized = {
            "id": source_id,
            "sha256": sha256,
            "rights": rights,
            "mime": str(source.get("mime", "application/octet-stream")),
        }
        if source.get("license_id"):
            normalized["license_id"] = str(source["license_id"])
        return normalized, None

    @staticmethod
    def _normalize_transform(step: Any, index: int) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(step, dict):
            return None, f"transform_{index}_not_object"
        op = str(step.get("op", "")).strip().lower()
        tool = str(step.get("tool", "")).strip()
        if not op:
            return None, f"transform_{index}_op_missing"
        if not tool:
            return None, f"transform_{index}_tool_missing"
        model = step.get("model")
        if op in _GENERATIVE_OPS and not str(model or "").strip():
            return None, f"transform_{index}_model_missing"

        normalized: dict[str, Any] = {
            "op": op,
            "tool": tool,
            "preserves_editability": bool(step.get("preserves_editability", True)),
            "params": step.get("params", {}),
        }
        if model:
            normalized["model"] = str(model)
        if step.get("version"):
            normalized["version"] = str(step["version"])
        return normalized, None

    def evaluate(self, req: CreativeProvenanceGateRequest) -> CreativeProvenanceGateReceipt:
        reasons: list[str] = []
        if not str(req.subject_id or "").strip():
            reasons.append("subject_id_missing")
        if req.budget <= self.MIN_BUDGET:
            reasons.append("budget_non_positive")
        if not isinstance(req.payload, dict):
            reasons.append("payload_not_object")

        payload = req.payload if isinstance(req.payload, dict) else {}
        raw_sources = payload.get("sources", [])
        raw_transforms = payload.get("transforms", [])
        raw_output = payload.get("output", {})
        if not isinstance(raw_sources, list) or not raw_sources:
            reasons.append("sources_missing")
        if not isinstance(raw_transforms, list):
            reasons.append("transforms_not_list")
            raw_transforms = []
        if not isinstance(raw_output, dict) or not raw_output.get("format"):
            reasons.append("output_format_missing")
            raw_output = raw_output if isinstance(raw_output, dict) else {}

        sources: list[dict[str, Any]] = []
        if isinstance(raw_sources, list):
            seen_ids: set[str] = set()
            for i, source in enumerate(raw_sources):
                normalized, error = self._normalize_source(source, i)
                if error:
                    reasons.append(error)
                    continue
                assert normalized is not None
                if normalized["id"] in seen_ids:
                    reasons.append(f"source_{normalized['id']}_duplicate")
                    continue
                seen_ids.add(normalized["id"])
                sources.append(normalized)

        transforms: list[dict[str, Any]] = []
        if isinstance(raw_transforms, list):
            for i, step in enumerate(raw_transforms):
                normalized, error = self._normalize_transform(step, i)
                if error:
                    reasons.append(error)
                    continue
                assert normalized is not None
                transforms.append(normalized)

        output = {
            "format": str(raw_output.get("format", "")).lower(),
            "editable": bool(raw_output.get("editable", False)),
        }
        if raw_output.get("profile"):
            output["profile"] = str(raw_output["profile"])
        if output["editable"] and any(not t["preserves_editability"] for t in transforms):
            reasons.append("editable_output_has_destructive_transform")

        ordered_sources = sorted(sources, key=lambda item: item["id"])
        source_root = _digest(ordered_sources) if ordered_sources else _digest([])
        chain: list[str] = [source_root]
        previous = source_root
        for step in transforms:
            previous = _digest({"parent": previous, "transform": step})
            chain.append(previous)

        manifest = {
            "schema": "glaciereq.creative-provenance.v1",
            "subject_id": str(req.subject_id),
            "grant_id": req.grant_id,
            "sources": ordered_sources,
            "transforms": transforms,
            "output": output,
            "source_root": source_root,
            "chain": chain,
        }
        receipt_digest = _digest(manifest)

        decision = Decision.REFUSE if reasons else Decision.ALLOW
        if not reasons:
            reasons = ["provenance_bound"]
        metrics = {
            "source_count": len(ordered_sources),
            "transform_count": len(transforms),
            "chain_depth": len(chain),
            "rights_verified": bool(ordered_sources) and all(s["rights"] in _ALLOWED_RIGHTS for s in ordered_sources),
            "editable_transform_ratio": (
                sum(1 for t in transforms if t["preserves_editability"]) / len(transforms)
                if transforms else 1.0
            ),
            "budget": req.budget,
        }
        return CreativeProvenanceGateReceipt(
            decision=decision,
            reasons=tuple(reasons),
            digest=receipt_digest,
            metrics=metrics,
            manifest=manifest,
        )

    def verify(self, req: CreativeProvenanceGateRequest, receipt: CreativeProvenanceGateReceipt) -> dict[str, Any]:
        """Recompute a receipt and report whether it is intact and current."""
        recomputed = self.evaluate(req)
        matches = (
            recomputed.digest == receipt.digest
            and recomputed.decision is receipt.decision
            and recomputed.manifest == receipt.manifest
        )
        return {
            "ok": matches,
            "digest": recomputed.digest,
            "expected_digest": receipt.digest,
            "decision": recomputed.decision.value,
        }


def verify_manifest(req: CreativeProvenanceGateRequest, receipt: CreativeProvenanceGateReceipt) -> dict[str, Any]:
    return CreativeProvenanceGate().verify(req, receipt)


Mechanism = CreativeProvenanceGate
