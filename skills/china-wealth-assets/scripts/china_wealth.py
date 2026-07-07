#!/usr/bin/env python3
"""CLI for China fund and wealth asset collection."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from china_wealth.parser import build_evidence, build_manifest, collect_from_inputs_with_audit, now_iso


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
    write_jsonl(out / "lake" / "china-wealth-assets" / "events.jsonl", events)
    manifest = build_manifest(events, collected_at=collected_at, collection_audit=collection_audit)
    evidence = build_evidence(events, generated_at=collected_at)
    write_json(out / "manifest.json", manifest)
    write_json(out / "investor_wiki_evidence.v1.json", evidence)
    (out / "SUMMARY.md").write_text(
        "\n".join(
            [
                "# 中国基金理财资产采集包",
                "",
                f"- 事件数：{len(events)}",
                "- 用途：补齐券商账户之外的基金、理财和现金管理资产边界。",
                "- 边界：不采支付密码、银行密码、消费流水；不声明完整资产边界，除非平台级真实验证完成。",
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
    lake_root = soulmirror_root / "lake" / "china-wealth-assets"
    run_dir = lake_root / run_id
    latest_dir = lake_root / "latest"
    root_event_file = lake_root / "events.jsonl"
    files = [
        output_dir / "manifest.json",
        output_dir / "investor_wiki_evidence.v1.json",
        output_dir / "SUMMARY.md",
        output_dir / "lake" / "china-wealth-assets" / "events.jsonl",
    ]
    copied: list[str] = []
    for dest_root in (run_dir, latest_dir):
        dest_root.mkdir(parents=True, exist_ok=True)
        for source in files:
            if source.exists():
                dest = dest_root / source.name
                shutil.copy2(source, dest)
                copied.append(str(dest))
    event_source = output_dir / "lake" / "china-wealth-assets" / "events.jsonl"
    if event_source.exists():
        lake_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(event_source, root_event_file)
        copied.append(str(root_event_file))
    bridge_manifest = {
        "schema": "finclaw.soulmirror_bridge.v1",
        "collector": "china-wealth-assets",
        "synced_at": now_iso(),
        "source_output": str(output_dir),
        "soulmirror_home": str(soulmirror_root),
        "run_dir": str(run_dir),
        "latest_dir": str(latest_dir),
        "root_event_file": str(root_event_file),
        "copied_files": sorted(set(copied)),
        "note": "Copied China wealth/fund asset evidence into SoulMirror lake only; final wiki organization remains app-controlled.",
    }
    write_json(output_dir / "soulmirror_sync.json", bridge_manifest)
    write_json(latest_dir / "soulmirror_sync.json", bridge_manifest)
    return bridge_manifest


def collect(args: argparse.Namespace) -> int:
    collected_at = args.collected_at or now_iso()
    events, collection_audit = collect_from_inputs_with_audit(args.input or [], collected_at=collected_at, limit=args.limit)
    package_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    if args.sync_soulmirror and package_dir is None:
        run_id = re.sub(r"[^0-9A-Za-z_.-]+", "-", collected_at).strip("-")
        package_dir = Path.home() / ".collectorx" / "runs" / "china-wealth-assets" / run_id
    if package_dir is not None:
        write_package(package_dir, events, collected_at=collected_at, collection_audit=collection_audit)
        if args.sync_soulmirror:
            sync_report = sync_package_to_soulmirror(package_dir, soulmirror_home=Path(args.soulmirror_home).expanduser() if args.soulmirror_home else None)
            print(f"SoulMirror lake 同步: {sync_report['latest_dir']}")
    if args.event_export:
        write_jsonl(Path(args.event_export).expanduser(), events)
    print(json.dumps({"event_count": len(events), "collector": "china-wealth-assets", "out_dir": str(package_dir) if package_dir else None}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect user-authorized China fund and wealth assets.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("collect", help="Parse fund/wealth exports.")
    p.add_argument("--input", action="append", help="Authorized export file/folder.")
    p.add_argument("--out-dir")
    p.add_argument("--event-export")
    p.add_argument("--sync-soulmirror", action="store_true", help="采集后把事件和投资证据包同步到 ~/.soulmirror/lake/china-wealth-assets")
    p.add_argument("--soulmirror-home", help="SoulMirror 根目录，默认 ~/.soulmirror")
    p.add_argument("--limit", type=int)
    p.add_argument("--collected-at")
    p.set_defaults(func=collect)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
