#!/usr/bin/env python3
"""Project-level validation for CollectorX."""

from __future__ import annotations

import py_compile
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
MIN_PYTHON = (3, 10)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectorx.investor_wiki import validate_evidence_file
from tools.validate_collector_package import validate_package

PY_COMPILE_EXCLUDES = {".git", ".venv", "__pycache__", ".pytest_cache"}

CLI_HELP_TARGETS = [
    "tools/validate_collector_package.py",
    "tools/validate_investor_wiki_evidence.py",
    "skills/wechat-export/scripts/wechat_query.py",
    "skills/feishu/scripts/feishu_api.py",
    "skills/ticktick-cli/scripts/ticktick_cli.py",
    "skills/ticktick-cli/scripts/ticktick_events.py",
    "skills/calendar-collector/scripts/calendar_query.py",
    "skills/collaboration-exports/scripts/collaboration_exports.py",
    "skills/email-collector/scripts/email_api.py",
    "skills/filesystem-collector/scripts/filesystem_query.py",
    "skills/meeting-artifacts/scripts/meeting_artifacts.py",
    "skills/wechat-favorites/scripts/wechat_favorites.py",
    "skills/qq-export/scripts/qq_query.py",
    "skills/notes-collector/scripts/notes_api.py",
    "skills/ths-portfolio/scripts/ths_query.py",
    "skills/ths-watchlist/scripts/ths_watchlist.py",
    "skills/eastmoney-portfolio/scripts/eastmoney_query.py",
    "skills/xueqiu-watchlist/scripts/xueqiu_query.py",
    "skills/xueqiu-investor-activity/scripts/xueqiu_activity.py",
    "skills/china-wealth-assets/scripts/china_wealth.py",
    "skills/financial-news-usage/scripts/financial_news_usage.py",
    "skills/hk-us-brokerage/scripts/hk_us_brokerage.py",
    "skills/pro-terminal-usage/scripts/pro_terminal_usage.py",
    "skills/social-activity/scripts/social_activity.py",
    "skills/investor-source-collectors/scripts/investor_sources.py",
]

PARSER_TESTS = [
    "tools/test_collector_package_validator.py",
    "tools/test_investor_wiki_contract.py",
    "skills/email-collector/tests/test_events.py",
    "skills/feishu/tests/test_feishu_collect.py",
    "skills/filesystem-collector/tests/test_filesystem_collector.py",
    "skills/meeting-artifacts/tests/test_meeting_artifacts.py",
    "skills/wechat-export/tests/test_collect_package.py",
    "skills/wechat-favorites/tests/test_wechat_favorites.py",
    "skills/qq-export/tests/test_parser.py",
    "skills/notes-collector/tests/test_notes_collector.py",
    "skills/ticktick-cli/scripts/test_ticktick_events.py",
    "skills/ticktick-cli/scripts/test_ticktick_api_client.py",
    "skills/ticktick-cli/scripts/test_collect_for_soulmirror.py",
    "skills/calendar-collector/tests/test_calendar_collector.py",
    "skills/collaboration-exports/tests/test_collaboration_exports.py",
    "skills/ths-portfolio/tests/test_parser.py",
    "skills/ths-watchlist/tests/test_ths_watchlist.py",
    "skills/eastmoney-portfolio/tests/test_parser.py",
    "skills/xueqiu-watchlist/tests/test_parser.py",
    "skills/xueqiu-investor-activity/tests/test_xueqiu_activity.py",
    "skills/china-wealth-assets/tests/test_china_wealth.py",
    "skills/financial-news-usage/tests/test_financial_news_usage.py",
    "skills/hk-us-brokerage/tests/test_hk_us_brokerage.py",
    "skills/pro-terminal-usage/tests/test_pro_terminal_usage.py",
    "skills/social-activity/tests/test_social_activity.py",
    "skills/investor-source-collectors/tests/test_investor_sources.py",
]

EVENT_REQUIRED_KEYS = {
    "schema",
    "id",
    "collector",
    "source",
    "owner_scope",
    "kind",
    "time",
    "collected_at",
    "data",
    "raw_ref",
    "privacy",
}

EVENT_KINDS = {
    "message",
    "file",
    "note",
    "email",
    "calendar",
    "task",
    "trade",
    "holding",
    "watchlist",
    "a2a",
    "profile",
    "other",
}

EXECUTABLE_TARGETS = [
    "skills/doubao-chat-export/scripts/bin/doubao-export-darwin-amd64",
    "skills/doubao-chat-export/scripts/bin/doubao-export-darwin-arm64",
    "skills/doubao-chat-export/scripts/bin/doubao-export-linux-amd64",
]


def check_python_version() -> None:
    if sys.version_info < MIN_PYTHON:
        major, minor = MIN_PYTHON
        raise SystemExit(
            f"CollectorX validation requires Python {major}.{minor}+; "
            f"current interpreter is {sys.version.split()[0]}"
        )


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.py"):
        if any(part in PY_COMPILE_EXCLUDES for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def run(cmd: list[str], *, cwd: Path = ROOT) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(cwd), check=True)


