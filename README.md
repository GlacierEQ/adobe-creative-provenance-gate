# Creative Provenance Engine

Independent GlacierEQ portfolio implementation aligned to public Adobe operating themes. This repository is not affiliated with or endorsed by Adobe.

## What it does

The engine turns a creative workflow into a deterministic, content-addressed provenance receipt. It binds:

- source asset digests
- source rights claims
- ordered transformation steps
- model identity for generative operations
- editability-preservation claims
- export format and profile

It then builds a chained digest across the transformation history so a changed source or changed transform produces a different receipt.

## Real behavior

The engine refuses workflows when, among other things:

- a source has no verifiable digest
- a source rights claim is unknown or unsupported
- a generative transform omits model identity
- an editable output claims to survive a destructive transform
- the input envelope is malformed

Allowed workflows receive a `glaciereq.creative-provenance.v1` manifest and deterministic SHA-256 receipt digest. Receipts can be recomputed and verified to detect mutation.

## Run it

```bash
python scripts/operate.py
```

That executes a built-in end-to-end demo and prints the resulting provenance receipt.

To run your own workflow:

```bash
python scripts/operate.py --input request.json --output receipt.json
```

Input shape:

```json
{
  "subject_id": "campaign-asset-42",
  "budget": 1.0,
  "payload": {
    "sources": [
      {
        "id": "brand-mark",
        "sha256": "<64 hex characters>",
        "rights": "owned",
        "mime": "image/svg+xml"
      }
    ],
    "transforms": [
      {
        "op": "generative_fill",
        "tool": "creative-editor",
        "model": "model-version-1",
        "preserves_editability": true,
        "params": {"prompt_digest": "..."}
      }
    ],
    "output": {
      "format": "psd",
      "editable": true,
      "profile": "display-p3"
    }
  }
}
```

A source may provide `content` instead of `sha256`; the engine hashes it and does not copy the content into the manifest.

## Verify behavior

```bash
python -m pytest -q
```

Tests cover deterministic receipts, mutation detection, rights refusal, generative-model identity, destructive editability conflicts, and malformed input.

## Design point

This is deliberately a small operational engine rather than a framework of promotion gates. The portfolio claim is the mechanism itself: reproducible provenance construction and verification using standard Python.
