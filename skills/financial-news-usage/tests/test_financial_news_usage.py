#!/usr/bin/env python3
"""Tests for financial-news-usage collector."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "financial_news_usage.py"


def chromium_time(value: datetime) -> int:
    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    return int((value - epoch).total_seconds() * 1_000_000)


def test_collect_usage_exports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        export = root / "usage.json"
        html = root / "wallstreetcn.html"
        alert_zip = root / "financial-news-alerts.zip"
        out = root / "out"
        export.write_text(
            json.dumps(
                {
                    "usage": [
                        {
                            "platform": "财联社",
                            "action": "收藏",
                            "title": "半导体产业链订单回暖",
                            "url": "https://www.cls.cn/detail/1",
                            "saved_at": "2026-07-08T08:30:00+08:00",
                            "channel": "电报",
                            "profile": {"token": "must-not-leak", "note": "keep"},
                        },
                        {
                            "platform": "格隆汇",
                            "action": "搜索",
                            "query": "港股创新药",
                            "time": "2026-07-08T09:00:00+08:00",
                        },
                        {
                            "platform": "华尔街见闻",
                            "action": "订阅",
                            "channel": "宏观",
                            "time": "2026-07-08T09:10:00+08:00",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        html.write_text(
            "<html><head><title>美联储路径与A股风险偏好</title>"
            "<meta property=\"og:site_name\" content=\"华尔街见闻\">"
            "<link rel=\"canonical\" href=\"https://wallstreetcn.com/articles/1\"></head>"
            "<body>用户保存的阅读页面。</body></html>",
            encoding="utf-8",
        )
        with zipfile.ZipFile(alert_zip, "w") as archive:
            archive.writestr(
                "cls-alert.json",
                json.dumps(
                    {
                        "alerts": [
                            {
                                "platform": "财联社",
                                "action": "提醒",
                                "title": "半导体自选提醒",
                                "url": "https://www.cls.cn/detail/alert",
                                "time": "2026-07-08T09:20:00+08:00",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            )
            archive.writestr("../unsafe.json", json.dumps([{"title": "不应读取"}], ensure_ascii=False))
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(root),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T03:20:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "financial-news-usage" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 5
        assert {event["data"]["platform"] for event in events} == {"cls", "gelonghui", "wallstreetcn"}
        assert {event["data"]["action_type"] for event in events} == {"favorite", "read", "search", "subscribe", "alert"}
        assert all("../unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all(event["collector"] == "financial-news-usage" for event in events)
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        assert any(event["data"].get("domain") == "www.cls.cn" for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_complete_usage_history"] is False
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["cls", "wallstreetcn", "gelonghui"]
        assert manifest["platform_coverage"]["missing_expected_platforms"] == []
        assert manifest["action_coverage"]["observed_expected_actions"] == ["read", "favorite", "search", "subscribe", "alert"]
        assert manifest["action_coverage"]["missing_expected_actions"] == []
        assert manifest["collection_readiness"]["platform_coverage_status"] == "all_expected_platforms_observed"
        assert manifest["collection_readiness"]["action_coverage_status"] == "all_expected_actions_observed"
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["source_is_public_news_crawler"] is False


def test_collect_chromium_browser_history() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        history = root / "History"
        out = root / "out"
        conn = sqlite3.connect(history)
        try:
            conn.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, typed_count INTEGER)")
            conn.execute("CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER, transition INTEGER)")
            conn.executemany(
                "INSERT INTO urls (id, url, title, visit_count, typed_count) VALUES (?, ?, ?, ?, ?)",
                [
                    (1, "https://www.cls.cn/detail/42", "财联社半导体快讯", 3, 1),
                    (2, "https://wallstreetcn.com/articles/8", "华尔街见闻宏观观察", 1, 0),
                    (3, "https://example.com/life", "普通网页", 5, 2),
                ],
            )
            conn.executemany(
                "INSERT INTO visits (id, url, visit_time, transition) VALUES (?, ?, ?, ?)",
                [
                    (10, 1, chromium_time(datetime(2026, 7, 8, 1, 0, tzinfo=timezone.utc)), 805306368),
                    (11, 2, chromium_time(datetime(2026, 7, 8, 2, 0, tzinfo=timezone.utc)), 268435456),
                    (12, 3, chromium_time(datetime(2026, 7, 8, 3, 0, tzinfo=timezone.utc)), 268435456),
                ],
            )
            conn.commit()
        finally:
            conn.close()

        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(root), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "financial-news-usage" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 2
        assert {event["data"]["platform"] for event in events} == {"cls", "wallstreetcn"}
        assert {event["data"]["source_app"] for event in events} == {"chromium_history"}
        assert all(event["data"]["action_type"] == "read" for event in events)
        assert not any("example.com" in json.dumps(event, ensure_ascii=False) for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["platform_counts"] == {"cls": 1, "wallstreetcn": 1}
        assert set(manifest["platform_coverage"]["missing_expected_platforms"]) == {"gelonghui"}


if __name__ == "__main__":
    test_collect_usage_exports()
    test_collect_chromium_browser_history()
    print("financial-news-usage tests passed.")
