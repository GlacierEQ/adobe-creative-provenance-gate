# Creative Provenance Gate

Independent GlacierEQ portfolio exhibit aligned to Adobe creative-systems operating themes.

> **Not affiliated.** This repository is not affiliated with, endorsed by, employed by, or deployed at Adobe. It uses no proprietary Adobe systems or data.

## What it does

This repository implements a **deterministic content-addressed provenance engine** for creative exports.

A creative export can be evaluated against:

- source asset SHA-256 identities
- source rights state and derivative permissions
- ordered transformation lineage
- transformation tool and model identity
- transformation cost versus a declared budget
- editable-structure preservation
- terminal-output membership in the lineage graph
- basic brand metadata/tag rules
- authority expiry
- tamper-evident receipt verification

The engine refuses exports when lineage is broken, rights are unknown/restricted, derivatives are prohibited, a generative step omits model identity, costs exceed budget, editability is lost when required, brand constraints drift, the authority window expires, or the declared output is not the terminal lineage product.

## Run it

```bash
python -m pytest -q
python scripts/operate.py
```

`operate.py` constructs two content-addressed source assets, composes them into an editable output, verifies rights and brand constraints, emits a lineage graph and provenance digest, then independently re-verifies the receipt before returning success.

## Core API

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
```

## Mechanism boundary

This project verifies **declared creative provenance and lineage**. It does not render images, call proprietary creative APIs, inspect external licenses, or claim production deployment. Rights claims are inputs that the engine validates for internal consistency; external legal validity still depends on the underlying license evidence.

## Why it exists

The design addresses a recurring systems problem: automation can generate and transform creative assets faster than teams can preserve source identity, transformation history, editability, and authorization. The repository turns that concern into an executable mechanism rather than a policy document.

## Repository surfaces

| Surface | Path |
|---|---|
| Provenance engine | `src/creative_provenance_gate.py` |
| Executable demonstration | `scripts/operate.py` |
| Behavioral tests | `tests/test_creative_provenance_gate.py` |
| Adversarial tests | `tests/test_adversarial.py` |
| CI | `.github/workflows/tests.yml` |

## Verification contract

A successful receipt includes:

- `decision = ALLOW`
- a deterministic receipt `digest`
- a content-addressed `provenance_digest`
- source/transform counts
- verified terminal output
- cost and editability metrics
- an inspectable lineage graph

`verify_receipt(request, receipt)` re-evaluates the request and rejects altered receipt content or digests.
