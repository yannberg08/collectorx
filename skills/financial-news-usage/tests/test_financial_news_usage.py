#!/usr/bin/env python3
"""Tests for financial-news-usage collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "financial_news_usage.py"


def test_collect_usage_exports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        export = root / "usage.json"
        html = root / "wallstreetcn.html"
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
        assert len(events) == 4
        assert {event["data"]["platform"] for event in events} == {"cls", "gelonghui", "wallstreetcn"}
        assert {event["data"]["action_type"] for event in events} == {"favorite", "read", "search", "subscribe"}
        assert all(event["collector"] == "financial-news-usage" for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_complete_usage_history"] is False
        evidence = json.loads((out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        assert evidence["coverage_summary"]["source_is_public_news_crawler"] is False


if __name__ == "__main__":
    test_collect_usage_exports()
    print("financial-news-usage tests passed.")
