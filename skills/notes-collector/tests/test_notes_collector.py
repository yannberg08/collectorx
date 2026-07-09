#!/usr/bin/env python3
"""Tests for notes-collector event output."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
SCRIPT = ROOT / "scripts" / "notes_api.py"
INVESTOR_SCRIPT = REPO_ROOT / "skills" / "investor-source-collectors" / "scripts" / "investor_sources.py"
PACKAGE_VALIDATOR = REPO_ROOT / "tools" / "validate_collector_package.py"
NOTES_INVESTMENT_FIXTURE = REPO_ROOT / "examples" / "fixtures" / "notes-investment-e2e" / "obsidian-vault"


def read_events(out: Path) -> list[dict]:
    event_file = out / "lake" / "notes" / "events.jsonl"
    return [json.loads(line) for line in event_file.read_text(encoding="utf-8").splitlines()]


def assert_package_valid(out: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(PACKAGE_VALIDATOR),
            str(out),
            "--collector",
            "notes",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
    )


def assert_investor_package_valid(out: Path, collector: str) -> None:
    subprocess.run(
        [
            sys.executable,
            str(PACKAGE_VALIDATOR),
            str(out),
            "--collector",
            collector,
            "--require-evidence",
            "--json",
        ],
        check=True,
        text=True,
        capture_output=True,
    )


def test_obsidian_outputs_collectorx_events_without_full_content_by_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        vault = root / "vault"
        vault.mkdir()
        (vault / "investment.md").write_text("#复盘\n贵州茅台 估值和买入纪律\n", encoding="utf-8")
        (vault / "research.canvas").write_text(
            json.dumps(
                {
                    "nodes": [
                        {"id": "n1", "type": "text", "text": "#估值\n研究贵州茅台现金流和安全边际"},
                        {"id": "n2", "type": "file", "file": "reports/maotai.md"},
                    ],
                    "edges": [{"id": "e1", "fromNode": "n1", "toNode": "n2"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        export = root / "notes.json"
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "obsidian",
                "--vault",
                str(vault),
                "--export",
                str(export),
                "--out-dir",
                str(out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 2
        event = next(item for item in events if item["data"]["title"] == "investment")
        assert event["schema"] == "collectorx.event.v1"
        assert event["collector"] == "notes"
        assert event["kind"] == "note"
        assert event["data"]["source_app"] == "obsidian"
        assert event["data"]["note_format"] == "markdown"
        assert event["data"]["content_preview"].startswith("#复盘")
        assert event["data"]["content_length"] == len("#复盘\n贵州茅台 估值和买入纪律\n")
        assert event["data"]["content_included"] is False
        assert len(event["data"]["content_digest"]) == 64
        assert "content" not in event["data"]
        assert event["wiki_targets"] == ["internal.knowledge.notes"]
        canvas_event = next(item for item in events if item["data"]["title"] == "research")
        assert canvas_event["data"]["note_format"] == "obsidian_canvas"
        assert canvas_event["data"]["canvas_node_count"] == 2
        assert canvas_event["data"]["canvas_edge_count"] == 1
        assert canvas_event["data"]["linked_files"] == ["reports/maotai.md"]
        assert canvas_event["data"]["tags"] == ["估值"]
        assert "安全边际" in canvas_event["data"]["content_preview"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 2
        assert manifest["note_event_count"] == 2
        assert manifest["gap_event_count"] == 0
        assert manifest["collection_readiness"]["can_claim_investment_notes"] is False
        assert manifest["content_policy"]["full_content_event_count"] == 0
        assert manifest["content_policy"]["preview_only_event_count"] == 2
        assert manifest["evidence_policy"]["required_lens"] == "investment-notes"
        assert manifest["field_coverage"]["field_counts"]["content_length"] == 2
        assert manifest["field_coverage"]["field_counts"]["note_format"] == 2
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["obsidian"]
        assert set(manifest["platform_coverage"]["missing_expected_platforms"]) == {"notion", "youdao", "evernote"}
        assert manifest["collection_readiness"]["platform_coverage_status"] == "partial_expected_platforms_observed"
        assert manifest["source_audit"]["source_type"] == "obsidian_vault"
        assert manifest["source_audit"]["resolved_input_file_count"] == 2
        assert manifest["source_audit"]["extension_counts"] == {".canvas": 1, ".md": 1}
        assert manifest["source_audit"]["canvas_import_supported"] is True
        assert manifest["source_audit"]["canvas_file_count"] == 1
        assert manifest["source_audit"]["canvas_note_count"] == 1
        assert manifest["source_audit"]["parsed_note_count"] == 2
        assert manifest["source_audit"]["emitted_event_count"] == 2
        assert manifest["source_audit"]["path_results"][0]["status"] == "parsed"
        assert_package_valid(out)


def test_notes_investment_fixture_flows_into_investment_notes_lens() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        notes_export = root / "notes.json"
        notes_out = root / "notes-out"
        lens_out = root / "lens-out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "obsidian",
                "--vault",
                str(NOTES_INVESTMENT_FIXTURE),
                "--export",
                str(notes_export),
                "--out-dir",
                str(notes_out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        notes_events = read_events(notes_out)
        assert len(notes_events) == 4
        notes_titles = {event["data"]["title"] for event in notes_events}
        assert notes_titles == {
            "600519-trade-review",
            "semiconductor-valuation-assumptions",
            "trade-checklist",
            "weekend-plan",
        }
        assert all(event["collector"] == "notes" for event in notes_events)
        assert all(event["kind"] == "note" for event in notes_events)
        assert all(event["data"]["content_included"] is False for event in notes_events)
        assert all("content" not in event["data"] for event in notes_events)
        assert any(event["data"]["title"] == "weekend-plan" for event in notes_events)
        assert any("周末生活安排" in event["data"]["content_preview"] for event in notes_events)

        notes_manifest = json.loads((notes_out / "manifest.json").read_text(encoding="utf-8"))
        assert notes_manifest["event_count"] == 4
        assert notes_manifest["note_event_count"] == 4
        assert notes_manifest["gap_event_count"] == 0
        assert notes_manifest["content_policy"]["full_content_event_count"] == 0
        assert notes_manifest["content_policy"]["preview_only_event_count"] == 4
        assert notes_manifest["content_policy"]["investment_classification_done"] is False
        assert notes_manifest["evidence_policy"]["generic_collector"] is True
        assert notes_manifest["evidence_policy"]["required_lens"] == "investment-notes"
        assert notes_manifest["evidence_policy"]["collector_writes_investor_wiki_directly"] is False
        assert notes_manifest["collection_readiness"]["can_claim_investment_notes"] is False
        assert notes_manifest["source_audit"]["source_type"] == "obsidian_vault"
        assert notes_manifest["source_audit"]["parsed_note_count"] == 4
        assert_package_valid(notes_out)

        subprocess.run(
            [
                sys.executable,
                str(INVESTOR_SCRIPT),
                "collect",
                "--source",
                "investment-notes",
                "--input",
                str(notes_out / "lake" / "notes" / "events.jsonl"),
                "--out-dir",
                str(lens_out),
                "--collected-at",
                "2026-07-08T12:30:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        lens_events = [
            json.loads(line)
            for line in (lens_out / "lake" / "investment-notes" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(lens_events) == 3
        lens_titles = {event["data"]["payload"]["title"] for event in lens_events}
        assert lens_titles == {"600519-trade-review", "semiconductor-valuation-assumptions", "trade-checklist"}
        assert "weekend-plan" not in lens_titles
        assert {event["raw_ref"]["upstream_event_id"] for event in lens_events} == {
            event["id"] for event in notes_events if event["data"]["title"] in lens_titles
        }
        assert all(event["raw_ref"]["parser"] == "collectorx.event.v1" for event in lens_events)
        assert all(event["raw_ref"]["upstream_raw_ref"]["source_app"] == "obsidian" for event in lens_events)
        assert all(event["data"]["payload"]["upstream_collector"] == "notes" for event in lens_events)
        assert all(event["data"]["payload"]["content_included"] is False for event in lens_events)
        assert all("content" not in event["data"]["payload"] for event in lens_events)

        classifications = [event["data"]["classification"] for event in lens_events]
        assert all(item["is_investment_evidence"] is True for item in classifications)
        assert any("review_note" in item["investment_note_types"] for item in classifications)
        assert any("rules_library" in item["investment_note_types"] for item in classifications)
        assert any("trade_checklist" in item["investment_note_types"] for item in classifications)
        assert any("valuation_assumption" in item["investment_note_types"] for item in classifications)
        assert any("research_note" in item["investment_note_types"] for item in classifications)

        lens_manifest = json.loads((lens_out / "manifest.json").read_text(encoding="utf-8"))
        assert lens_manifest["collection_readiness"]["can_feed_investor_wiki_evidence"] is True
        surface = lens_manifest["lens_surface_summary"]
        assert surface["event_count"] == 3
        assert surface["source_app_counts"] == {"obsidian": 3}
        assert surface["upstream_collector_counts"] == {"notes": 3}
        assert surface["full_content_event_count"] == 0
        assert surface["preview_only_event_count"] == 3
        assert surface["tagged_event_count"] == 3
        assert surface["collector_writes_wiki_directly"] is False
        assert surface["investment_note_type_counts"]["review_note"] >= 1
        assert surface["investment_note_type_counts"]["rules_library"] >= 1
        assert surface["investment_note_type_counts"]["trade_checklist"] >= 1
        assert surface["investment_note_type_counts"]["valuation_assumption"] >= 1
        assert surface["investment_note_type_counts"]["research_note"] >= 1

        proof = lens_manifest["investment_note_boundary_proof"]
        assert proof["source_type"] == "notes_lake_investment_note_lens"
        assert proof["proof_level"] == "authorized_investment_notes_preview_only"
        assert proof["event_count"] == 3
        assert proof["candidate_record_count"] == 4
        assert proof["matched_event_count"] == 3
        assert proof["filtered_candidate_count"] == 1
        assert proof["complete_notes_vault_claimed"] is False
        assert proof["complete_note_context_claimed"] is False
        assert proof["direct_notes_reconnect"] is False
        assert proof["requires_upstream_notes_collector"] is True
        assert proof["collector_writes_wiki_directly"] is False
        assert proof["content_boundary"]["full_content_event_count"] == 0
        assert proof["content_boundary"]["preview_only_event_count"] == 3
        assert proof["note_boundary"]["generic_notes_lens"] is True
        assert proof["note_boundary"]["collector_writes_wiki_directly"] is False

        evidence = json.loads((lens_out / "investor_wiki_evidence.v1.json").read_text(encoding="utf-8"))
        evidence_surface = evidence["coverage_summary"]["source_surface_summary"]["investment-notes"]
        assert evidence_surface["event_count"] == 3
        assert evidence_surface["source_app_counts"] == {"obsidian": 3}
        assert evidence_surface["generic_notes_lens"] is True
        assert evidence_surface["collector_writes_wiki_directly"] is False
        assert evidence_surface["full_content_event_count"] == 0
        assert evidence_surface["preview_only_event_count"] == 3
        assert_investor_package_valid(lens_out, "investment-notes")


def test_import_outputs_youdao_evernote_and_markdown_events() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        exports = root / "exports"
        exports.mkdir()
        (exports / "youdao-notes.json").write_text(
            json.dumps(
                {
                    "notes": [
                        {
                            "source": "有道云笔记",
                            "title": "半导体复盘",
                            "content": "估值、库存周期、买入纪律",
                            "updated": "2026-07-08T10:00:00+08:00",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (exports / "evernote.enex").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<en-export>
  <note>
    <title>白酒跟踪</title>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?><en-note>现金流和估值复盘</en-note>]]></content>
    <created>20260708T020000Z</created>
    <tag>投资</tag>
  </note>
</en-export>
""",
            encoding="utf-8",
        )
        (exports / "rules.md").write_text("# 交易规则\n控制仓位和回撤\n", encoding="utf-8")
        (exports / "obsidian.canvas").write_text(
            json.dumps({"nodes": [{"id": "n1", "type": "text", "text": "#规则\n仓位上限和回撤控制"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (exports / "ignore.bin").write_bytes(b"not a note")
        export = root / "notes.json"
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "import",
                "--input",
                str(exports),
                "--source-app",
                "auto",
                "--export",
                str(export),
                "--out-dir",
                str(out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 4
        assert {event["data"]["source_app"] for event in events} == {"youdao", "evernote", "markdown", "obsidian"}
        assert {event["data"]["title"] for event in events} == {"半导体复盘", "白酒跟踪", "交易规则", "obsidian"}
        assert all("content" not in event["data"] for event in events)
        assert any("现金流和估值复盘" in event["data"]["content_preview"] for event in events)
        assert any(event["data"].get("note_format") == "obsidian_canvas" for event in events)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 4
        assert manifest["note_event_count"] == 4
        assert manifest["gap_event_count"] == 0
        assert manifest["platform_coverage"]["source_app_counts"] == {
            "evernote": 1,
            "markdown": 1,
            "obsidian": 1,
            "youdao": 1,
        }
        assert set(manifest["platform_coverage"]["missing_expected_platforms"]) == {"notion"}
        assert manifest["source_audit"]["source_type"] == "authorized_notes_export"
        assert manifest["source_audit"]["resolved_input_file_count"] == 4
        assert manifest["source_audit"]["canvas_file_count"] == 1
        assert manifest["source_audit"]["canvas_note_count"] == 1
        assert manifest["source_audit"]["parsed_note_count"] == 4
        assert manifest["source_audit"]["emitted_event_count"] == 4
        assert manifest["source_audit"]["skipped_file_count"] == 1
        assert manifest["source_audit"]["skipped_reason_counts"] == {"unsupported_extension": 1}
        assert manifest["source_audit"]["skipped_extension_counts"] == {".bin": 1}
        assert len(manifest["source_audit"]["path_results"]) == 5
        assert_package_valid(out)


def test_import_notion_csv_database_and_tsv_zip_tables() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        exports = root / "exports"
        notion_dir = exports / "Notion Export"
        notion_dir.mkdir(parents=True)
        (notion_dir / "Investment Rules.csv").write_text(
            "Name,Content,Tags,Updated,URL,Ticker,Action\n"
            "买入规则,估值低于安全边际才买入,\"规则,checklist\",2026-07-08,https://notion.example/rule,600519,wait\n"
            "复盘模板,记录买入理由、错因和仓位,\"复盘,模板\",2026-07-09,https://notion.example/review,300750,review\n",
            encoding="utf-8",
        )
        zip_path = exports / "notion-tables.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(
                "Notion Export/valuation.tsv",
                "标题\t正文\t标签\t更新时间\t股票\n"
                "估值假设\tDCF、PE、现金流和安全边际\t估值;研究\t2026-07-10\tSH600519\n",
            )

        export = root / "notes.json"
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "import",
                "--input",
                str(exports),
                "--source-app",
                "auto",
                "--export",
                str(export),
                "--out-dir",
                str(out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 3
        assert {event["data"]["source_app"] for event in events} == {"notion"}
        assert {event["data"]["title"] for event in events} == {"买入规则", "复盘模板", "估值假设"}
        rule_event = next(event for event in events if event["data"]["title"] == "买入规则")
        assert "Ticker: 600519" in rule_event["data"]["content_preview"]
        assert "Action: wait" in rule_event["data"]["content_preview"]
        assert rule_event["data"]["tags"] == ["checklist", "规则"]
        assert all("content" not in event["data"] for event in events)
        zip_event = next(event for event in events if event["data"]["title"] == "估值假设")
        assert zip_event["raw_ref"]["archive_member"] == "Notion Export/valuation.tsv"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 3
        assert manifest["note_event_count"] == 3
        assert manifest["gap_event_count"] == 0
        audit = manifest["source_audit"]
        assert audit["extension_counts"] == {".csv": 1, ".zip": 1}
        assert audit["table_import_supported"] is True
        assert audit["table_file_count"] == 2
        assert audit["table_row_count"] == 3
        assert audit["table_note_count"] == 3
        assert audit["path_results"][0]["parser"] == "table"
        assert audit["path_results"][0]["table_row_count"] == 2
        assert audit["archive_member_event_count"] == 1
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["notion"]
        assert manifest["content_policy"]["full_content_event_count"] == 0
        assert_package_valid(out)


def test_import_note_source_policy_filters_by_source_path_and_tag() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        exports = root / "exports"
        notion_dir = exports / "Notion Export"
        notion_dir.mkdir(parents=True)
        (notion_dir / "Investment Rules.csv").write_text(
            "Name,Content,Tags,Updated\n"
            "买入规则,估值低于安全边际才买入,\"规则,checklist\",2026-07-08\n"
            "生活清单,周末买菜,\"生活\",2026-07-08\n",
            encoding="utf-8",
        )
        (exports / "youdao.json").write_text(
            json.dumps({"notes": [{"source": "有道云笔记", "title": "规则旁注", "content": "#规则 估值和复盘"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        zip_path = exports / "notion-scope.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("Notion Export/valuation.md", "# 估值规则\n#规则\n现金流和安全边际\n")

        export = root / "notes.json"
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "import",
                "--input",
                str(exports),
                "--source-app",
                "auto",
                "--allow-source-app",
                "notion",
                "--allow-path",
                "Notion Export",
                "--allow-tag",
                "规则",
                "--deny-tag",
                "生活",
                "--export",
                str(export),
                "--out-dir",
                str(out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 2
        assert {event["data"]["source_app"] for event in events} == {"notion"}
        assert {event["data"]["title"] for event in events} == {"买入规则", "估值规则"}
        assert not any(event["data"]["title"] == "生活清单" for event in events)
        assert not any(event["data"]["title"] == "规则旁注" for event in events)
        zip_event = next(event for event in events if event["data"]["title"] == "估值规则")
        assert zip_event["raw_ref"]["source_archive"] == str(zip_path)
        assert zip_event["raw_ref"]["archive_member"] == "Notion Export/valuation.md"

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["source_audit"]
        policy = audit["note_source_policy"]
        assert manifest["event_count"] == 2
        assert manifest["note_event_count"] == 2
        assert manifest["gap_event_count"] == 0
        assert manifest["collection_readiness"]["status"] == "events_collected"
        assert audit["candidate_note_count"] == 4
        assert audit["parsed_note_count"] == 2
        assert audit["archive_member_event_count"] == 1
        assert policy["enabled"] is True
        assert policy["allow_source_apps"] == ["notion"]
        assert policy["allow_paths"] == ["Notion Export"]
        assert policy["allow_tags"] == ["规则"]
        assert policy["deny_tags"] == ["生活"]
        assert policy["filtered_note_count"] == 2
        assert policy["filter_reason_counts"] == {"source_app_not_allowed": 1, "tag_denied": 1}
        assert policy["policy_does_not_assert_investment_relevance"] is True
        assert audit["note_source_policy_filtered_all"] is False
        assert_package_valid(out)


def test_import_note_source_policy_filtered_all_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        exports = root / "exports"
        exports.mkdir()
        (exports / "rules.md").write_text("# 交易规则\n控制仓位和回撤\n", encoding="utf-8")
        export = root / "notes.json"
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "import",
                "--input",
                str(exports),
                "--source-app",
                "auto",
                "--allow-tag",
                "不存在的标签",
                "--export",
                str(export),
                "--out-dir",
                str(out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 1
        gap = events[0]
        assert gap["schema"] == "collectorx.event.v1"
        assert gap["collector"] == "notes"
        assert gap["kind"] == "profile"
        assert gap["time"]
        assert gap["collected_at"]
        assert gap["data"]["subtype"] == "collector_gap"
        assert gap["data"]["action_type"] == "collector_gap"
        assert gap["data"]["gap"] == "notes_source_policy_filtered_all"
        assert gap["data"]["status"] == "source_policy_filtered_all"
        assert gap["data"]["profile_type"] == "notes_collection_gap"
        assert gap["data"]["candidate_note_count"] == 1
        assert gap["data"]["note_event_count"] == 0
        assert gap["data"]["source_policy_filtered_note_count"] == 1
        assert gap["data"]["source_policy_filter_reason_counts"] == {"tag_not_allowed": 1}
        assert gap["data"]["policy_is_user_authorization_scope"] is True
        assert gap["data"]["policy_does_not_assert_investment_relevance"] is True
        assert gap["data"]["investment_note_fact_claimed"] is False
        assert gap["data"]["complete_notes_vault_claimed"] is False
        assert gap["data"]["full_content_collected"] is False
        assert gap["raw_ref"] == {
            "preflight": True,
            "reason": "notes_source_policy_filtered_all",
            "source_policy_enabled": True,
        }
        assert "collection_gap" in gap["privacy"]["contains"]
        assert gap["wiki_targets"] == ["collectorx.data_quality.collection_gaps"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["note_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["kind_counts"] == {"profile": 1}
        assert manifest["collection_readiness"]["status"] == "source_policy_filtered_all"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        audit = manifest["source_audit"]
        assert audit["candidate_note_count"] == 1
        assert audit["parsed_note_count"] == 0
        assert audit["emitted_event_count"] == 1
        assert audit["note_source_policy_filtered_all"] is True
        assert audit["note_source_policy"]["filtered_note_count"] == 1
        assert audit["note_source_policy"]["filter_reason_counts"] == {"tag_not_allowed": 1}
        assert_package_valid(out)


def test_import_zip_and_all_expected_platform_coverage() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        exports = root / "exports"
        exports.mkdir()
        (exports / "obsidian-review.md").write_text("# 复盘\n组合调整纪律\n", encoding="utf-8")
        (exports / "youdao.json").write_text(
            json.dumps({"notes": [{"source": "有道云笔记", "title": "煤炭跟踪", "content": "供需和估值"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        (exports / "evernote.enex").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<en-export>
  <note>
    <title>银行股规则</title>
    <content><![CDATA[<en-note>分红率和资产质量 checklist</en-note>]]></content>
  </note>
</en-export>
""",
            encoding="utf-8",
        )
        zip_path = exports / "notion-export.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("Notion Export/半导体研究.md", "# 半导体研究\n库存周期和订单验证\n")
            archive.writestr("../unsafe.md", "# 不应读取\n")
            archive.writestr("..\\windows-traversal.md", "# 不应读取\n")
            archive.writestr("C:\\unsafe.md", "# 不应读取\n")

        export = root / "notes.json"
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "import",
                "--input",
                str(exports),
                "--source-app",
                "auto",
                "--export",
                str(export),
                "--out-dir",
                str(out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 4
        assert {event["data"]["source_app"] for event in events} == {"obsidian", "notion", "youdao", "evernote"}
        assert all("../unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("windows-traversal" not in (event["raw_ref"].get("path") or "") for event in events)
        assert all("C:/unsafe" not in (event["raw_ref"].get("path") or "") for event in events)
        notion_event = next(event for event in events if event["data"]["source_app"] == "notion")
        assert notion_event["raw_ref"]["source_archive"] == str(zip_path)
        assert notion_event["raw_ref"]["archive_member"] == "Notion Export/半导体研究.md"
        assert notion_event["data"]["path"] == f"{zip_path}::Notion Export/半导体研究.md"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 4
        assert manifest["note_event_count"] == 4
        assert manifest["gap_event_count"] == 0
        assert manifest["platform_coverage"]["observed_expected_platforms"] == ["obsidian", "notion", "youdao", "evernote"]
        assert manifest["platform_coverage"]["missing_expected_platforms"] == []
        assert manifest["collection_readiness"]["platform_coverage_status"] == "all_expected_platforms_observed"
        assert manifest["platform_coverage"]["real_account_validation"] is False
        assert manifest["field_coverage"]["field_counts"]["source_app"] == 4
        assert manifest["field_coverage"]["field_counts"]["content_length"] == 4
        assert manifest["source_audit"]["archive_member_event_count"] == 1
        assert manifest["source_audit"]["archive_member_count"] == 4
        assert manifest["source_audit"]["skipped_archive_member_count"] == 3
        assert manifest["source_audit"]["skipped_archive_member_reason_counts"] == {"unsafe_path": 3}
        assert manifest["source_audit"]["archive_count"] == 1
        assert manifest["source_audit"]["archive_path_traversal_members_collected"] is False
        assert manifest["source_audit"]["windows_drive_archive_members_collected"] is False
        assert len(manifest["source_audit"]["path_results"]) == 4
        assert manifest["content_policy"]["full_content_event_count"] == 0
        assert manifest["content_policy"]["investment_classification_done"] is False
        assert_package_valid(out)


def test_import_missing_input_has_source_audit_gap() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        missing = root / "missing-export"
        export = root / "notes.json"
        out = root / "out"
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "import",
                "--input",
                str(missing),
                "--source-app",
                "auto",
                "--export",
                str(export),
                "--out-dir",
                str(out),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = read_events(out)
        assert len(events) == 1
        gap = events[0]
        assert gap["kind"] == "profile"
        assert gap["data"]["subtype"] == "collector_gap"
        assert gap["data"]["gap"] == "notes_authorized_input_missing"
        assert gap["data"]["status"] == "needs_authorized_notes_input"
        assert gap["data"]["candidate_note_count"] == 0
        assert gap["data"]["note_event_count"] == 0
        assert gap["data"]["policy_does_not_assert_investment_relevance"] is True
        assert gap["data"]["complete_notes_vault_claimed"] is False
        assert gap["raw_ref"]["reason"] == "notes_authorized_input_missing"
        assert "collection_gap" in gap["privacy"]["contains"]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["event_count"] == 1
        assert manifest["note_event_count"] == 0
        assert manifest["gap_event_count"] == 1
        assert manifest["collection_readiness"]["status"] == "needs_authorized_notes_input"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is False
        assert manifest["source_audit"]["input_exists"] is False
        assert manifest["source_audit"]["input_kind"] == "missing"
        assert manifest["source_audit"]["emitted_event_count"] == 1
        assert manifest["source_audit"]["skipped_reason_counts"] == {"input_missing": 1}
        assert manifest["source_audit"]["path_results"][0]["status"] == "missing"
        assert_package_valid(out)


if __name__ == "__main__":
    test_obsidian_outputs_collectorx_events_without_full_content_by_default()
    test_notes_investment_fixture_flows_into_investment_notes_lens()
    test_import_outputs_youdao_evernote_and_markdown_events()
    test_import_notion_csv_database_and_tsv_zip_tables()
    test_import_note_source_policy_filters_by_source_path_and_tag()
    test_import_note_source_policy_filtered_all_status()
    test_import_zip_and_all_expected_platform_coverage()
    test_import_missing_input_has_source_audit_gap()
    print("notes-collector tests passed.")
