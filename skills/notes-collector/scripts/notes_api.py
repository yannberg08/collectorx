#!/usr/bin/env python3
"""
笔记采集器 - 支持 Notion/Obsidian/有道云/印象笔记/ZIP 授权导出
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

from notes.events import notes_to_events, write_jsonl, write_package
from notes.parser import parse_notes_export_with_audit

# Windows控制台utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def collect_obsidian(
    vault_path: str,
    export_path: str,
    limit: int = None,
    event_export: str = None,
    out_dir: str = None,
    include_content: bool = False,
):
    """采集Obsidian笔记（本地文件）"""
    vault = Path(vault_path)
    if not vault.exists():
        print(f"ERROR: Vault目录不存在: {vault_path}")
        return
    
    notes = []
    md_files = sorted(vault.rglob("*.md"))
    total_md_files = len(md_files)
    
    if limit:
        md_files = md_files[:limit]
    audit = {
        "source_type": "obsidian_vault",
        "input": str(vault),
        "input_exists": True,
        "input_kind": "directory",
        "input_count": 1,
        "resolved_input_file_count": len(md_files),
        "source_app": "obsidian",
        "limit": limit,
        "limit_reached": bool(limit and total_md_files > len(md_files)),
        "extension_counts": {".md": len(md_files)} if md_files else {},
        "skipped_extension_counts": {},
        "skipped_reason_counts": {},
        "skipped_file_count": 0,
        "archive_count": 0,
        "archive_member_count": 0,
        "archive_member_event_count": 0,
        "skipped_archive_member_count": 0,
        "skipped_archive_member_reason_counts": {},
        "archive_path_traversal_members_collected": False,
        "windows_drive_archive_members_collected": False,
        "parsed_note_count": 0,
        "path_results": [],
        "unvisited_input_file_count_due_limit": max(0, total_md_files - len(md_files)),
    }
    skipped_reason_counts: Counter[str] = Counter()
    
    for md_file in md_files:
        result = {"path": str(md_file), "extension": ".md", "status": "pending"}
        try:
            content = md_file.read_text(encoding="utf-8")
            note = {
                "path": str(md_file.relative_to(vault)),
                "name": md_file.stem,
                "content": content,
                "mtime": md_file.stat().st_mtime
            }
            notes.append(note)
            result.update({"status": "parsed", "parsed_note_count": 1})
        except Exception as e:
            print(f"读取失败 {md_file}: {e}")
            audit["skipped_file_count"] += 1
            skipped_reason_counts["read_error"] += 1
            result.update({"status": "read_error", "reason": "read_error", "parsed_note_count": 0})
        audit["path_results"].append(result)
    audit["parsed_note_count"] = len(notes)
    audit["skipped_reason_counts"] = dict(sorted(skipped_reason_counts.items()))
    
    # 导出
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)

    events = notes_to_events(
        notes,
        source_app="obsidian",
        source_label=f"Obsidian vault: {vault.name}",
        include_content=include_content,
    )
    audit["emitted_event_count"] = len(events)
    if event_export:
        write_jsonl(Path(event_export).expanduser(), events)
    if out_dir:
        write_package(Path(out_dir).expanduser(), events, source_app="obsidian", collection_audit=audit)
    
    print(f"导出完成: {len(notes)} 篇笔记 -> {export_path}")


def collect_notion(
    token: str = None,
    export_path: str = None,
    limit: int = None,
    event_export: str = None,
    out_dir: str = None,
    include_content: bool = False,
    token_env: str = None,
):
    """采集Notion笔记（通过API）"""
    import urllib.request

    token = resolve_notion_token(token, token_env)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28"
    }
    
    # 搜索所有页面
    url = "https://api.notion.com/v1/search"
    data = json.dumps({"page_size": 100}).encode()
    
    req = urllib.request.Request(url, data=data, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
        
        pages = result.get("results", [])
        if limit:
            pages = pages[:limit]
        
        notes = []
        for page in pages:
            note = {
                "id": page["id"],
                "title": _extract_notion_title(page),
                "url": page.get("url", ""),
                "created": page.get("created_time", ""),
                "last_edited": page.get("last_edited_time", "")
            }
            notes.append(note)
        audit = {
            "source_type": "notion_api",
            "input": "notion_api_search",
            "input_exists": True,
            "input_kind": "api",
            "input_count": 1,
            "resolved_input_file_count": 0,
            "source_app": "notion",
            "limit": limit,
            "limit_reached": False,
            "parsed_note_count": len(notes),
            "emitted_event_count": 0,
            "skipped_file_count": 0,
            "skipped_reason_counts": {},
            "archive_count": 0,
            "archive_member_count": 0,
            "archive_member_event_count": 0,
            "skipped_archive_member_count": 0,
            "skipped_archive_member_reason_counts": {},
            "archive_path_traversal_members_collected": False,
            "windows_drive_archive_members_collected": False,
            "path_results": [],
        }
        
        # 导出
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)

        events = notes_to_events(
            notes,
            source_app="notion",
            source_label="Notion API",
            include_content=include_content,
        )
        audit["emitted_event_count"] = len(events)
        if event_export:
            write_jsonl(Path(event_export).expanduser(), events)
        if out_dir:
            write_package(Path(out_dir).expanduser(), events, source_app="notion", collection_audit=audit)
        
        print(f"导出完成: {len(notes)} 篇笔记 -> {export_path}")
        
    except Exception as e:
        print(f"采集失败: {e}")


def collect_import(
    input_path: str,
    source_app: str,
    export_path: str,
    limit: int = None,
    event_export: str = None,
    out_dir: str = None,
    include_content: bool = False,
):
    """采集用户授权的笔记导出文件/目录。"""
    notes, collection_audit = parse_notes_export_with_audit(input_path, source_app=source_app, limit=limit)
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)

    package_source = source_app if source_app != "auto" else "notes-export"
    events = notes_to_events(
        notes,
        source_app=package_source,
        source_label=f"Notes export: {package_source}",
        include_content=include_content,
    )
    collection_audit["emitted_event_count"] = len(events)
    if event_export:
        write_jsonl(Path(event_export).expanduser(), events)
    if out_dir:
        write_package(Path(out_dir).expanduser(), events, source_app=package_source, collection_audit=collection_audit)
    print(f"导出完成: {len(notes)} 篇笔记 -> {export_path}")


def _extract_notion_title(page):
    """提取Notion页面标题"""
    props = page.get("properties", {})
    for prop_name, prop_value in props.items():
        if prop_value.get("type") == "title":
            title_parts = prop_value.get("title", [])
            return "".join(part.get("plain_text", "") for part in title_parts)
    return page.get("id", "Untitled")


def resolve_notion_token(token: str = None, token_env: str = None) -> str:
    if token_env:
        token = os.environ.get(token_env)
        if not token:
            raise ValueError(f"环境变量未设置或为空: {token_env}")
    if not token:
        raise ValueError("缺少 Notion API Token。推荐使用 --token-env 指向环境变量。")
    return token


def cmd_status():
    """显示状态"""
    print("笔记采集器")
    print("支持: Notion/Obsidian/有道云/印象笔记/ZIP授权导出")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="笔记采集器")
    subparsers = parser.add_subparsers(dest="command")
    
    # obsidian命令
    obs_parser = subparsers.add_parser("obsidian", help="采集Obsidian笔记")
    obs_parser.add_argument("--vault", required=True, help="Vault目录")
    obs_parser.add_argument("--export", required=True, help="导出路径")
    obs_parser.add_argument("--limit", type=int, help="限制数量")
    obs_parser.add_argument("--event-export", help="导出 CollectorX Event JSONL")
    obs_parser.add_argument("--out-dir", help="导出完整采集包目录")
    obs_parser.add_argument("--include-content", action="store_true", help="在事件中包含完整笔记正文；默认只放预览")
    
    # notion命令
    not_parser = subparsers.add_parser("notion", help="采集Notion笔记")
    not_parser.add_argument("--token", help="API Token；推荐改用 --token-env，避免明文进入命令历史")
    not_parser.add_argument("--token-env", help="保存 Notion API Token 的环境变量名")
    not_parser.add_argument("--export", required=True, help="导出路径")
    not_parser.add_argument("--limit", type=int, help="限制数量")
    not_parser.add_argument("--event-export", help="导出 CollectorX Event JSONL")
    not_parser.add_argument("--out-dir", help="导出完整采集包目录")
    not_parser.add_argument("--include-content", action="store_true", help="在事件中包含完整笔记正文；默认只放预览")

    # import命令
    import_parser = subparsers.add_parser("import", help="导入授权笔记导出文件/目录")
    import_parser.add_argument("--input", required=True, help="导出文件或目录，支持 md/html/txt/json/jsonl/csv/tsv/enex/zip")
    import_parser.add_argument("--source-app", default="auto", choices=["auto", "notion", "obsidian", "youdao", "evernote", "markdown", "notes-export"], help="来源应用")
    import_parser.add_argument("--export", required=True, help="标准化 JSON 导出路径")
    import_parser.add_argument("--limit", type=int, help="限制数量")
    import_parser.add_argument("--event-export", help="导出 CollectorX Event JSONL")
    import_parser.add_argument("--out-dir", help="导出完整采集包目录")
    import_parser.add_argument("--include-content", action="store_true", help="在事件中包含完整笔记正文；默认只放预览")
    
    # status命令
    subparsers.add_parser("status", help="显示状态")
    
    args = parser.parse_args()
    
    if args.command == "obsidian":
        collect_obsidian(args.vault, args.export, args.limit, args.event_export, args.out_dir, args.include_content)
    elif args.command == "notion":
        collect_notion(args.token, args.export, args.limit, args.event_export, args.out_dir, args.include_content, args.token_env)
    elif args.command == "import":
        collect_import(args.input, args.source_app, args.export, args.limit, args.event_export, args.out_dir, args.include_content)
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