def check_no_ds_store() -> None:
    bad = sorted(ROOT.rglob(".DS_Store"))
    if bad:
        rel = "\n".join(str(p.relative_to(ROOT)) for p in bad)
        raise SystemExit(f".DS_Store files must not be committed:\n{rel}")


def compile_python() -> None:
    for path in iter_python_files():
        rel = path.relative_to(ROOT)
        print(f"py_compile {rel}", flush=True)
        py_compile.compile(str(path), doraise=True)


def check_cli_help() -> None:
    for rel in CLI_HELP_TARGETS:
        run([PYTHON, rel, "--help"])


def check_prebuilt_executables() -> None:
    for rel in EXECUTABLE_TARGETS:
        path = ROOT / rel
        if not path.exists():
            raise SystemExit(f"Missing prebuilt executable: {rel}")
        if not os.access(path, os.X_OK):
            raise SystemExit(f"Prebuilt executable is not executable: {rel}")


def run_parser_tests() -> None:
    for rel in PARSER_TESTS:
        run([PYTHON, rel])


def validate_event_examples() -> None:
    samples = sorted((ROOT / "examples" / "events").glob("*.json"))
    if not samples:
        raise SystemExit("No event examples found.")

    for path in samples:
        rel = path.relative_to(ROOT)
        print(f"validate_event {rel}", flush=True)
        event = json.loads(path.read_text(encoding="utf-8"))
        missing = EVENT_REQUIRED_KEYS.difference(event)
        if missing:
            raise SystemExit(f"{rel} missing required keys: {sorted(missing)}")
        if event["schema"] != "collectorx.event.v1":
            raise SystemExit(f"{rel} has invalid schema: {event['schema']}")
        if event["kind"] not in EVENT_KINDS:
            raise SystemExit(f"{rel} has invalid kind: {event['kind']}")
        privacy = event.get("privacy")
        if not isinstance(privacy, dict):
            raise SystemExit(f"{rel} privacy must be an object")
        for key in ("sensitive", "local_only"):
            if not isinstance(privacy.get(key), bool):
                raise SystemExit(f"{rel} privacy.{key} must be boolean")


def validate_investor_catalog() -> None:
    path = ROOT / "collectors" / "finclaw-investor-catalog.json"
    print(f"validate_catalog {path.relative_to(ROOT)}", flush=True)
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema") != "collectorx.finclaw_investor_catalog.v1":
        raise SystemExit("FinClaw investor catalog has an invalid schema")
    entries = catalog.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SystemExit("FinClaw investor catalog must contain entries")

    category_folder = {"generic": "generic", "vertical": "vertical", "lens": "lenses"}
    collector_files = {
        path.stem
        for folder in category_folder.values()
        for path in (ROOT / "collectors" / folder).glob("*.yaml")
    }
    required_fields = {
        "id",
        "priority",
        "category",
        "skill",
        "readiness",
        "gate",
        "finclaw_action",
        "cli",
        "collects",
        "must_not_collect",
        "production_gap",
    }
    expected_priorities = {"P0", "P1", "P2", "supporting"}
    expected_categories = {"generic", "vertical", "lens"}
    expected_readiness = set(catalog.get("readiness_levels") or {})
    ids: set[str] = set()
    priorities: dict[str, int] = {"P0": 0, "P1": 0, "P2": 0}

    for entry in entries:
        missing = required_fields.difference(entry)
        if missing:
            raise SystemExit(f"Catalog entry missing fields: {sorted(missing)}")
        cid = entry["id"]
        if cid in ids:
            raise SystemExit(f"Duplicate catalog entry id: {cid}")
        ids.add(cid)
        if cid not in collector_files:
            raise SystemExit(f"Catalog entry has no collector YAML: {cid}")
        if entry["priority"] not in expected_priorities:
            raise SystemExit(f"Catalog entry {cid} has invalid priority")
        if entry["category"] not in expected_categories:
            raise SystemExit(f"Catalog entry {cid} has invalid category")
        category_path = ROOT / "collectors" / category_folder[entry["category"]] / f"{cid}.yaml"
        if not category_path.exists():
            raise SystemExit(f"Catalog entry {cid} category does not match collector YAML folder")
        if entry["readiness"] not in expected_readiness:
            raise SystemExit(f"Catalog entry {cid} has unknown readiness: {entry['readiness']}")
        skill_dir = ROOT / "skills" / entry["skill"]
        if not (skill_dir / "SKILL.md").exists():
            raise SystemExit(f"Catalog entry {cid} references missing skill: {entry['skill']}")
        cli = str(entry["cli"])
        script_refs = extract_catalog_script_refs(cli, entry["skill"])
        if not script_refs:
            raise SystemExit(f"Catalog entry {cid} CLI does not reference a runnable script")
        for script in script_refs:
            if not script.exists():
                raise SystemExit(f"Catalog entry {cid} references missing script: {script.relative_to(ROOT)}")
        if entry["category"] == "lens" and f"--source {cid}" not in cli:
            raise SystemExit(f"Catalog lens entry {cid} CLI must include --source {cid}")
        if not cli.startswith("SoulMirror") and "<out-dir>" not in cli:
            raise SystemExit(f"Catalog entry {cid} CLI must declare <out-dir> output")
        if cli.startswith("SoulMirror"):
            text = category_path.read_text(encoding="utf-8")
            if "apiVersion: soulmirror/v1" not in text:
                raise SystemExit(f"Catalog entry {cid} uses SoulMirror CLI but YAML is not soulmirror/v1")
        if entry["priority"] in priorities:
            priorities[entry["priority"]] += 1

    for priority, count in priorities.items():
        if count == 0:
            raise SystemExit(f"Catalog has no {priority} entries")


