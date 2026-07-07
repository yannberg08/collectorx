#!/usr/bin/env python3
"""Tests for wechat-favorites collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wechat_favorites.py"


def test_collect_json_and_html_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        export = root / "favorites.json"
        article = root / "wechat_article.html"
        out = root / "out"
        export.write_text(
            json.dumps(
                {
                    "favorites": [
                        {
                            "title": "半导体行业景气跟踪",
                            "author": "某券商研究",
                            "url": "https://mp.weixin.qq.com/s/investment",
                            "action": "收藏",
                            "saved_at": "2026-07-08T09:00:00+08:00",
                            "summary": "讨论财报、估值和风险点。",
                        },
                        {
                            "title": "周末做饭清单",
                            "author": "生活号",
                            "action": "阅读",
                            "saved_at": "2026-07-08T10:00:00+08:00",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        article.write_text(
            "<html><head><title>贵州茅台估值复盘</title>"
            "<meta property=\"og:site_name\" content=\"投资公众号\"></head>"
            "<body>买入框架、现金流和安全边际。</body></html>",
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
                "2026-07-08T02:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "wechat-favorites" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 3
        assert all(event["collector"] == "wechat-favorites" for event in events)
        assert all(event["kind"] == "file" for event in events)
        assert all(event["wiki_targets"] == ["internal.knowledge.saved_articles"] for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_article_favorites"] is False
        assert manifest["collection_readiness"]["source_collection_scope"] == "partial_authorized_input"


if __name__ == "__main__":
    test_collect_json_and_html_events()
    print("wechat-favorites tests passed.")
