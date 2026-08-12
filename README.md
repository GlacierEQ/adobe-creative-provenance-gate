# Creative Provenance Gate

A deterministic, content-addressed provenance and lineage verifier for creative assets and exports.

> **Independent portfolio project.** This repository is not affiliated with, endorsed by, employed by, or deployed at Adobe. It uses no proprietary Adobe systems or data.

## Purpose

Creative automation can generate and transform assets faster than teams can preserve source identity, transformation history, editability, rights boundaries, cost, and authorization. This repository turns those requirements into executable software.

A creative export can be evaluated against:

- source asset SHA-256 identities
- source rights state and derivative permissions
- ordered transformation lineage
- transformation tool and model identity
- transformation cost versus a declared budget
- editable-structure preservation
- terminal-output membership in the lineage graph
- brand metadata/tag rules
- authority expiry
- tamper-evident receipt verification

The engine refuses an export when its declared provenance does not survive those checks.

## Install

```bash
python -m pip install -e .
```

The package exposes:

```bash
creative-provenance
```

## Verify a provenance request

`creative-provenance` accepts JSON from a file or stdin. A request contains already-computed content identities and declared transformations; the engine verifies their internal lineage contract rather than pretending to inspect an external license registry.

```json
{
  "subject_id": "campaign-hero-v1",
  "budget": 1.0,
  "sources": [
    {
      "asset_id": "brand-logo",
      "sha256": "<64-hex-source-digest>",
      "rights": "owned",
      "allow_derivatives": true,
      "editable": true,
      "metadata": {"format": "svg"}
    }
  ],
  "transforms": [
    {
      "operation": "resize",
      "input_sha256": ["<64-hex-source-digest>"],
      "output_sha256": "<64-hex-output-digest>",
      "tool_id": "resizer/1",
      "cost": 0.1,
      "preserves_editability": true
    }
  ],
  "output_sha256": "<64-hex-output-digest>",
  "requires_editable": true
}
```

Run it:

```bash
creative-provenance --input request.json --pretty
```

Persist the receipt as well:

```bash
creative-provenance \
  --input request.json \
  --output receipt.json \
  --pretty
```

The command independently re-verifies the receipt before returning success. A refused provenance request, malformed request, or failed receipt verification exits non-zero.

## Python API

```python
from creative_provenance_gate import (
    CreativeProvenanceGate,
    CreativeProvenanceGateRequest,
    RightsStatus,
)

gate = CreativeProvenanceGate(clock=lambda: 1000.0)

logo = gate.source_claim(
    "brand-logo",
    b"vector-logo:v3",
    rights=RightsStatus.OWNED,
)

output = b"composite-output"
step = gate.transform_claim(
    "compose",
    [logo],
    output,
    tool_id="layer-compositor/1.0",
    cost=0.2,
)

request = CreativeProvenanceGateRequest(
    subject_id="hero-v1",
    budget=1.0,
    now=1000.0,
    sources=(logo,),
    transforms=(step,),
    output_sha256=gate.content_digest(output),
)

receipt = gate.evaluate(request)
verified, reason = gate.verify_receipt(request, receipt)
```

## Concrete demonstration

The repository retains a real executable demonstration because it exercises the domain mechanism rather than reflecting over class names:

```bash
python scripts/operate.py
```

It constructs two content-addressed source assets, composes them into an editable output, verifies rights and brand constraints, emits a lineage graph and provenance digest, and re-verifies the receipt.

## Failure behavior

The engine refuses when it detects material provenance problems including:

- unknown or restricted source rights
- prohibited derivatives
- malformed source/input/output digests
- unknown lineage inputs
- a non-noop transform claiming an unchanged digest
- generative operations without model identity
- negative or excessive transform cost
- budget overrun
- lost editability when editability is required
- brand-rule mismatch
- unauthorized affiliation claims
- expired authority
- output outside the lineage graph
- output that is not the terminal transform
- altered receipt content or digest

## Mechanism boundary

This project verifies **declared creative provenance and lineage**. It does not render images, call proprietary creative APIs, inspect external licenses, or claim production deployment. Rights claims are inputs whose internal consistency is checked; external legal validity still depends on the underlying license evidence.

## Verification

```bash
python -m pytest -q
python scripts/operate.py
```

CI additionally installs the package and executes `creative-provenance` against a real content-addressed request.

Behavioral proof surfaces:

- `tests/test_creative_provenance_gate.py`
- `tests/test_adversarial.py`
- `tests/test_cli.py`
- `scripts/operate.py`
- `.github/workflows/tests.yml`

A successful receipt includes a deterministic receipt digest, content-addressed provenance digest, lineage graph, source/transform counts, cost and editability metrics, and terminal output identity.

## Status

**FUNCTIONAL** as a standalone creative provenance verifier and CLI.

It should not be described as externally license-aware or Adobe-integrated unless those integrations are actually implemented and exercised. The active repository no longer carries promotion/excellence machinery as a substitute for those missing external capabilities.
