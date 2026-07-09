#!/usr/bin/env python3
"""Tests for xueqiu-investor-activity."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
SCRIPT = ROOT / "scripts" / "xueqiu_activity.py"
PACKAGE_VALIDATOR = REPO_ROOT / "tools" / "validate_collector_package.py"
XUEQIU_ACTIVITY_FIXTURE = REPO_ROOT / "examples" / "fixtures" / "xueqiu-investor-activity" / "activity_export.json"


def read_events(out: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def assert_package_valid(out: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE_VALIDATOR),
            str(out),
            "--collector",
            "xueqiu-investor-activity",
            "--require-evidence",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def assert_evidence_generated_from(
    out: Path,
    *,
    raw_event_count: int,
    usable_event_count: int,
    gap_event_count: int,
) -> dict:
    evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
    generated_from = evidence["generated_from"]
    assert generated_from["event_count"] == usable_event_count
    assert generated_from["raw_event_count"] == raw_event_count
    assert generated_from["gap_event_count"] == gap_event_count
    assert generated_from["event_count"] + generated_from["gap_event_count"] == generated_from["raw_event_count"]
    assert "collectorx.data_quality.collection_gaps" not in evidence["coverage_summary"]["route_counts"]
    if usable_event_count == 0:
        assert evidence["coverage_summary"]["route_counts"] == {}
        assert all(
            child["evidence_count"] == 0
            for dimension in evidence["dimensions"]
            for child in dimension["children"]
        )
    return evidence


def chromium_time(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    from datetime import datetime, timezone

    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    value = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    return int((value - epoch).total_seconds() * 1_000_000)


def safari_time(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> float:
    from datetime import datetime, timezone

    epoch = datetime(2001, 1, 1, tzinfo=timezone.utc)
    value = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    return (value - epoch).total_seconds()


def write_chromium_history(path: Path, rows: list[tuple[int, str, str, int, int, int, int]]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE urls (
              id INTEGER PRIMARY KEY,
              url TEXT,
              title TEXT,
              visit_count INTEGER,
              typed_count INTEGER
            );
            CREATE TABLE visits (
              id INTEGER PRIMARY KEY,
              url INTEGER,
              visit_time INTEGER,
              transition INTEGER
            );
            """
        )
        conn.executemany(
            "INSERT INTO urls (id, url, title, visit_count, typed_count) VALUES (?, ?, ?, ?, ?)",
            [(row[0], row[1], row[2], row[3], row[4]) for row in rows],
        )
        conn.executemany(
            "INSERT INTO visits (id, url, visit_time, transition) VALUES (?, ?, ?, ?)",
            [(row[5], row[0], row[6], row[7]) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


def write_safari_history(path: Path, rows: list[tuple[int, str, str, int, int, float]]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE history_items (
              id INTEGER PRIMARY KEY,
              url TEXT,
              title TEXT,
              visit_count INTEGER
            );
            CREATE TABLE history_visits (
              id INTEGER PRIMARY KEY,
              history_item INTEGER,
              visit_time REAL
            );
            """
        )
        conn.executemany(
            "INSERT INTO history_items (id, url, title, visit_count) VALUES (?, ?, ?, ?)",
            [(row[0], row[1], row[2], row[3]) for row in rows],
        )
        conn.executemany(
            "INSERT INTO history_visits (id, history_item, visit_time) VALUES (?, ?, ?)",
            [(row[4], row[0], row[5]) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


def test_collect_watchlist_csv() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "watchlist.csv"
        out = root / "out"
        csv_path.write_text("type,code,name,group,note\nwatchlist,600519,贵州茅台,白酒,长期观察\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(csv_path), "--out-dir", str(out), "--collected-at", "2026-07-07T15:00:00+08:00"],
            check=True,
            text=True,
            capture_output=True,
        )
        assert_package_valid(out)
        event = read_events(out)[0]
        assert event["schema"] == "collectorx.event.v1"
        assert event["kind"] == "watchlist"
        assert event["data"]["symbol"] == "SH600519"
        assert event["data"]["symbols"] == ["SH600519"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["usable_event_count"] == 1
        assert manifest["activity_event_count"] == 1
        assert manifest["gap_event_count"] == 0
        assert manifest["collection_readiness"]["can_enter_xueqiu_activity_lake"] is True
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is False
        assert manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is True
        assert manifest["collection_readiness"]["usable_event_count"] == 1
        proof = manifest["activity_boundary_proof"]
        assert proof["can_enter_xueqiu_activity_lake"] is True
        assert proof["can_enter_data_quality_lake"] is False
        assert proof["can_feed_investor_wiki_evidence"] is True
        evidence = assert_evidence_generated_from(
            out,
            raw_event_count=manifest["event_count"],
            usable_event_count=manifest["usable_event_count"],
            gap_event_count=manifest["gap_event_count"],
        )
        assert evidence["coverage_summary"]["xueqiu_is_strong_trade_source"] is False
        assert evidence["coverage_summary"]["dimension_count"] == 7
        assert evidence["coverage_summary"]["subdimension_count"] == 20
        industry_circle = next(
            child
            for dimension in evidence["dimensions"]
            for child in dimension["children"]
            if child["subdimension_id"] == "inv-industry-circle"
        )
        assert industry_circle["support_level"] == "medium"
        assert industry_circle["evidence_count"] == 1


def test_collect_posts_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "activities.json"
        out = root / "out"
        json_path.write_text(
            json.dumps(
                [
                    {"type": "post", "title": "复盘", "text": "今天减仓新能源，原因是估值和成交量。", "created_at": "2026-07-07T10:00:00+08:00"},
                    {"type": "follow_user", "screen_name": "某研究员", "url": "https://xueqiu.com/u/1"},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run([sys.executable, str(SCRIPT), "collect", "--input", str(json_path), "--out-dir", str(out)], check=True, text=True, capture_output=True)
        assert_package_valid(out)
        events = read_events(out)
        assert [event["kind"] for event in events] == ["note", "profile"]


def test_collects_fixed_offline_fixture_with_evidence_boundary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(XUEQIU_ACTIVITY_FIXTURE),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-09T11:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        assert_package_valid(out)
        events = read_events(out)
        assert len(events) == 5
        assert [event["data"]["activity_type"] for event in events] == [
            "watchlist",
            "post",
            "favorite",
            "follow_user",
            "portfolio_activity",
        ]
        assert {event["kind"] for event in events} == {"holding", "note", "profile", "watchlist"}
        assert all(event["data"]["broker_confirmed_trade"] is False for event in events)
        assert all("collectorx.data_quality.collection_gaps" not in event["wiki_targets"] for event in events)
        serialized_events = json.dumps(events, ensure_ascii=False)
        assert "SHOULD_NOT_LEAK" not in serialized_events
        assert "cookie" not in serialized_events
        assert "authorization" not in serialized_events
        assert "SH600519" in serialized_events

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 5
        assert manifest["usable_event_count"] == 5
        assert manifest["activity_event_count"] == 5
        assert manifest["gap_event_count"] == 0
        assert manifest["activity_counts"] == {
            "favorite": 1,
            "follow_user": 1,
            "portfolio_activity": 1,
            "post": 1,
            "watchlist": 1,
        }
        assert manifest["collection_readiness"]["can_enter_xueqiu_activity_lake"] is True
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is False
        assert manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is True
        assert manifest["collection_readiness"]["can_claim_broker_trade_collection"] is False
        proof = manifest["activity_boundary_proof"]
        assert proof["overall_proof_level"] == "medium_partial_activity_boundary"
        assert proof["complete_xueqiu_activity_boundary_claimed"] is False
        assert proof["xueqiu_is_broker_trade_source"] is False
        assert proof["missing_expected_activity_types"] == ["follow_portfolio", "comment", "saved_page"]
        assert proof["missing_global_requirements"] == ["expected_activity_surface_coverage", "validated_pagination"]
        assert proof["pagination_completeness"]["completeness_level"] == "pagination_markers_observed_not_validated"
        assert manifest["collection_audit"]["real_account_adapter_used"] is False

        evidence = assert_evidence_generated_from(
            out,
            raw_event_count=manifest["event_count"],
            usable_event_count=manifest["usable_event_count"],
            gap_event_count=manifest["gap_event_count"],
        )
        assert evidence["coverage_summary"]["xueqiu_is_strong_trade_source"] is False
        assert evidence["coverage_summary"]["activity_boundary_proof"]["complete_xueqiu_activity_boundary_claimed"] is False
        assert evidence["coverage_summary"]["dimension_count"] == 7
        assert evidence["coverage_summary"]["subdimension_count"] == 20


def test_activity_scope_policy_filters_authorized_records() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "activities.json"
        out = root / "out"
        json_path.write_text(
            json.dumps(
                [
                    {
                        "type": "post",
                        "symbol": "600519",
                        "screen_name": "价值研究员",
                        "text": "白酒复盘，继续观察赔率。",
                        "url": "https://xueqiu.com/1/1",
                    },
                    {
                        "type": "post",
                        "symbol": "688981",
                        "screen_name": "价值研究员",
                        "text": "半导体复盘。",
                        "url": "https://xueqiu.com/1/2",
                    },
                    {
                        "type": "post",
                        "symbol": "600519",
                        "screen_name": "价值研究员",
                        "text": "私人备忘。",
                        "url": "https://xueqiu.com/1/3",
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(json_path),
                "--out-dir",
                str(out),
                "--allow-activity",
                "post",
                "--allow-domain",
                "xueqiu.com",
                "--allow-symbol",
                "SH600519",
                "--allow-author",
                "价值",
                "--allow-keyword",
                "白酒",
                "--deny-keyword",
                "私人",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        assert events[0]["data"]["symbol"] == "SH600519"
        assert events[0]["data"]["symbols"] == ["SH600519"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["collection_audit"]
        assert audit["xueqiu_activity_scope_policy"]["configured"] is True
        assert audit["scope_policy_candidate_event_count"] == 3
        assert audit["scope_policy_retained_event_count"] == 1
        assert audit["scope_policy_filtered_event_count"] == 2
        assert audit["scope_policy_filter_reason_counts"] == {
            "allow_keyword_mismatch": 2,
            "allow_symbol_mismatch": 1,
            "deny_keyword": 1,
        }
        proof = manifest["activity_boundary_proof"]
        assert proof["authorization_scope_boundary"]["policy_configured"] is True
        assert proof["authorization_scope_boundary"]["retained_event_count"] == 1


def test_activity_scope_policy_filtered_all_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "activities.json"
        out = root / "out"
        json_path.write_text(
            json.dumps([{"type": "post", "text": "普通复盘", "url": "https://xueqiu.com/1/1"}], ensure_ascii=False),
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(json_path),
                "--out-dir",
                str(out),
                "--allow-activity",
                "comment",
                "--collected-at",
                "2026-07-08T12:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 1
        assert_package_valid(out)
        gap = events[0]
        assert gap["kind"] == "profile"
        assert gap["time"] == "2026-07-08T12:00:00+08:00"
        assert gap["collected_at"] == "2026-07-08T12:00:00+08:00"
        assert gap["data"]["activity_type"] == "collector_gap"
        assert gap["data"]["gap"] == "xueqiu_scope_policy_filtered_all"
        assert gap["data"]["status"] == "scope_policy_filtered_all"
        assert gap["data"]["profile_type"] == "xueqiu_scope_policy_filtered_all"
        assert gap["data"]["candidate_event_count"] == 1
        assert gap["data"]["retained_event_count"] == 0
        assert gap["data"]["filtered_event_count"] == 1
        assert gap["data"]["filter_reason_counts"] == {"allow_activity_mismatch": 1}
        assert gap["data"]["broker_trade_fact_claimed"] is False
        assert gap["data"]["holding_fact_claimed"] is False
        assert gap["data"]["order_or_fund_flow_claimed"] is False
        assert gap["wiki_targets"] == ["collectorx.data_quality.collection_gaps"]
        assert gap["raw_ref"] == {
            "preflight": True,
            "reason": "xueqiu_scope_policy_filtered_all",
            "scope_policy_enabled": True,
        }
        assert str(json_path) not in json.dumps(gap, ensure_ascii=False)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["usable_event_count"] == 0
        assert manifest["activity_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["kind_counts"] == {"profile": 1}
        assert manifest["collection_readiness"]["status"] == "scope_policy_filtered_all"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["collection_readiness"]["can_enter_xueqiu_activity_lake"] is False
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is True
        assert manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is False
        assert manifest["collection_readiness"]["usable_event_count"] == 0
        assert manifest["collection_readiness"]["activity_boundary_scope"] == "scope_policy_excluded_all"
        assert manifest["collection_audit"]["xueqiu_activity_scope_policy_filtered_all"] is True
        assert manifest["activity_boundary_proof"]["overall_proof_level"] == "scope_policy_filtered_all"
        assert manifest["activity_boundary_proof"]["authorization_scope_boundary"]["filtered_all"] is True
        assert manifest["activity_boundary_proof"]["can_enter_data_quality_lake"] is True
        assert_evidence_generated_from(out, raw_event_count=1, usable_event_count=0, gap_event_count=1)


def test_activity_gap_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T12:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 1
        assert_package_valid(out)
        assert events[0]["kind"] == "profile"
        assert events[0]["time"] == "2026-07-08T12:00:00+08:00"
        assert events[0]["data"]["activity_type"] == "collector_gap"
        assert events[0]["data"]["gap"] == "xueqiu_authorized_input_missing"
        assert events[0]["data"]["status"] == "needs_xueqiu_authorized_input"
        assert events[0]["data"]["candidate_event_count"] == 0
        assert events[0]["data"]["retained_event_count"] == 0
        assert events[0]["data"]["filtered_event_count"] == 0
        assert events[0]["data"]["broker_trade_fact_claimed"] is False
        assert events[0]["wiki_targets"] == ["collectorx.data_quality.collection_gaps"]
        assert events[0]["raw_ref"] == {
            "preflight": True,
            "reason": "xueqiu_authorized_input_missing",
            "scope_policy_enabled": False,
        }
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["usable_event_count"] == 0
        assert manifest["activity_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["kind_counts"] == {"profile": 1}
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["collection_readiness"]["can_enter_xueqiu_activity_lake"] is False
        assert manifest["collection_readiness"]["can_enter_data_quality_lake"] is True
        assert manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is False
        assert_evidence_generated_from(out, raw_event_count=1, usable_event_count=0, gap_event_count=1)


def test_collects_nested_xueqiu_api_shapes_and_sanitizes_secrets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "xueqiu-api.json"
        out = root / "out"
        json_path.write_text(
            json.dumps(
                {
                    "data": {
                        "items": [
                            {
                                "type": "status",
                                "id": 1001,
                                "max_id": 1001,
                                "text": "继续跟踪 $贵州茅台(SH600519)$，估值进入可研究区间。",
                                "created_at": "2026-07-08T09:30:00+08:00",
                                "user": {"id": 42, "screen_name": "价值研究员"},
                                "cookie": "must-not-leak",
                            },
                            {
                                "type": "portfolio",
                                "cube_symbol": "ZH123456",
                                "cube_name": "低波红利组合",
                                "rebalancing_histories": [
                                    {"stock_symbol": "600519", "stock_name": "贵州茅台", "prev_weight": "8", "target_weight": "10"}
                                ],
                            },
                            {
                                "type": "favorite",
                                "title": "白酒行业深度",
                                "url": "https://xueqiu.com/123/456",
                                "token": "must-not-leak",
                            },
                        ]
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(json_path), "--out-dir", str(out), "--collected-at", "2026-07-08T10:00:00+08:00"],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [event["data"]["activity_type"] for event in events] == ["post", "portfolio_activity", "favorite"]
        assert events[0]["data"]["symbols"] == ["SH600519"]
        assert events[0]["data"]["author"] == "价值研究员"
        assert events[1]["data"]["portfolio_changes"][0]["symbol"] == "SH600519"
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        assert "cookie" not in events[0]["data"]["raw"]
        assert "token" not in events[2]["data"]["raw"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["activity_counts"] == {"favorite": 1, "portfolio_activity": 1, "post": 1}
        assert manifest["collection_readiness"]["can_claim_complete_xueqiu_activity_boundary"] is False
        assert manifest["collection_audit"]["pagination_marker_count"] == 1
        assert manifest["collection_audit"]["pagination_marker_field_counts"]["max_id"] == 1
        assert manifest["field_coverage"]["fields"]["content_preview"]["present"] >= 1
        proof = manifest["activity_boundary_proof"]
        assert proof["overall_proof_level"] == "narrow_partial_activity_boundary"
        assert proof["complete_xueqiu_activity_boundary_claimed"] is False
        assert proof["pagination_completeness"]["completeness_level"] == "pagination_markers_observed_not_validated"
        assert "validated_pagination" in proof["missing_global_requirements"]


def test_collects_har_network_export_without_leaking_secrets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        har_path = root / "xueqiu-network.har"
        out = root / "out"
        response_payload = {
            "data": {
                "items": [
                    {
                        "type": "status",
                        "id": 2001,
                        "max_id": 2001,
                        "text": "继续跟踪 $贵州茅台(SH600519)$，等待更好的赔率。",
                        "created_at": "2026-07-08T09:30:00+08:00",
                        "user": {"id": 42, "screen_name": "价值研究员"},
                        "cookie": "must-not-leak",
                    }
                ]
            }
        }
        har_path.write_text(
            json.dumps(
                {
                    "log": {
                        "entries": [
                            {
                                "request": {
                                    "url": "https://xueqiu.com/statuses/user_timeline.json?xq_a_token=must-not-leak&count=20",
                                    "headers": [
                                        {"name": "Cookie", "value": "xq_a_token=must-not-leak"},
                                        {"name": "Authorization", "value": "Bearer must-not-leak"},
                                    ],
                                    "cookies": [{"name": "xq_a_token", "value": "must-not-leak"}],
                                },
                                "response": {
                                    "status": 200,
                                    "headers": [{"name": "Set-Cookie", "value": "xq_r_token=must-not-leak"}],
                                    "content": {"mimeType": "application/json", "text": json.dumps(response_payload, ensure_ascii=False)},
                                },
                            },
                            {
                                "request": {"url": "https://example.com/analytics"},
                                "response": {"status": 200, "content": {"mimeType": "application/json", "text": "{}"}},
                            },
                            {
                                "request": {"url": "https://xueqiu.com/v4/statuses/public_timeline.json"},
                                "response": {"status": 200, "content": {"mimeType": "text/html", "text": "<html>not json</html>"}},
                            },
                        ]
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(har_path),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T13:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        event = events[0]
        assert event["data"]["activity_type"] == "post"
        assert event["data"]["symbols"] == ["SH600519"]
        assert event["data"]["author"] == "价值研究员"
        assert event["raw_ref"]["parser"] == "har"
        assert event["raw_ref"]["har_entry"] == 1
        assert event["raw_ref"]["har_endpoint"] == "/statuses/user_timeline.json"
        assert "?" not in event["raw_ref"]["har_endpoint"]
        serialized_events = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized_events
        assert "xq_a_token" not in serialized_events
        assert "Authorization" not in serialized_events
        assert "Cookie" not in serialized_events

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["collection_audit"]
        assert audit["extension_counts"] == {".har": 1}
        assert audit["authorized_browser_network_export_used"] is True
        assert audit["browser_network_export_file_count"] == 1
        assert audit["har_entry_count"] == 3
        assert audit["har_xueqiu_entry_count"] == 2
        assert audit["har_response_record_count"] == 1
        assert audit["har_skipped_entry_count"] == 2
        assert audit["har_skip_reason_counts"] == {"non_json_response": 1, "non_xueqiu_url": 1}
        assert audit["har_endpoint_counts"] == {
            "/statuses/user_timeline.json": 1,
            "/v4/statuses/public_timeline.json": 1,
        }
        assert audit["har_secret_material_stripped_count"] >= 4
        assert audit["har_query_string_stripped_count"] == 1
        proof = manifest["activity_boundary_proof"]
        assert proof["pagination_completeness"]["completeness_level"] == "paginated_partial_export"
        assert proof["pagination_completeness"]["pagination_marker_count"] == 1
        assert proof["pagination_completeness"]["har_endpoint_counts"] == {
            "/statuses/user_timeline.json": 1,
            "/v4/statuses/public_timeline.json": 1,
        }
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["activity_boundary_proof"]["pagination_completeness"]["completeness_level"] == "paginated_partial_export"


def test_collects_browser_history_copy_filters_xueqiu_domains() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        history = root / "History"
        out = root / "out"
        write_chromium_history(
            history,
            [
                (1, "https://xueqiu.com/S/SH600519", "贵州茅台讨论", 5, 1, 10, chromium_time(2026, 7, 8, 1, 0), 1),
                (2, "https://xueqiu.com/u/123456", "价值研究员", 3, 0, 11, chromium_time(2026, 7, 8, 2, 0), 8),
                (3, "https://example.com/not-xueqiu", "无关页面", 9, 0, 12, chromium_time(2026, 7, 8, 3, 0), 0),
            ],
        )

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(history),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T14:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        events = [json.loads(line) for line in (out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 2
        assert {event["source"] for event in events} == {"雪球用户授权浏览器历史"}
        assert {event["data"]["source_surface"] for event in events} == {"browser_history"}
        assert {event["data"]["source_app"] for event in events} == {"chromium_history"}
        assert {event["data"]["activity_type"] for event in events} == {"saved_page"}
        assert all(event["raw_ref"]["parser"] == "browser_history" for event in events)
        assert all("xueqiu.com" in event["data"]["url"] for event in events)
        assert "example.com" not in json.dumps(events, ensure_ascii=False)
        first = next(event for event in events if event["data"]["url"].endswith("/S/SH600519"))
        assert first["data"]["visit_count"] == 5
        assert first["data"]["typed_count"] == 1
        assert first["data"]["transition_type"] == "typed"
        assert first["data"]["symbols"] == ["SH600519"]

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["collection_audit"]
        assert audit["extension_counts"] == {"<browser_history>": 1}
        assert audit["browser_history_input_count"] == 1
        assert audit["browser_history_event_count"] == 2
        assert audit["browser_history_source_apps"] == ["chromium_history"]
        assert audit["browser_history_domain_filtering"] is True
        assert audit["path_results"][0]["parser"] == "browser_history"
        proof = manifest["activity_boundary_proof"]
        assert proof["browser_history_boundary"]["browser_history_event_count"] == 2
        assert proof["browser_history_boundary"]["unrelated_browser_history_collected"] is False
        assert proof["pagination_completeness"]["browser_history_event_count"] == 2
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["activity_boundary_proof"]["browser_history_boundary"]["browser_history_domain_filtering"] is True


def test_collects_zipped_browser_history_copy_from_spaced_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "space input"
        root.mkdir()
        history = root / "History"
        package = root / "history package.zip"
        out = root / "out"
        write_chromium_history(
            history,
            [
                (1, "https://xueqiu.com?source=home", "雪球首页", 2, 1, 10, chromium_time(2026, 7, 8, 4, 0), 1),
                (2, "https://stock.xueqiu.com/v5/stock/chart/kline.json?symbol=SH600519", "行情接口", 4, 0, 11, chromium_time(2026, 7, 8, 5, 0), 0),
                (3, "https://notxueqiu.com/?next=https://xueqiu.com", "伪装域名", 8, 0, 12, chromium_time(2026, 7, 8, 6, 0), 0),
            ],
        )
        with zipfile.ZipFile(package, "w") as archive:
            archive.write(history, "Default/History")

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(package),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T15:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        events = [json.loads(line) for line in (out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 2
        serialized = json.dumps(events, ensure_ascii=False)
        assert "notxueqiu.com" not in serialized
        assert any(event["data"]["url"] == "https://xueqiu.com?source=home" for event in events)
        assert any(event["data"].get("symbols") == ["SH600519"] for event in events)
        assert {event["raw_ref"]["archive_member"] for event in events} == {"Default/History"}
        assert {event["raw_ref"]["parser"] for event in events} == {"browser_history"}

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["collection_audit"]
        assert audit["extension_counts"] == {".zip": 1}
        assert audit["archive_member_extension_counts"] == {"<browser_history>": 1}
        assert audit["browser_history_input_count"] == 1
        assert audit["browser_history_event_count"] == 2
        assert audit["path_results"][0]["parser"] == "zip"


def test_collects_safari_history_copy_without_optional_load_successful() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        history = root / "History.db"
        out = root / "out"
        write_safari_history(
            history,
            [
                (1, "https://xueqiu.com/S/SZ000001", "平安银行讨论", 7, 10, safari_time(2026, 7, 8, 7, 0)),
                (2, "https://example.com/not-xueqiu", "无关页面", 9, 11, safari_time(2026, 7, 8, 8, 0)),
            ],
        )

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(history),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T16:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        events = [json.loads(line) for line in (out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        event = events[0]
        assert event["data"]["source_surface"] == "browser_history"
        assert event["data"]["source_app"] == "safari_history"
        assert event["data"]["url"] == "https://xueqiu.com/S/SZ000001"
        assert event["data"]["visit_count"] == 7
        assert event["data"]["symbols"] == ["SZ000001"]
        assert "transition_type" not in event["data"]
        assert "example.com" not in json.dumps(events, ensure_ascii=False)

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["collection_audit"]
        assert audit["extension_counts"] == {"<browser_history>": 1}
        assert audit["browser_history_source_apps"] == ["safari_history"]
        assert manifest["activity_boundary_proof"]["browser_history_boundary"]["browser_history_event_count"] == 1


def test_collects_html_saved_page_and_manifest_audit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        html_path = root / "saved-xueqiu.html"
        out = root / "out"
        html_path.write_text(
            """
            <html>
              <head>
                <meta property="og:title" content="半导体行业收藏">
                <meta name="author" content="雪球用户">
                <link rel="canonical" href="https://xueqiu.com/123/456">
              </head>
              <body>收藏了一篇关于 $中芯国际(SH688981)$ 的讨论。</body>
            </html>
            """,
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(html_path),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T10:30:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        assert events[0]["data"]["activity_type"] == "saved_page"
        assert events[0]["data"]["source_surface"] == "saved_page"
        assert events[0]["data"]["url"] == "https://xueqiu.com/123/456"
        assert "SH688981" in events[0]["data"]["symbols"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_audit"]["extension_counts"] == {".html": 1}
        assert manifest["field_coverage"]["fields"]["url"]["present"] == 1


def test_syncs_package_to_soulmirror_lake() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        csv_path = root / "watchlist.csv"
        out = root / "out"
        soulmirror = root / "soulmirror"
        csv_path.write_text("type,code,name\nwatchlist,000001,平安银行\n", encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(csv_path),
                "--out-dir",
                str(out),
                "--sync-soulmirror",
                "--soulmirror-home",
                str(soulmirror),
                "--collected-at",
                "2026-07-08T11:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        assert (soulmirror / "lake" / "xueqiu-investor-activity" / "events.jsonl").exists()
        assert (soulmirror / "lake" / "xueqiu-investor-activity" / "latest" / "manifest.json").exists()
        assert (soulmirror / "lake" / "xueqiu-investor-activity" / "latest" / "soulmirror_sync.json").exists()


def test_collects_zip_excel_activity_package() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workbook_path = root / "portfolio.xlsx"
        zip_path = root / "xueqiu-package.zip"
        out = root / "out"

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "组合调仓"
        sheet.append(["type", "cube_symbol", "cube_name", "stock_symbol", "stock_name", "target_weight"])
        sheet.append(["portfolio", "ZH100001", "AI组合", "300750", "宁德时代", "12.5"])
        workbook.save(workbook_path)

        with zipfile.ZipFile(zip_path, "w") as package:
            package.write(workbook_path, "nested/portfolio.xlsx")
            package.writestr("../escape.json", json.dumps({"type": "post", "text": "must skip"}, ensure_ascii=False))

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(zip_path),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T12:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        assert events[0]["kind"] == "holding"
        assert events[0]["data"]["activity_type"] == "portfolio_activity"
        assert events[0]["data"]["symbol"] == "SZ300750"
        assert events[0]["raw_ref"]["archive_member"] == "nested/portfolio.xlsx"
        assert events[0]["raw_ref"]["member_row"] == 1
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must skip" not in serialized
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["archive_member_event_count"] == 1
        assert manifest["evidence_policy"]["xueqiu_is_broker_trade_source"] is False


def test_activity_boundary_proof_reports_broad_partial_coverage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        json_path = root / "all-surfaces.json"
        out = root / "out"
        json_path.write_text(
            json.dumps(
                {
                    "items": [
                        {"type": "watchlist", "symbol": "600519", "name": "贵州茅台"},
                        {"type": "follow_user", "screen_name": "价值研究员", "user_id": "u-1", "url": "https://xueqiu.com/u/1"},
                        {"type": "follow_portfolio", "cube_symbol": "ZH001", "cube_name": "红利组合", "url": "https://xueqiu.com/P/ZH001"},
                        {
                            "type": "portfolio",
                            "cube_symbol": "ZH001",
                            "cube_name": "红利组合",
                            "rebalancing_histories": [{"stock_symbol": "600519", "stock_name": "贵州茅台", "target_weight": "10"}],
                        },
                        {"type": "comment", "text": "同意继续观察估值。", "screen_name": "本人", "url": "https://xueqiu.com/1/2"},
                        {"type": "favorite", "title": "白酒深度", "url": "https://xueqiu.com/1/3", "text": "收藏行业研究。"},
                        {"type": "post", "text": "复盘：降低仓位等待赔率。", "url": "https://xueqiu.com/1/4"},
                        {"type": "saved_page", "title": "半导体收藏", "url": "https://xueqiu.com/1/5", "content": "保存页内容。"},
                    ],
                    "max_id": 88,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(json_path), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        proof = manifest["activity_boundary_proof"]
        assert proof["overall_proof_level"] == "broad_partial_activity_boundary"
        assert proof["missing_expected_activity_types"] == []
        assert proof["complete_xueqiu_activity_boundary_claimed"] is False
        assert proof["xueqiu_is_broker_trade_source"] is False
        assert proof["pagination_completeness"]["completeness_level"] == "pagination_markers_observed_not_validated"
        assert proof["pagination_completeness"]["complete_timeline_claimed"] is False
        assert proof["activity_proof_level_counts"]["usable_activity_evidence"] >= 6
        watchlist = next(item for item in proof["activity_proofs"] if item["activity_type"] == "watchlist")
        assert watchlist["proof_level"] == "usable_activity_evidence"
        assert watchlist["field_counts"]["symbols"] == 1
        summary = (out / "SUMMARY.md").read_text(encoding="utf-8")
        assert "活动覆盖证明：`broad_partial_activity_boundary`" in summary
        assert "分页完整性：`pagination_markers_observed_not_validated`" in summary
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["activity_boundary_proof"]["overall_proof_level"] == "broad_partial_activity_boundary"


if __name__ == "__main__":
    test_collect_watchlist_csv()
    test_collect_posts_json()
    test_collects_fixed_offline_fixture_with_evidence_boundary()
    test_activity_scope_policy_filters_authorized_records()
    test_activity_scope_policy_filtered_all_gap()
    test_activity_gap_event()
    test_collects_nested_xueqiu_api_shapes_and_sanitizes_secrets()
    test_collects_har_network_export_without_leaking_secrets()
    test_collects_browser_history_copy_filters_xueqiu_domains()
    test_collects_zipped_browser_history_copy_from_spaced_path()
    test_collects_safari_history_copy_without_optional_load_successful()
    test_collects_html_saved_page_and_manifest_audit()
    test_syncs_package_to_soulmirror_lake()
    test_collects_zip_excel_activity_package()
    test_activity_boundary_proof_reports_broad_partial_coverage()
    print("xueqiu-investor-activity tests passed.")
