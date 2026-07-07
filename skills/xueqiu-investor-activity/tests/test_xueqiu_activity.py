#!/usr/bin/env python3
"""Tests for xueqiu-investor-activity."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


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


if __name__ == "__main__":
    test_collect_watchlist_csv()
    test_collect_posts_json()
    test_collects_nested_xueqiu_api_shapes_and_sanitizes_secrets()
    test_syncs_package_to_soulmirror_lake()
    print("xueqiu-investor-activity tests passed.")
