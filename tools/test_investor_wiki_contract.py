#!/usr/bin/env python3
"""Tests for the shared Investor Wiki evidence contract."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectorx.investor_wiki import augment_evidence_with_dimensions, validate_evidence_contract

VALIDATOR = ROOT / "tools" / "validate_investor_wiki_evidence.py"


def sample_event() -> dict:
    return {
        "schema": "collectorx.event.v1",
        "id": "sample:1",
        "collector": "sample",
        "source": "fixture",
        "owner_scope": "personal",
        "kind": "holding",
        "time": "2026-07-08T12:00:00+08:00",
        "collected_at": "2026-07-08T12:00:00+08:00",
        "data": {"subtype": "position"},
        "raw_ref": {"fixture": True},
        "privacy": {"sensitive": True, "local_only": True, "contains": ["portfolio"]},
        "wiki_targets": ["investor.risk_portfolio.current_positions"],
    }


def test_augment_and_validate_dimension_tree() -> None:
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
        "inv-portfolio-preference": {
            "support_level": "strong",
            "route_targets": ["investor.risk_portfolio.current_positions"],
            "signals": ["持仓事实可支撑组合偏好画像。"],
            "gaps": ["仍需用户目标和约束说明。"],
        }
    }
    augmented = augment_evidence_with_dimensions(evidence, [sample_event()], rules)
    assert augmented["coverage_summary"]["dimension_count"] == 7
    assert augmented["coverage_summary"]["subdimension_count"] == 20
    assert augmented["coverage_summary"]["support_level_counts"] == {"none": 19, "strong": 1}
    portfolio = next(
        child
        for dimension in augmented["dimensions"]
        for child in dimension["children"]
        if child["subdimension_id"] == "inv-portfolio-preference"
    )
    assert portfolio["support_level"] == "strong"
    assert portfolio["evidence_count"] == 1
    assert validate_evidence_contract(augmented) == []


def test_validator_cli_rejects_route_only_when_strict() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "investor_wiki_evidence.v1.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "finclaw.investor_wiki_evidence.v1",
                    "generated_from": {"collector": "legacy", "event_schema": "collectorx.event.v1", "event_count": 1},
                    "wiki_write_policy": {
                        "collector_writes_wiki_directly": False,
                        "raw_json_writes_wiki_directly": False,
                        "required_flow": ["collectorx.event.v1", "finclaw.investor_wiki_evidence.v1"],
                    },
                    "coverage_summary": {"route_counts": {"investor.risk_portfolio.current_positions": 1}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        strict = subprocess.run([sys.executable, str(VALIDATOR), str(path)], text=True, capture_output=True)
        assert strict.returncode == 1
        relaxed = subprocess.run([sys.executable, str(VALIDATOR), str(path), "--allow-route-only"], text=True, capture_output=True)
        assert relaxed.returncode == 0


def main() -> None:
    test_augment_and_validate_dimension_tree()
    test_validator_cli_rejects_route_only_when_strict()
    print("investor wiki contract tests passed.")


if __name__ == "__main__":
    main()