def validate_skill_metadata() -> None:
    catalog_path = ROOT / "collectors" / "finclaw-investor-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog_skills = sorted({entry["skill"] for entry in catalog.get("entries", [])})

    for skill in catalog_skills:
        skill_dir = ROOT / "skills" / skill
        metadata_path = skill_dir / ".collectorx.json"
        version_path = skill_dir / "VERSION"
        if not metadata_path.exists():
            raise SystemExit(f"Catalog skill is missing .collectorx.json: skills/{skill}/.collectorx.json")
        if not version_path.exists():
            raise SystemExit(f"Catalog skill is missing VERSION: skills/{skill}/VERSION")

    for metadata_path in sorted((ROOT / "skills").glob("*/.collectorx.json")):
        skill_dir = metadata_path.parent
        rel = metadata_path.relative_to(ROOT)
        print(f"validate_skill_metadata {rel}", flush=True)
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{rel} is invalid JSON: {exc}") from exc
        if not isinstance(metadata, dict):
            raise SystemExit(f"{rel} must contain a JSON object")

        version_path = skill_dir / "VERSION"
        if version_path.exists():
            expected_version = version_path.read_text(encoding="utf-8").strip()
            observed_version = metadata.get("version")
            if observed_version != expected_version:
                raise SystemExit(
                    f"{rel} version {observed_version!r} does not match "
                    f"{version_path.relative_to(ROOT)} {expected_version!r}"
                )

        if not (metadata.get("slug") or metadata.get("collector")):
            raise SystemExit(f"{rel} must declare slug or collector")
        if "description" not in metadata or not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
            raise SystemExit(f"{rel} must declare a non-empty description")


def extract_catalog_script_refs(cli: str, skill: str) -> list[Path]:
    refs: list[Path] = []
    for raw in re.findall(r"skills/[^\s`'\"]+?\.py", cli):
        refs.append(ROOT / raw)
    for raw in re.findall(r"<SKILL_DIR>/([^\s`'\"]+?\.py)", cli):
        refs.append(ROOT / "skills" / skill / raw)
    return refs


def run_first_loop_smoke_test() -> None:
    with tempfile.TemporaryDirectory(prefix="collectorx-first-loop-") as tmp:
        run([
            PYTHON,
            "tools/run_first_investor_loop.py",
            "--input-csv",
            "examples/fixtures/ths-portfolio.sample.csv",
            "--out-dir",
            tmp,
            "--collected-at",
            "2026-07-07T15:00:00+08:00",
        ])
        out = Path(tmp)
        required = [
            out / "lake" / "ths-portfolio" / "events.jsonl",
            out / "manifest.json",
            out / "wiki" / "vertical" / "investor" / "record-review" / "决策日志.md",
            out / "wiki" / "vertical" / "investor" / "risk-portfolio" / "组合约束.md",
            out / "investor_wiki_evidence.v1.json",
            out / "wiki" / "vertical" / "investor_maturity.json",
            out / "SUMMARY.md",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise SystemExit(f"First investor loop missing outputs: {missing}")

        events = (out / "lake" / "ths-portfolio" / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
        if len(events) != 4:
            raise SystemExit(f"Expected 4 first-loop events, got {len(events)}")
        evidence_errors = validate_evidence_file(out / "investor_wiki_evidence.v1.json")
        if evidence_errors:
            raise SystemExit(f"First investor loop evidence contract failed: {evidence_errors}")
        package_summary, package_errors = validate_package(out, collector="ths-portfolio", require_evidence=True)
        if package_errors:
            raise SystemExit(f"First investor loop package validation failed: {package_errors}")
        if package_summary["event_count"] != 4:
            raise SystemExit(f"First investor loop package expected 4 events, got {package_summary['event_count']}")


def main() -> int:
    check_python_version()
    check_no_ds_store()
    compile_python()
    check_cli_help()
    check_prebuilt_executables()
    run_parser_tests()
    validate_event_examples()
    validate_investor_catalog()
    validate_skill_metadata()
    run_first_loop_smoke_test()
    print("CollectorX validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
