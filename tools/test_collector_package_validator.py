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
from tools.validate_collector_package import DATA_QUALITY_GAP_TARGET, validate_package


VALIDATOR = ROOT / "tools" / "validate_collector_package.py"
BUSINESS_TARGET = "investor.capability_circle.attention_universe"


def sample_event(
    *,
    collector: str = "sample",
    event_id: str | None = None,
    kind: str = "watchlist",
    data: dict | None = None,
    wiki_targets: list[str] | None = None,
) -> dict:
    return {
        "schema": "collectorx.event.v1",
        "id": event_id or f"{collector}:1",
        "collector": collector,
        "source": "fixture",
        "owner_scope": "personal",
        "kind": kind,
        "time": "2026-07-08T12:00:00+08:00",
        "collected_at": "2026-07-08T12:00:00+08:00",
        "data": data or {"symbol": "600519", "name": "sample"},
        "raw_ref": {"fixture": True},
        "privacy": {"sensitive": False, "local_only": True, "contains": ["watchlist"]},
        "wiki_targets": wiki_targets or [BUSINESS_TARGET],
    }


def sample_gap_event(
    *,
    collector: str = "sample",
    event_id: str | None = None,
    wiki_targets: list[str] | None = None,
) -> dict:
    event = sample_event(
        collector=collector,
        event_id=event_id or f"{collector}:gap",
        kind="profile",
        data={
            "subtype": "collector_gap",
            "action_type": "collector_gap",
            "gap": "authorized_input_missing",
            "profile_type": f"{collector}_collection_gap",
            "message": "fixture gap",
        },
        wiki_targets=wiki_targets or [DATA_QUALITY_GAP_TARGET],
    )
    event["privacy"]["contains"] = ["collection_gap"]
    return event


