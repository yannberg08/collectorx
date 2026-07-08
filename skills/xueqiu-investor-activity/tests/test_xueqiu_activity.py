#!/usr/bin/env python3
"""Tests for xueqiu-investor-activity."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "xueqiu_activity.py"


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
        event = json.loads((out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert event["schema"] == "collectorx.event.v1"
        assert event["kind"] == "watchlist"
        assert event["data"]["symbol"] == "SH600519"
        assert event["data"]["symbols"] == ["SH600519"]
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
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
        events = [json.loads(line) for line in (out / "lake" / "xueqiu-investor-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [event["kind"] for event in events] == ["note", "profile"]


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


if __name__ == "__main__":
    test_collect_watchlist_csv()
    test_collect_posts_json()
    test_collects_nested_xueqiu_api_shapes_and_sanitizes_secrets()
    test_collects_har_network_export_without_leaking_secrets()
    test_collects_html_saved_page_and_manifest_audit()
    test_syncs_package_to_soulmirror_lake()
    test_collects_zip_excel_activity_package()
    print("xueqiu-investor-activity tests passed.")
