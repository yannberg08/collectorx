#!/usr/bin/env python3
"""Tests for social-activity collector."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import openpyxl


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
        assert all(event["data"]["evidence_role"] == "weak_influence_signal" for event in events)
        assert all(event["data"]["investment_claim_allowed"] is False for event in events)
        assert all(event["wiki_targets"] == ["internal.social.activity"] for event in events)
        comment = next(event for event in events if event["data"]["action_type"] == "comment")
        assert comment["kind"] == "message"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_claim_investment_influence"] is False
        assert manifest["collection_readiness"]["evidence_strength"] == "weak_attention"
        assert manifest["collection_readiness"]["source_collection_scope"] == "partial_authorized_input"


def test_collect_nested_sections_workbook_and_weak_policy() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        package = root / "xhs_social_package.json"
        workbook_path = root / "bilibili_activity.xlsx"
        weibo_zip = root / "weibo_share.zip"
        out = root / "out"
        package.write_text(
            json.dumps(
                {
                    "platform": "小红书",
                    "favorites": [
                        {
                            "title": "基金定投纪律",
                            "creator": "投教作者",
                            "url": "https://www.xiaohongshu.com/explore/abc",
                            "item_id": "xhs-abc",
                            "symbols": "000300.SH",
                            "favorite_count": "86",
                            "content": "投资内容" * 800,
                            "profile": {"token": "must-not-leak"},
                        }
                    ],
                    "likes": [{"title": "消费观察", "creator": "消费研究员", "like_count": "1.2万"}],
                    "comments": [{"title": "新能源讨论", "comment": "怎么看现金流？", "creator_id": "u-1", "comment_count": "42"}],
                    "shares": [{"title": "港股互联网复盘", "share_count": "3"}],
                    "follows": [{"creator": "财经博主C", "creator_url": "https://weibo.com/u/finance-c", "follower_count": "20000"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        workbook = openpyxl.Workbook()
        watch = workbook.active
        watch.title = "watch_history"
        watch.append(["Platform", "Title", "Creator", "URL", "Tags", "View Count", "Duration", "Progress", "Time"])
        watch.append(["B站", "半导体产业链复盘", "投研UP主", "https://www.bilibili.com/video/BV1", "股票,半导体", "2.5万", "1800", "75%", "2026-07-08T10:00:00+08:00"])
        fav = workbook.create_sheet("favorites")
        fav.append(["Title", "Creator", "URL", "Topics"])
        fav.append(["微博AI投资主线", "财经博主D", "https://weibo.com/123/456", "AI,投资"])
        workbook.save(workbook_path)
        with zipfile.ZipFile(weibo_zip, "w") as archive:
            archive.writestr(
                "shares/weibo-share.json",
                json.dumps(
                    {
                        "shares": [
                            {
                                "platform": "微博",
                                "title": "转发宏观流动性图表",
                                "creator": "宏观研究员E",
                                "url": "https://weibo.com/234/567",
                                "share_count": "5",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            )
            archive.writestr("../unsafe.json", json.dumps([{"platform": "微博", "action": "点赞"}], ensure_ascii=False))
            archive.writestr("..\\windows-traversal.json", json.dumps([{"platform": "微博", "action": "点赞"}], ensure_ascii=False))
            archive.writestr("C:\\unsafe.json", json.dumps([{"platform": "微博", "action": "点赞"}], ensure_ascii=False))

        subprocess.run(
            [sys.executable, str(SCRIPT), "collect", "--input", str(root), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [json.loads(line) for line in (out / "lake" / "social-activity" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(events) == 8
        assert {event["data"]["platform"] for event in events} == {"bilibili", "weibo", "xiaohongshu"}
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        favorite = next(event for event in events if event["data"].get("title") == "基金定投纪律")
        assert favorite["data"]["domain"] == "www.xiaohongshu.com"
        assert len(favorite["data"]["raw"]["content"]) == 1200
        assert favorite["data"]["content_length"] > 1200
        like = next(event for event in events if event["data"].get("title") == "消费观察")
        assert like["data"]["like_count"] == 12000.0
        watch_event = next(event for event in events if event["data"].get("title") == "半导体产业链复盘")
        assert watch_event["data"]["view_count"] == 25000.0
        assert watch_event["data"]["tags"] == ["股票", "半导体"]
        assert watch_event["data"]["duration_seconds"] == 1800.0
        zip_event = next(event for event in events if event["data"].get("title") == "转发宏观流动性图表")
        assert zip_event["raw_ref"]["path"] == f"{weibo_zip}::shares/weibo-share.json"
        assert zip_event["raw_ref"]["source_archive"] == str(weibo_zip)
        assert zip_event["raw_ref"]["archive_member"] == "shares/weibo-share.json"
        assert all("../unsafe" not in event["raw_ref"]["path"] for event in events)
        assert all("windows-traversal" not in event["raw_ref"]["path"] for event in events)
        assert all("C:/unsafe" not in event["raw_ref"]["path"] for event in events)
        assert all(event["data"]["requires_corroboration"] is True for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["action_counts"]["favorite"] == 2
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["weibo", "bilibili", "xiaohongshu"]
        assert manifest["platform_coverage"]["missing_expected_platforms"] == []
        assert manifest["action_coverage"]["observed_expected_actions"] == ["follow", "like", "favorite", "watch", "comment", "share"]
        assert manifest["action_coverage"]["missing_expected_actions"] == []
        assert manifest["weak_signal_field_coverage"]["missing_recommended_fields"] == []
        assert manifest["influence_surface_summary"]["weak_signal_event_count"] == 8
        assert manifest["influence_surface_summary"]["events_with_creator"] >= 6
        assert manifest["influence_surface_summary"]["events_with_engagement_counts"] >= 5
        assert manifest["influence_surface_summary"]["events_with_symbols"] == 1
        assert manifest["influence_surface_summary"]["events_with_source_section"] == 8
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["source_audit"]["source_section_event_count"] == 8
        assert manifest["source_audit"]["archive_path_traversal_members_collected"] is False
        assert manifest["source_audit"]["windows_drive_archive_members_collected"] is False
        assert manifest["content_policy"]["full_platform_scrape"] is False
        assert manifest["content_policy"]["content_preview_max_chars"] == 1200
        assert manifest["weak_evidence_policy"]["investment_claim_allowed"] is False
        assert manifest["weak_evidence_policy"]["usable_as_investment_conclusion"] is False
        assert manifest["weak_evidence_policy"]["generic_collector"] is True
        assert manifest["collection_readiness"]["platform_coverage_status"] == "all_expected_platforms_observed"
        assert manifest["collection_readiness"]["action_coverage_status"] == "all_expected_actions_observed"
        assert manifest["collection_readiness"]["weak_signal_field_coverage_status"] == "all_expected_weak_signal_fields_observed"
        assert manifest["collection_readiness"]["collector_claims_investment_conclusion"] is False


if __name__ == "__main__":
    test_collect_social_activity_exports()
    test_collect_nested_sections_workbook_and_weak_policy()
    print("social-activity tests passed.")
