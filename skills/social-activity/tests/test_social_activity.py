#!/usr/bin/env python3
"""Tests for social-activity collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "social_activity.py"


def test_collect_social_activity_exports() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        export = root / "social.json"
        csv_path = root / "bilibili.csv"
        html_path = root / "xiaohongshu.html"
        out = root / "out"
        export.write_text(
            json.dumps(
                {
                    "activities": [
                        {
                            "platform": "微博",
                            "action": "关注",
                            "creator": "财经博主A",
                            "title": "关注财经博主A",
                            "time": "2026-07-08T09:00:00+08:00",
                        },
                        {
                            "platform": "微博",
                            "action": "评论",
                            "creator": "基金经理B",
                            "text": "这次财报怎么看？",
                            "time": "2026-07-08T09:30:00+08:00",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        csv_path.write_text(
            "platform,action,title,creator,tags,time\n"
            "B站,观看,半导体投资复盘,投研UP主,\"股票,半导体\",2026-07-08T10:00:00+08:00\n"
            "B站,点赞,游戏直播剪辑,娱乐UP主,游戏,2026-07-08T11:00:00+08:00\n",
            encoding="utf-8",
        )
        html_path.write_text(
            "<html><head><title>小红书 投资笔记收藏</title>"
            "<meta property=\"og:site_name\" content=\"小红书\"></head>"
            "<body>收藏一篇关于基金定投和风险控制的笔记。</body></html>",
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
                "2026-07-08T05:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "social-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 5
        assert {event["data"]["platform"] for event in events} == {"bilibili", "weibo", "xiaohongshu"}
        assert {event["data"]["action_type"] for event in events} == {"comment", "follow", "like", "saved_page", "watch"}
        assert all(event["wiki_targets"] == ["internal.social.activity"] for event in events)
        comment = next(event for event in events if event["data"]["action_type"] == "comment")
        assert comment["kind"] == "message"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_influence"] is False
        assert manifest["collection_readiness"]["source_collection_scope"] == "partial_authorized_input"


if __name__ == "__main__":
    test_collect_social_activity_exports()
    print("social-activity tests passed.")
