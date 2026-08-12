from __future__ import annotations

import json

from creative_provenance_cli import evaluate_mapping, main
from creative_provenance_gate import CreativeProvenanceGate


def valid_request() -> dict:
    gate = CreativeProvenanceGate()
    source = gate.source_claim("logo", b"logo-v1")
    output = b"logo-v1:resized"
    transform = gate.transform_claim(
        "resize",
        [source],
        output,
        tool_id="resizer/1",
        cost=0.1,
    )
    return {
        "subject_id": "creative-cli-test",
        "budget": 1.0,
        "sources": [
            {
                "asset_id": source.asset_id,
                "sha256": source.sha256,
                "rights": "owned",
                "allow_derivatives": True,
                "editable": True,
            }
        ],
        "transforms": [
            {
                "operation": transform.operation,
                "input_sha256": list(transform.input_sha256),
                "output_sha256": transform.output_sha256,
                "tool_id": transform.tool_id,
                "cost": transform.cost,
                "preserves_editability": True,
            }
        ],
        "output_sha256": gate.content_digest(output),
        "requires_editable": True,
    }


def test_evaluate_mapping_returns_verified_receipt() -> None:
    result = evaluate_mapping(valid_request())
    assert result["decision"] == "ALLOW"
    assert result["receipt_verified"] is True
    assert result["lineage"]["terminal_output"] == valid_request()["output_sha256"]


def test_cli_writes_receipt(tmp_path, capsys) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "receipt.json"
    request_path.write_text(json.dumps(valid_request()), encoding="utf-8")

    assert main(["--input", str(request_path), "--output", str(output_path)]) == 0
    stdout = json.loads(capsys.readouterr().out)
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout == persisted
    assert persisted["decision"] == "ALLOW"
    assert persisted["receipt_verified"] is True


def test_cli_refuses_invalid_json(tmp_path, capsys) -> None:
    request_path = tmp_path / "bad.json"
    request_path.write_text("not-json", encoding="utf-8")

    assert main(["--input", str(request_path)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["decision"] == "REFUSE"
    assert output["receipt_verified"] is False
