#!/usr/bin/env python3
"""Tests for the CollectorX package validator."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectorx.investor_wiki import augment_evidence_with_dimensions
from tools.validate_collector_package import validate_package


VALIDATOR = ROOT / "tools" / "validate_collector_package.py"


def sample_event() -> dict:
    return {
        "schema": "collectorx.event.v1",
        "id": "sample:1",
        "collector": "sample",
        "source": "fixture",
        "owner_scope": "personal",
        "kind": "watchlist",
        "time": "2026-07-08T12:00:00+08:00",
        "collected_at": "2026-07-08T12:00:00+08:00",
        "data": {"symbol": "600519", "name": "sample"},
        "raw_ref": {"fixture": True},
        "privacy": {"sensitive": False, "local_only": True, "contains": ["watchlist"]},
        "wiki_targets": ["investor.capability_circle.attention_universe"],
    }


def write_package(root: Path, *, include_evidence: bool = False, bad_privacy: bool = False) -> None:
    (root / "lake" / "sample").mkdir(parents=True)
    event = sample_event()
    if bad_privacy:
        event["privacy"]["sensitive"] = "false"
    (root / "lake" / "sample" / "events.jsonl").write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"schema": "collectorx.sample.manifest.v1", "collector": "sample", "event_count": 1}, ensure_ascii=False),
        encoding="utf-8",
    )
    if include_evidence:
        evidence = {
            "schema": "finclaw.investor_wiki_evidence.v1",
            "generated_at": "2026-07-08T12:00:00+08:00",
            "generated_from": {"collector": "sample", "event_schema": "collectorx.event.v1", "event_count": 1},
            "wiki_write_policy": {
                "collector_writes_wiki_directly": False,
                "raw_json_writes_wiki_directly": False,
                "required_flow": ["collectorx.event.v1", "finclaw.investor_wiki_evidence.v1", "SoulMirror investor-portrait distill/organize"],
            },
            "coverage_summary": {},
        }
        rules = {
            "inv-industry-circle": {
                "support_level": "weak",
                "route_targets": ["investor.capability_circle.attention_universe"],
                "signals": ["Sample watchlist supports attention-universe routing."],
                "gaps": ["Sample fixture is not a production source."],
            }
        }
        augmented = augment_evidence_with_dimensions(evidence, [event], rules)
        (root / "investor_wiki_evidence.v1.json").write_text(json.dumps(augmented, ensure_ascii=False), encoding="utf-8")


def test_valid_event_package_without_evidence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_package(root)
        summary, errors = validate_package(root, collector="sample")
        assert errors == []
        assert summary["event_count"] == 1
        assert summary["evidence_present"] is False


def test_require_evidence_and_cli_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_package(root, include_evidence=True)
        summary, errors = validate_package(root, collector="sample", require_evidence=True)
        assert errors == []
        assert summary["evidence_present"] is True

        result = subprocess.run(
            [sys.executable, str(VALIDATOR), str(root), "--collector", "sample", "--require-evidence", "--json"],
            check=True,
            text=True,
            capture_output=True,
        )
        payload = json.loads(result.stdout)
        assert payload["valid"] is True
        assert payload["event_count"] == 1
        assert payload["evidence_present"] is True


def test_invalid_package_reports_errors() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_package(root, bad_privacy=True)
        summary, errors = validate_package(root, collector="sample", require_evidence=True)
        assert summary["valid"] is False
        assert any("privacy.sensitive must be boolean" in error for error in errors)
        assert any("missing required evidence package" in error for error in errors)


def main() -> None:
    test_valid_event_package_without_evidence()
    test_require_evidence_and_cli_json()
    test_invalid_package_reports_errors()
    print("collector package validator tests passed.")


if __name__ == "__main__":
    main()
