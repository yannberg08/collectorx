#!/usr/bin/env python3
"""Project-level validation for CollectorX."""

from __future__ import annotations

import py_compile
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
MIN_PYTHON = (3, 10)

PY_COMPILE_EXCLUDES = {".git", ".venv", "__pycache__", ".pytest_cache"}

CLI_HELP_TARGETS = [
    "skills/wechat-export/scripts/wechat_query.py",
    "skills/feishu/scripts/feishu_api.py",
    "skills/ticktick-cli/scripts/ticktick_cli.py",
    "skills/ticktick-cli/scripts/ticktick_events.py",
    "skills/calendar-collector/scripts/calendar_query.py",
    "skills/email-collector/scripts/email_api.py",
    "skills/filesystem-collector/scripts/filesystem_query.py",
    "skills/meeting-artifacts/scripts/meeting_artifacts.py",
    "skills/wechat-favorites/scripts/wechat_favorites.py",
    "skills/qq-export/scripts/qq_query.py",
    "skills/notes-collector/scripts/notes_api.py",
    "skills/ths-portfolio/scripts/ths_query.py",
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
    "skills/email-collector/tests/test_events.py",
    "skills/filesystem-collector/tests/test_filesystem_collector.py",
    "skills/meeting-artifacts/tests/test_meeting_artifacts.py",
    "skills/wechat-favorites/tests/test_wechat_favorites.py",
    "skills/qq-export/tests/test_parser.py",
    "skills/notes-collector/tests/test_notes_collector.py",
    "skills/ticktick-cli/scripts/test_ticktick_events.py",
    "skills/calendar-collector/tests/test_calendar_collector.py",
    "skills/ths-portfolio/tests/test_parser.py",
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
            out / "wiki" / "vertical" / "investor" / "record-review" / "决策日志.md",
            out / "wiki" / "vertical" / "investor" / "risk-portfolio" / "组合约束.md",
            out / "wiki" / "vertical" / "investor_maturity.json",
            out / "SUMMARY.md",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise SystemExit(f"First investor loop missing outputs: {missing}")

        events = (out / "lake" / "ths-portfolio" / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
        if len(events) != 4:
            raise SystemExit(f"Expected 4 first-loop events, got {len(events)}")


def main() -> int:
    check_python_version()
    check_no_ds_store()
    compile_python()
    check_cli_help()
    check_prebuilt_executables()
    run_parser_tests()
    validate_event_examples()
    run_first_loop_smoke_test()
    print("CollectorX validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