def write_package(
    root: Path,
    *,
    collector: str = "sample",
    events: list[dict] | None = None,
    manifest: dict | None = None,
    evidence: dict | None = None,
    include_evidence: bool = False,
    bad_privacy: bool = False,
) -> None:
    (root / "lake" / collector).mkdir(parents=True)
    package_events = events or [sample_event(collector=collector)]
    if bad_privacy:
        package_events[0]["privacy"]["sensitive"] = "false"
    (root / "lake" / collector / "events.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in package_events),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(
            manifest or {"schema": "collectorx.sample.manifest.v1", "collector": collector, "event_count": len(package_events)},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    if evidence is not None or include_evidence:
        evidence_package = evidence or build_evidence(package_events, collector=collector)
        (root / "investor_wiki_evidence.v1.json").write_text(json.dumps(evidence_package, ensure_ascii=False), encoding="utf-8")


def build_evidence(
    events: list[dict],
    *,
    collector: str = "sample",
    event_count: int | None = None,
    raw_event_count: int | None = None,
    gap_event_count: int | None = None,
) -> dict:
    usable_events = [event for event in events if (event.get("data") or {}).get("subtype") != "collector_gap"]
    actual_gap_event_count = len(events) - len(usable_events)
    evidence = {
        "schema": "finclaw.investor_wiki_evidence.v1",
        "generated_at": "2026-07-08T12:00:00+08:00",
        "generated_from": {
            "collector": collector,
            "event_schema": "collectorx.event.v1",
            "event_count": len(usable_events) if event_count is None else event_count,
            "raw_event_count": len(events) if raw_event_count is None else raw_event_count,
            "gap_event_count": actual_gap_event_count if gap_event_count is None else gap_event_count,
        },
        "wiki_write_policy": {
            "collector_writes_wiki_directly": False,
            "raw_json_writes_wiki_directly": False,
            "required_flow": [
                "collectorx.event.v1",
                "finclaw.investor_wiki_evidence.v1",
                "SoulMirror investor-portrait distill/organize",
            ],
        },
        "coverage_summary": {},
    }
    rules = {
        "inv-industry-circle": {
            "support_level": "weak",
            "route_targets": [BUSINESS_TARGET],
            "signals": ["Sample watchlist supports attention-universe routing."],
            "gaps": ["Sample fixture is not a production source."],
        }
    }
    return augment_evidence_with_dimensions(evidence, events, rules)


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


def test_business_readiness_counts_are_valid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        collector = "hk-us-brokerage"
        events = [sample_event(collector=collector, kind="trade", data={"subtype": "broker_trade_execution"})]
        manifest = {
            "schema": "collectorx.hk_us_brokerage.manifest.v1",
            "collector": collector,
            "event_count": 1,
            "usable_event_count": 1,
            "brokerage_event_count": 1,
            "gap_event_count": 0,
            "collection_readiness": {
                "status": "events_collected",
                "usable_event_count": 1,
                "brokerage_event_count": 1,
                "gap_event_count": 0,
                "can_enter_finclaw": True,
                "can_enter_hk_us_brokerage_lake": True,
                "can_enter_data_quality_lake": False,
                "can_feed_investor_wiki_evidence": True,
            },
        }
        write_package(root, collector=collector, events=events, manifest=manifest, include_evidence=True)
        summary, errors = validate_package(root, collector=collector, require_evidence=True)
        assert errors == []
        assert summary["usable_event_count"] == 1
        assert summary["gap_event_count"] == 0


def test_gap_only_readiness_counts_and_evidence_are_valid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        collector = "hk-us-brokerage"
        events = [sample_gap_event(collector=collector)]
        manifest = {
            "schema": "collectorx.hk_us_brokerage.manifest.v1",
            "collector": collector,
            "event_count": 1,
            "usable_event_count": 0,
            "brokerage_event_count": 0,
            "gap_event_count": 1,
            "collection_readiness": {
                "status": "scope_policy_filtered_all",
                "usable_event_count": 0,
                "brokerage_event_count": 0,
                "gap_event_count": 1,
                "can_enter_finclaw": False,
                "can_enter_hk_us_brokerage_lake": False,
                "can_enter_data_quality_lake": True,
                "can_feed_investor_wiki_evidence": False,
            },
        }
        write_package(root, collector=collector, events=events, manifest=manifest, include_evidence=True)
        summary, errors = validate_package(root, collector=collector, require_evidence=True)
        assert errors == []
        assert summary["gap_only"] is True


def test_route_aware_data_quality_package_is_valid_for_collector() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        collector = "filesystem"
        events = [sample_gap_event(collector=collector)]
        (root / "lake" / "data_quality").mkdir(parents=True)
        (root / "lake" / "data_quality" / "events.jsonl").write_text(
            json.dumps(events[0], ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        manifest = {
            "schema": "collectorx.filesystem_collect.manifest.v1",
            "collector": collector,
            "event_count": 1,
            "usable_event_count": 0,
            "filesystem_event_count": 0,
            "file_event_count": 0,
            "gap_event_count": 1,
            "collection_readiness": {
                "status": "no_matching_files",
                "usable_event_count": 0,
                "filesystem_event_count": 0,
                "file_event_count": 0,
                "gap_event_count": 1,
                "can_enter_finclaw": False,
                "can_enter_filesystem_lake": False,
                "can_enter_data_quality_lake": True,
                "can_feed_investor_wiki_directly": False,
            },
        }
        (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        summary, errors = validate_package(root, collector=collector)
        assert errors == []
        assert summary["event_file_count"] == 1
        assert summary["gap_only"] is True


def test_collector_specific_primary_counts_are_validated() -> None:
    cases = [
        ("filesystem", "filesystem_event_count"),
        ("feishu", "feishu_event_count"),
        ("wechat-favorites", "wechat_favorite_event_count"),
    ]
    for collector, count_key in cases:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = [sample_event(collector=collector)]
            manifest = {
                "schema": f"collectorx.{collector.replace('-', '_')}.manifest.v1",
                "collector": collector,
                "event_count": 1,
                "usable_event_count": 1,
                count_key: 0,
                "gap_event_count": 0,
            }
            write_package(root, collector=collector, events=events, manifest=manifest)
            _summary, errors = validate_package(root, collector=collector)
            assert any(
                f"{count_key} 0 must match non-gap event count 1" in error for error in errors
            ), collector


def test_known_collector_manifest_requires_primary_count() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        collector = "research-documents"
        events = [sample_event(collector=collector, kind="file")]
        manifest = {
            "schema": "collectorx.investor_source_collect.manifest.v1",
            "collector": collector,
            "event_count": 1,
            "usable_event_count": 1,
            "gap_event_count": 0,
        }
        write_package(root, collector=collector, events=events, manifest=manifest)
        _summary, errors = validate_package(root, collector=collector)
        assert any(
            "research_document_event_count is required for collector research-documents" in error
            for error in errors
        )


def test_gap_event_must_route_to_data_quality_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        events = [sample_gap_event(wiki_targets=[BUSINESS_TARGET])]
        manifest = {
            "schema": "collectorx.sample.manifest.v1",
            "collector": "sample",
            "event_count": 1,
            "usable_event_count": 0,
            "gap_event_count": 1,
            "collection_readiness": {
                "status": "needs_input",
                "usable_event_count": 0,
                "gap_event_count": 1,
                "can_enter_finclaw": False,
                "can_enter_sample_lake": False,
                "can_enter_data_quality_lake": True,
                "can_feed_investor_wiki_evidence": False,
            },
        }
        write_package(root, events=events, manifest=manifest)
        _summary, errors = validate_package(root, collector="sample")
        assert any("must route only to collectorx.data_quality.collection_gaps" in error for error in errors)


def test_manifest_counts_must_match_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        collector = "hk-us-brokerage"
        events = [sample_event(collector=collector, kind="trade", data={"subtype": "broker_trade_execution"})]
        manifest = {
            "schema": "collectorx.hk_us_brokerage.manifest.v1",
            "collector": collector,
            "event_count": 1,
            "usable_event_count": 2,
            "brokerage_event_count": 3,
            "gap_event_count": 0,
        }
        write_package(root, collector=collector, events=events, manifest=manifest)
        _summary, errors = validate_package(root, collector=collector)
        assert any("usable_event_count 2 does not match non-gap event count 1" in error for error in errors)
        assert any("brokerage_event_count 3 cannot exceed usable_event_count 1" in error for error in errors)


def test_gap_only_readiness_cannot_claim_business_or_wiki() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        events = [sample_gap_event()]
        manifest = {
            "schema": "collectorx.sample.manifest.v1",
            "collector": "sample",
            "event_count": 1,
            "usable_event_count": 0,
            "gap_event_count": 1,
            "collection_readiness": {
                "status": "needs_input",
                "usable_event_count": 0,
                "gap_event_count": 1,
                "can_enter_finclaw": True,
                "can_enter_sample_lake": True,
                "can_enter_data_quality_lake": True,
                "can_feed_investor_wiki_evidence": True,
            },
        }
        write_package(root, events=events, manifest=manifest)
        _summary, errors = validate_package(root, collector="sample")
        assert any("can_enter_finclaw must be false for a gap-only package" in error for error in errors)
        assert any("can_enter_sample_lake must be false for a gap-only package" in error for error in errors)
        assert any("can_feed_investor_wiki_evidence must be false for a gap-only package" in error for error in errors)


def test_social_activity_cannot_feed_investor_wiki_directly() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        collector = "social-activity"
        events = [sample_event(collector=collector, kind="note", data={"action_type": "favorite"})]
        manifest = {
            "schema": "collectorx.social_activity.manifest.v1",
            "collector": collector,
            "event_count": 1,
            "usable_event_count": 1,
            "social_activity_event_count": 1,
            "gap_event_count": 0,
            "collection_readiness": {
                "status": "events_collected",
                "usable_event_count": 1,
                "social_activity_event_count": 1,
                "gap_event_count": 0,
                "can_enter_finclaw": True,
                "can_enter_social_activity_lake": True,
                "can_enter_data_quality_lake": False,
                "can_feed_social_investment_lens": True,
                "can_feed_investor_wiki_directly": True,
            },
        }
        write_package(root, collector=collector, events=events, manifest=manifest)
        _summary, errors = validate_package(root, collector=collector)
        assert any("can_feed_investor_wiki_directly must be false for social-activity" in error for error in errors)


def test_gap_only_social_activity_cannot_feed_lens() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        collector = "social-activity"
        events = [sample_gap_event(collector=collector)]
        manifest = {
            "schema": "collectorx.social_activity.manifest.v1",
            "collector": collector,
            "event_count": 1,
            "usable_event_count": 0,
            "social_activity_event_count": 0,
            "gap_event_count": 1,
            "collection_readiness": {
                "status": "scope_policy_filtered_all",
                "usable_event_count": 0,
                "social_activity_event_count": 0,
                "gap_event_count": 1,
                "can_enter_finclaw": False,
                "can_enter_social_activity_lake": False,
                "can_enter_data_quality_lake": True,
                "can_feed_social_investment_lens": True,
                "can_feed_investor_wiki_directly": False,
            },
        }
        write_package(root, collector=collector, events=events, manifest=manifest)
        _summary, errors = validate_package(root, collector=collector)
        assert any("can_feed_social_investment_lens must be false" in error for error in errors)


def test_evidence_cannot_count_gap_events_as_facts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        events = [sample_gap_event()]
        manifest = {
            "schema": "collectorx.sample.manifest.v1",
            "collector": "sample",
            "event_count": 1,
            "usable_event_count": 0,
            "gap_event_count": 1,
            "collection_readiness": {
                "status": "needs_input",
                "usable_event_count": 0,
                "gap_event_count": 1,
                "can_enter_finclaw": False,
                "can_enter_sample_lake": False,
                "can_enter_data_quality_lake": True,
                "can_feed_investor_wiki_evidence": False,
            },
        }
        evidence = build_evidence(events, event_count=1, gap_event_count=0)
        write_package(root, events=events, manifest=manifest, evidence=evidence)
        _summary, errors = validate_package(root, collector="sample", require_evidence=True)
        assert any("generated_from.event_count 1 does not match non-gap event count 0" in error for error in errors)
        assert any("generated_from.gap_event_count 0 does not match gap event count 1" in error for error in errors)


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
    test_business_readiness_counts_are_valid()
    test_gap_only_readiness_counts_and_evidence_are_valid()
    test_route_aware_data_quality_package_is_valid_for_collector()
    test_collector_specific_primary_counts_are_validated()
    test_known_collector_manifest_requires_primary_count()
    test_gap_event_must_route_to_data_quality_only()
    test_manifest_counts_must_match_events()
    test_gap_only_readiness_cannot_claim_business_or_wiki()
    test_social_activity_cannot_feed_investor_wiki_directly()
    test_gap_only_social_activity_cannot_feed_lens()
    test_evidence_cannot_count_gap_events_as_facts()
    test_invalid_package_reports_errors()
    print("collector package validator tests passed.")


if __name__ == "__main__":
    main()
