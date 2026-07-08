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
        unsupported = root / "ignore.bin"
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
                            "favorite_reason": "估值框架可复用",
                            "read_duration_seconds": 180,
                            "read_progress": "85%",
                            "证券代码": "688981",
                            "read_count": "1234",
                            "like_count": 56,
                            "token": "must-not-leak",
                        },
                        {
                            "title": "周末做饭清单",
                            "author": "生活号",
                            "action": "阅读",
                            "saved_at": "2026-07-08T10:00:00+08:00",
                            "read_duration": "2分钟",
                            "read_progress": "50%",
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
                                "article_id": "share-article-001",
                                "share_target": "投研群",
                                "symbols": ["00700", "03690"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            )
            archive.writestr("../unsafe.json", json.dumps([{"title": "不应读取"}], ensure_ascii=False))
            archive.writestr("..\\windows-traversal.json", json.dumps([{"title": "不应读取 Windows traversal"}], ensure_ascii=False))
            archive.writestr("C:\\unsafe.json", json.dumps([{"title": "不应读取 Windows drive"}], ensure_ascii=False))
        unsupported.write_bytes(b"not a supported favorite export")
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
        assert share_event["data"]["article_id"] == "share-article-001"
        assert share_event["data"]["share_target"] == "投研群"
        assert share_event["data"]["symbols"] == ["00700", "03690"]
        favorite_event = next(event for event in events if event["data"]["action_type"] == "favorite")
        assert favorite_event["data"]["source_account_type"] == "broker_research_account"
        assert favorite_event["data"]["favorite_reason"] == "估值框架可复用"
        assert favorite_event["data"]["read_duration_seconds"] == 180
        assert favorite_event["data"]["read_progress"] == 0.85
        assert favorite_event["data"]["symbols"] == ["688981"]
        assert favorite_event["data"]["engagement"]["read_count"] == 1234
        assert favorite_event["data"]["engagement"]["like_count"] == 56
        assert "must-not-leak" not in json.dumps(events, ensure_ascii=False)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_article_favorites"] is False
        assert manifest["collection_readiness"]["source_collection_scope"] == "partial_authorized_input"
        assert manifest["action_coverage"]["observed_expected_actions"] == ["favorite", "read", "share", "saved_file"]
        assert manifest["action_coverage"]["missing_expected_actions"] == []
        assert manifest["collection_readiness"]["action_coverage_status"] == "all_expected_actions_observed"
        assert manifest["action_coverage"]["real_account_validation"] is False
        assert manifest["field_coverage"]["field_counts"]["action_type"] == 4
        assert manifest["field_coverage"]["field_counts"]["source_account_type"] == 4
        assert manifest["field_coverage"]["field_counts"]["article_id"] >= 2
        assert manifest["field_coverage"]["field_counts"]["symbols"] == 2
        assert manifest["field_coverage"]["field_counts"]["favorite_reason"] == 1
        assert manifest["field_coverage"]["field_counts"]["share_target"] == 1
        assert manifest["field_coverage"]["field_counts"]["read_duration_seconds"] == 2
        assert manifest["field_coverage"]["field_counts"]["read_progress"] == 2
        assert manifest["field_coverage"]["field_counts"]["engagement"] == 1
        assert manifest["article_surface_summary"]["events_with_url"] >= 2
        assert manifest["article_surface_summary"]["events_with_article_id"] >= 2
        assert manifest["article_surface_summary"]["events_with_symbols"] == 2
        assert manifest["article_surface_summary"]["source_account_type_counts"]["broker_research_account"] == 1
        assert manifest["article_surface_summary"]["source_account_type_counts"]["investment_creator_account"] >= 2
        assert manifest["article_behavior_summary"]["events_with_favorite_reason"] == 1
        assert manifest["article_behavior_summary"]["events_with_share_target"] == 1
        assert manifest["article_behavior_summary"]["events_with_read_duration"] == 2
        assert manifest["article_behavior_summary"]["events_with_read_progress"] == 2
        assert manifest["article_behavior_summary"]["events_with_engagement"] == 1
        assert manifest["article_behavior_summary"]["average_read_duration_seconds"] == 150
        assert manifest["article_behavior_summary"]["average_read_progress"] == 0.675
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_member_count"] == 4
        assert manifest["source_audit"]["skipped_archive_member_count"] == 3
        assert manifest["source_audit"]["skipped_archive_member_reason_counts"] == {"unsafe_path": 3}
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["source_audit"]["resolved_input_file_count"] == 3
        assert manifest["source_audit"]["parsed_record_count"] == 4
        assert manifest["source_audit"]["emitted_event_count"] == 4
        assert manifest["source_audit"]["skipped_file_count"] == 1
        assert manifest["source_audit"]["skipped_reason_counts"] == {"unsupported_extension": 1}
        assert manifest["source_audit"]["skipped_extension_counts"] == {".bin": 1}
        assert len(manifest["source_audit"]["path_results"]) == 4
        assert manifest["source_audit"]["archive_path_traversal_members_collected"] is False
        assert manifest["source_audit"]["windows_drive_archive_members_collected"] is False
        assert manifest["content_policy"]["full_public_account_crawl"] is False
        assert manifest["content_policy"]["full_content_included_by_default"] is False
        assert manifest["evidence_policy"]["required_lens"] == "wechat-article-favorites"
        assert manifest["source_account_count"] == 4


def test_collect_missing_input_writes_gap_audit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "out"
        missing = root / "missing-export"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "collect",
                "--input",
                str(missing),
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
        assert len(events) == 1
        assert events[0]["data"]["gap"] == "wechat_favorites_input_missing"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["status"] == "needs_wechat_favorites_input"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["source_audit"]["input_count"] == 1
        assert manifest["source_audit"]["input_missing_count"] == 1
        assert manifest["source_audit"]["parsed_record_count"] == 0
        assert manifest["source_audit"]["skipped_reason_counts"] == {"input_missing": 1}
        assert manifest["source_audit"]["path_results"][0]["status"] == "missing"


def test_collect_scope_policy_filters_account_action_tag_domain_and_keyword() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        export = root / "favorites.json"
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
                            "tags": ["投资"],
                            "summary": "讨论估值和风险。",
                        },
                        {
                            "title": "周末买菜清单",
                            "author": "某券商研究",
                            "url": "https://mp.weixin.qq.com/s/life",
                            "action": "收藏",
                            "tags": ["投资"],
                        },
                        {
                            "title": "半导体观察",
                            "author": "生活号",
                            "url": "https://mp.weixin.qq.com/s/life-account",
                            "action": "收藏",
                            "tags": ["投资"],
                        },
                        {
                            "title": "估值框架阅读",
                            "author": "某券商研究",
                            "url": "https://mp.weixin.qq.com/s/read",
                            "action": "阅读",
                            "tags": ["投资"],
                        },
                        {
                            "title": "外部网页收藏",
                            "author": "某券商研究",
                            "url": "https://example.com/article",
                            "action": "收藏",
                            "tags": ["投资"],
                        },
                    ]
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
                str(export),
                "--out-dir",
                str(out),
                "--allow-source-account",
                "某券商研究",
                "--allow-action",
                "favorite",
                "--allow-tag",
                "投资",
                "--allow-domain",
                "mp.weixin.qq.com",
                "--deny-keyword",
                "买菜",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "wechat-favorites" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 1
        assert events[0]["data"]["title"] == "半导体行业景气跟踪"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        policy = manifest["source_audit"]["wechat_favorites_scope_policy"]
        assert manifest["source_audit"]["candidate_record_count"] == 5
        assert manifest["source_audit"]["emitted_event_count"] == 1
        assert policy["enabled"] is True
        assert policy["filtered_record_count"] == 4
        assert policy["filter_reason_counts"] == {
            "action_not_allowed": 1,
            "domain_not_allowed": 1,
            "keyword_denied": 1,
            "source_account_not_allowed": 1,
        }
        assert manifest["source_audit"]["wechat_favorites_scope_policy_filtered_all"] is False
        assert manifest["source_audit"]["path_results"][0]["scope_policy_filtered_record_count"] == 4


