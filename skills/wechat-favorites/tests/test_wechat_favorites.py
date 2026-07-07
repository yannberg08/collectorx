#!/usr/bin/env python3
"""Tests for wechat-favorites collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "wechat_favorites.py"


def test_collect_json_and_html_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        export = root / "favorites.json"
        article = root / "wechat_article.html"
        share_zip = root / "wechat-share.zip"
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
                            "token": "must-not-leak",
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
        with zipfile.ZipFile(share_zip, "w") as archive:
            archive.writestr(
                "shares.json",
                json.dumps(
                    {
                        "articles": [
                            {
                                "title": "港股互联网复盘",
                                "publisher": "投资笔记号",
                                "url": "https://mp.weixin.qq.com/s/share",
                                "action": "转发",
                                "shared_at": "2026-07-08T11:00:00+08:00",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            )
            archive.writestr("../unsafe.json", json.dumps([{"title": "不应读取"}], ensure_ascii=False))
            archive.writestr("..\\windows-traversal.json", json.dumps([{"title": "不应读取 Windows traversal"}], ensure_ascii=False))
            archive.writestr("C:\\unsafe.json", json.dumps([{"title": "不应读取 Windows drive"}], ensure_ascii=False))
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
        assert len(events) == 4
        assert all(event["collector"] == "wechat-favorites" for event in events)
        assert all(event["kind"] == "file" for event in events)
        assert all(event["wiki_targets"] == ["internal.knowledge.saved_articles"] for event in events)
        assert {event["data"]["action_type"] for event in events} == {"favorite", "read", "share", "saved_file"}
        assert all("../unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("windows-traversal" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("C:/unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        assert any(event["data"].get("text_length") for event in events)
        share_event = next(event for event in events if event["data"]["action_type"] == "share")
        assert share_event["raw_ref"]["source_archive"] == str(share_zip)
        assert share_event["raw_ref"]["archive_member"] == "shares.json"
        assert "must-not-leak" not in json.dumps(events, ensure_ascii=False)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_article_favorites"] is False
        assert manifest["collection_readiness"]["source_collection_scope"] == "partial_authorized_input"
        assert manifest["action_coverage"]["observed_expected_actions"] == ["favorite", "read", "share", "saved_file"]
        assert manifest["action_coverage"]["missing_expected_actions"] == []
        assert manifest["collection_readiness"]["action_coverage_status"] == "all_expected_actions_observed"
        assert manifest["action_coverage"]["real_account_validation"] is False
        assert manifest["field_coverage"]["field_counts"]["action_type"] == 4
        assert manifest["article_surface_summary"]["events_with_url"] >= 2
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["source_audit"]["archive_path_traversal_members_collected"] is False
        assert manifest["content_policy"]["full_public_account_crawl"] is False
        assert manifest["content_policy"]["full_content_included_by_default"] is False
        assert manifest["evidence_policy"]["required_lens"] == "wechat-article-favorites"
        assert manifest["source_account_count"] == 4


if __name__ == "__main__":
    test_collect_json_and_html_events()
    print("wechat-favorites tests passed.")
