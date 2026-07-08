#!/usr/bin/env python3
"""CLI for Xueqiu investor activity collection."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from xueqiu_activity.parser import ACTIVITY_SCOPE_POLICY_KEYS, build_evidence, build_manifest, collect_from_inputs_with_audit, now_iso


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_package(out: Path, events: list[dict], *, collected_at: str, collection_audit: dict | None = None) -> dict:
    out = out.expanduser()
    write_jsonl(out / "lake" / "xueqiu-investor-activity" / "events.jsonl", events)
    manifest = build_manifest(events, collected_at=collected_at, collection_audit=collection_audit)
    evidence = build_evidence(events, generated_at=collected_at, collection_audit=collection_audit)
    write_json(out / "manifest.json", manifest)
    write_json(out / "investor_wiki_evidence.v1.json", evidence)
    (out / "SUMMARY.md").write_text(
        "\n".join(
            [
                "# 雪球投资者活动采集包",
                "",
                f"- 事件数：{len(events)}",
                f"- 活动覆盖证明：`{manifest['activity_boundary_proof']['overall_proof_level']}`",
                f"- 分页完整性：`{manifest['activity_boundary_proof']['pagination_completeness']['completeness_level']}`",
                "- 强交易事实：false",
                "- 边界：雪球只作为关注池、信息源、人脉网络、观点表达和组合模拟行为证据。",
                "- Wiki 写入：采集器只写 lake 和 evidence，最终 Wiki 由 SoulMirror investor-portrait 组织。",
            ]
        ),
        encoding="utf-8",
    )
    return manifest


def sync_package_to_soulmirror(output_dir: Path, *, soulmirror_home: Path | None = None) -> dict:
    output_dir = output_dir.expanduser().resolve()
    soulmirror_root = (soulmirror_home or Path.home() / ".soulmirror").expanduser()
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    collected_at = str(manifest.get("collected_at") or now_iso())
    run_id = re.sub(r"[^0-9A-Za-z_.-]+", "-", collected_at).strip("-")
    lake_root = soulmirror_root / "lake" / "xueqiu-investor-activity"
    run_dir = lake_root / run_id
    latest_dir = lake_root / "latest"
    root_event_file = lake_root / "events.jsonl"
    files = [
        output_dir / "manifest.json",
        output_dir / "investor_wiki_evidence.v1.json",
        output_dir / "SUMMARY.md",
        output_dir / "lake" / "xueqiu-investor-activity" / "events.jsonl",
    ]
    copied: list[str] = []
    for dest_root in (run_dir, latest_dir):
        dest_root.mkdir(parents=True, exist_ok=True)
        for source in files:
            if source.exists():
                dest = dest_root / source.name
                shutil.copy2(source, dest)
                copied.append(str(dest))
    event_source = output_dir / "lake" / "xueqiu-investor-activity" / "events.jsonl"
    if event_source.exists():
        lake_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(event_source, root_event_file)
        copied.append(str(root_event_file))
    bridge_manifest = {
        "schema": "finclaw.soulmirror_bridge.v1",
        "collector": "xueqiu-investor-activity",
        "synced_at": now_iso(),
        "source_output": str(output_dir),
        "soulmirror_home": str(soulmirror_root),
        "run_dir": str(run_dir),
        "latest_dir": str(latest_dir),
        "root_event_file": str(root_event_file),
        "copied_files": sorted(set(copied)),
        "note": "Copied Xueqiu investor evidence into SoulMirror lake only; final wiki organization remains app-controlled.",
    }
    write_json(output_dir / "soulmirror_sync.json", bridge_manifest)
    write_json(latest_dir / "soulmirror_sync.json", bridge_manifest)
    return bridge_manifest


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events, collection_audit = collect_from_inputs_with_audit(
        args.input or [],
        collected_at=collected_at,
        limit=args.limit,
        scope_policy=scope_policy_from_args(args),
    )
    package_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    if args.sync_soulmirror and package_dir is None:
        run_id = re.sub(r"[^0-9A-Za-z_.-]+", "-", collected_at).strip("-")
        package_dir = Path.home() / ".collectorx" / "runs" / "xueqiu-investor-activity" / run_id
    if package_dir is not None:
        write_package(package_dir, events, collected_at=collected_at, collection_audit=collection_audit)
        if args.sync_soulmirror:
            sync_report = sync_package_to_soulmirror(package_dir, soulmirror_home=Path(args.soulmirror_home).expanduser() if args.soulmirror_home else None)
            print(f"SoulMirror lake 同步: {sync_report['latest_dir']}")
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    print(json.dumps({"event_count": len(events), "collector": "xueqiu-investor-activity", "out_dir": str(package_dir) if package_dir else None}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized Xueqiu investor activity.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect", help="Parse local Xueqiu exports, saved activity files, HAR packages, or browser history copies.")
    p.add_argument("--input", action="append", help="Authorized Xueqiu export file/folder, HAR file, ZIP package, or copied Chromium/Safari browser history.")
    p.add_argument("--out-dir")
    p.add_argument("--event-export")
    p.add_argument("--sync-soulmirror", action="store_true", help="采集后把事件和投资证据包同步到 ~/.soulmirror/lake/xueqiu-investor-activity")
    p.add_argument("--soulmirror-home", help="SoulMirror 根目录，默认 ~/.soulmirror")
    p.add_argument("--limit", type=int)
    p.add_argument("--collected-at")
    add_scope_policy_args(p)
    p.set_defaults(func=collect)
    return parser


def add_scope_policy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-activity", action="append", help="Only keep matching activity types.")
    parser.add_argument("--deny-activity", action="append", help="Exclude matching activity types.")
    parser.add_argument("--allow-source-surface", action="append", help="Only keep matching source surfaces.")
    parser.add_argument("--deny-source-surface", action="append", help="Exclude matching source surfaces.")
    parser.add_argument("--allow-source-app", action="append", help="Only keep matching source apps, such as chromium_history or safari_history.")
    parser.add_argument("--deny-source-app", action="append", help="Exclude matching source apps.")
    parser.add_argument("--allow-domain", action="append", help="Only keep matching URL domains.")
    parser.add_argument("--deny-domain", action="append", help="Exclude matching URL domains.")
    parser.add_argument("--allow-symbol", action="append", help="Only keep matching symbols/codes.")
    parser.add_argument("--deny-symbol", action="append", help="Exclude matching symbols/codes.")
    parser.add_argument("--allow-author", action="append", help="Only keep matching authors, target users, or author ids.")
    parser.add_argument("--deny-author", action="append", help="Exclude matching authors, target users, or author ids.")
    parser.add_argument("--allow-keyword", action="append", help="Only keep events whose content, URL, symbols, author, portfolio, or raw preview matches keyword.")
    parser.add_argument("--deny-keyword", action="append", help="Exclude events whose content, URL, symbols, author, portfolio, or raw preview matches keyword.")


def scope_policy_from_args(args: argparse.Namespace) -> dict:
    return {key: getattr(args, key, None) for key in ACTIVITY_SCOPE_POLICY_KEYS}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