def test_collect_scope_policy_filtered_all_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        export = root / "favorites.json"
        out = root / "out"
        export.write_text(
            json.dumps(
                [
                    {
                        "title": "半导体行业景气跟踪",
                        "author": "某券商研究",
                        "url": "https://mp.weixin.qq.com/s/investment",
                        "action": "收藏",
                        "tags": ["投资"],
                    }
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
                str(export),
                "--out-dir",
                str(out),
                "--allow-tag",
                "不存在的标签",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events_path = out / "lake" / "wechat-favorites" / "events.jsonl"
        assert events_path.read_text(encoding="utf-8") == ""
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 0
        assert manifest["collection_readiness"]["status"] == "scope_policy_filtered_all"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["collection_readiness"]["source_collection_scope"] == "scope_policy_excluded_all"
        assert manifest["source_audit"]["wechat_favorites_scope_policy"]["filter_reason_counts"] == {"tag_not_allowed": 1}
        assert manifest["source_audit"]["wechat_favorites_scope_policy_filtered_all"] is True


if __name__ == "__main__":
    test_collect_json_and_html_events()
    test_collect_missing_input_writes_gap_audit()
    test_collect_scope_policy_filters_account_action_tag_domain_and_keyword()
    test_collect_scope_policy_filtered_all_status()
    print("wechat-favorites tests passed.")
