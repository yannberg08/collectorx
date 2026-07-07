#!/usr/bin/env python3
"""
QQ聊天记录查询工具
支持QQ 9.x（NT架构）的SQLite数据库
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from qq.collect import collect_records, collect_records_to_messages, dump_collect_payload
from qq.events import messages_to_events, write_events_jsonl
from qq.keyprobe import capture_passphrase, diagnose_key_access
from qq.parser import (
    decrypt_nt_with_sqlcipher,
    find_qq_db_dir,
    get_db_path,
    normalize_messages,
    prepare_nt_clean_copies,
    probe_db_dir,
    read_nt_entities,
    read_message_rows,
)

# Windows控制台utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass


def cmd_recent(db_dir: Path, limit: int = 10):
    """查看最新消息"""
    db_path = get_db_path(db_dir)
    if not db_path:
        _print_no_readable_db_error(db_dir)
        return
    
    try:
        messages = normalize_messages(read_message_rows(db_path, limit=limit))
        for msg in messages:
            print(json.dumps(msg, ensure_ascii=False, default=str))
        
    except Exception as e:
        print(f"查询失败: {e}")


def cmd_probe(db_dir: Path):
    """只检查QQ本地数据库结构，不读取消息正文"""
    print(json.dumps(probe_db_dir(db_dir), ensure_ascii=False, indent=2))


def cmd_prepare_nt(db_dir: Path, out_dir: str, roles: str = None):
    """去掉 QQ NT 数据库 1024 字节封装头，输出仍为加密 SQLCipher 文件。"""
    include_roles = _split_csv(roles)
    manifest = prepare_nt_clean_copies(db_dir, Path(out_dir).expanduser(), include_roles=include_roles)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def cmd_decrypt_nt(
    db_dir: Path,
    out_dir: str,
    passphrase: str = None,
    passphrase_env: str = None,
    passphrase_file: str = None,
    roles: str = None,
    sqlcipher: str = "sqlcipher",
):
    """用 SQLCipher 解密 QQ NT 数据库。passphrase 不会写入输出。"""
    secret = passphrase
    if passphrase_env:
        secret = os.environ.get(passphrase_env)
    if passphrase_file and not secret:
        path = Path(passphrase_file).expanduser()
        if path.exists():
            secret = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not secret:
        print("DECRYPT-ERROR: 请通过 --passphrase-env、--passphrase-file 或 --passphrase 提供 QQ NT 数据库 passphrase")
        return
    include_roles = _split_csv(roles)
    result = decrypt_nt_with_sqlcipher(
        db_dir,
        Path(out_dir).expanduser(),
        passphrase=secret,
        include_roles=include_roles,
        sqlcipher_bin=sqlcipher,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_entities(db_dir: Path, out: str = None, limit_per_table: int = None):
    """导出解密后的 QQ NT 联系人、群和最近联系人清单。"""
    probe = probe_db_dir(db_dir)
    if probe.get("status") == "needs_decryption":
        _print_no_readable_db_error(db_dir, prefix="ENTITIES-ERROR")
        return
    payload = read_nt_entities(db_dir, limit_per_table=limit_per_table)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if out:
        output = Path(out).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(
            "ENTITIES "
            f"contacts={len(payload.get('contacts', []))} "
            f"groups={len(payload.get('groups', []))} "
            f"recent={len(payload.get('recent_contacts', []))}"
        )
    else:
        print(text)


def cmd_key_diagnose():
    """诊断 QQ NT passphrase 获取前置条件，不读取/输出密钥。"""
    print(json.dumps(diagnose_key_access(), ensure_ascii=False, indent=2))


def cmd_key_capture(out: str = None, timeout: int = 120):
    """捕获 QQ NT passphrase 到本机文件，不在终端输出密钥。"""
    target = Path(out).expanduser() if out else Path.home() / ".collectorx" / "qq" / "nt_passphrase"
    print(json.dumps(capture_passphrase(target, timeout=timeout), ensure_ascii=False, indent=2))


def cmd_search(db_dir: Path, keyword: str):
    """搜索消息"""
    db_path = get_db_path(db_dir)
    if not db_path:
        _print_no_readable_db_error(db_dir)
        return
    
    try:
        messages = normalize_messages(read_message_rows(db_path, keyword=keyword, limit=50))
        print(f"找到 {len(messages)} 条消息")
        for msg in messages:
            print(json.dumps(msg, ensure_ascii=False, default=str))
        
    except Exception as e:
        print(f"搜索失败: {e}")


def cmd_collect(
    db_dir: Path,
    *,
    out: str = None,
    pretty: bool = False,
    days: int = None,
    after: str = None,
    limit: int = None,
    exclude: str = None,
    include_groups: str = None,
    active_group_days: int = 30,
    participated_only: bool = False,
    owner_uin: str = None,
    event_export: str = None,
    collected_at: str = None,
):
    """微信采集器同构模式：输出紧凑 QQ collect JSON。"""
    db_path = get_db_path(db_dir)
    if not db_path:
        _print_no_readable_db_error(db_dir, prefix="COLLECT-ERROR")
        return

    after_ts = None
    if after:
        try:
            after_ts = datetime.strptime(after.strip(), "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            print(f"COLLECT-ERROR: bad --after {after!r}, expect 'YYYY-MM-DD HH:MM:SS'")
            return

    rows = read_message_rows(db_path)
    messages = normalize_messages(rows, owner_uin=owner_uin)
    if days is not None:
        latest_ts = max((item.get("time_ts") or 0 for item in messages), default=0)
        cutoff = latest_ts - days * 86400
        messages = [item for item in messages if (item.get("time_ts") or 0) >= cutoff]

    records = collect_records(
        messages,
        after_ts=after_ts,
        limit=limit or 0,
        exclude=exclude,
        include_groups=include_groups,
        active_group_days=active_group_days,
        participated_only=participated_only,
    )
    payload = dump_collect_payload(records, pretty=pretty)
    if out:
        output = Path(out).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        print(f"COLLECTED {len(records)}")
    else:
        print(payload)

    if event_export:
        event_messages = collect_records_to_messages(records)
        events = messages_to_events(
            event_messages,
            source="QQ collect 模式",
            raw_file=str(db_path),
            collected_at=collected_at,
        )
        write_events_jsonl(event_export, events)
        print(f"事件导出完成: {len(events)} 条 -> {event_export}")


def cmd_export(
    db_dir: Path,
    output: str,
    *,
    event_export: str = None,
    source: str = "QQ 本地聊天记录",
    collected_at: str = None,
    owner_uin: str = None,
):
    """导出聊天记录"""
    db_path = get_db_path(db_dir)
    if not db_path:
        _print_no_readable_db_error(db_dir)
        return
    
    try:
        rows = read_message_rows(db_path)
        messages = normalize_messages(rows, owner_uin=owner_uin)
        
        with open(output, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"导出完成: {len(messages)} 条消息 -> {output}")
        if event_export:
            events = messages_to_events(
                messages,
                source=source,
                raw_file=str(db_path),
                collected_at=collected_at,
            )
            write_events_jsonl(event_export, events)
            print(f"事件导出完成: {len(events)} 条 -> {event_export}")
        
    except Exception as e:
        print(f"导出失败: {e}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="QQ聊天记录查询")
    parser.add_argument("--db-dir", help="QQ数据库目录")
    
    subparsers = parser.add_subparsers(dest="command")
    
    # recent命令
    subparsers.add_parser("probe", help="检查数据库结构，不读取消息正文")
    subparsers.add_parser("key-diagnose", help="诊断QQ NT passphrase获取条件，不读取/输出密钥")
    key_capture_parser = subparsers.add_parser("key-capture", help="捕获QQ NT passphrase到本机文件，不输出密钥")
    key_capture_parser.add_argument("--out", help="passphrase写入路径，默认 ~/.collectorx/qq/nt_passphrase")
    key_capture_parser.add_argument("--timeout", type=int, default=120, help="等待捕获秒数")

    prepare_parser = subparsers.add_parser("prepare-nt", help="准备QQ NT加密库：去掉1024字节封装头")
    prepare_parser.add_argument("--out-dir", required=True, help="输出clean SQLCipher文件目录")
    prepare_parser.add_argument("--roles", help="只处理指定角色，逗号分隔，如 messages,contacts,groups")

    decrypt_parser = subparsers.add_parser("decrypt-nt", help="用SQLCipher解密QQ NT数据库到明文SQLite")
    decrypt_parser.add_argument("--out-dir", required=True, help="输出明文SQLite目录")
    decrypt_parser.add_argument("--passphrase-env", help="从环境变量读取QQ NT数据库passphrase")
    decrypt_parser.add_argument("--passphrase-file", help="从本机文件读取QQ NT数据库passphrase")
    decrypt_parser.add_argument("--passphrase", help="直接提供passphrase；不建议在共享终端使用")
    decrypt_parser.add_argument("--roles", help="只解密指定角色，逗号分隔，如 messages,contacts,groups")
    decrypt_parser.add_argument("--sqlcipher", default="sqlcipher", help="sqlcipher可执行文件路径")

    entities_parser = subparsers.add_parser("entities", help="导出解密后的联系人、群和最近联系人清单")
    entities_parser.add_argument("--out", help="写出JSON路径")
    entities_parser.add_argument("--limit-per-table", type=int, help="每张表最多读取N行，用于排查")

    # collect命令，参数对齐微信采集器
    collect_parser = subparsers.add_parser("collect", help="微信同构采集模式：输出QQ主人相关紧凑JSON")
    collect_parser.add_argument("--days", type=int, help="只采最近N天消息")
    collect_parser.add_argument("--after", help='只采该时刻之后消息，格式 "YYYY-MM-DD HH:MM:SS"')
    collect_parser.add_argument("--out", help="写出collect JSON路径")
    collect_parser.add_argument("--pretty", action="store_true", help="人工排查时输出缩进JSON；默认紧凑JSON")
    collect_parser.add_argument("--limit", type=int, help="限制输出数量")
    collect_parser.add_argument("--exclude", help="黑名单，会话名逗号分隔")
    collect_parser.add_argument("--include-groups", help="群聊白名单，逗号分隔")
    collect_parser.add_argument("--active-group-days", type=int, default=30, help="自动包含近N天主人发言过的群，0关闭")
    collect_parser.add_argument("--participated-only", action="store_true", help="只保留主人实际发过言的私聊")
    collect_parser.add_argument("--owner-uin", help="当前用户QQ号，用于判断'我'发言")
    collect_parser.add_argument("--event-export", help="同时导出CollectorX Event JSONL路径")
    collect_parser.add_argument("--collected-at", help="事件collected_at字段")

    # recent命令
    recent_parser = subparsers.add_parser("recent", help="查看最新消息")
    recent_parser.add_argument("--limit", type=int, default=10)
    
    # search命令
    search_parser = subparsers.add_parser("search", help="搜索消息")
    search_parser.add_argument("keyword", help="搜索关键词")
    
    # export命令
    export_parser = subparsers.add_parser("export", help="导出聊天记录")
    export_parser.add_argument("output", help="输出文件路径")
    export_parser.add_argument("--event-export", help="导出CollectorX Event JSONL路径")
    export_parser.add_argument("--source", default="QQ 本地聊天记录", help="事件source字段")
    export_parser.add_argument("--collected-at", help="事件collected_at字段，默认当前时间")
    export_parser.add_argument("--owner-uin", help="当前用户QQ号，用于标记sender_is_owner")
    
    args = parser.parse_args()
    
    if args.command == "key-diagnose":
        cmd_key_diagnose()
        return
    if args.command == "key-capture":
        cmd_key_capture(out=args.out, timeout=args.timeout)
        return

    # 查找数据库目录
    if args.db_dir:
        db_dir = Path(args.db_dir)
    else:
        db_dir = find_qq_db_dir()
        if not db_dir:
            if args.command == "probe":
                print(json.dumps({
                    "status": "data_dir_not_found",
                    "platform": sys.platform,
                    "message": "未找到QQ数据目录。请安装/登录QQ或手动指定 --db-dir。",
                }, ensure_ascii=False, indent=2))
                return
            print("ERROR: 未找到QQ数据目录")
            print("请手动指定 --db-dir 参数")
            sys.exit(1)
    
    print(f"使用数据库目录: {db_dir}")
    
    if args.command == "probe":
        cmd_probe(db_dir)
    elif args.command == "prepare-nt":
        cmd_prepare_nt(db_dir, args.out_dir, args.roles)
    elif args.command == "decrypt-nt":
        cmd_decrypt_nt(
            db_dir,
            args.out_dir,
            passphrase=args.passphrase,
            passphrase_env=args.passphrase_env,
            passphrase_file=args.passphrase_file,
            roles=args.roles,
            sqlcipher=args.sqlcipher,
        )
    elif args.command == "entities":
        cmd_entities(db_dir, out=args.out, limit_per_table=args.limit_per_table)
    elif args.command == "collect":
        cmd_collect(
            db_dir,
            out=args.out,
            pretty=args.pretty,
            days=args.days,
            after=args.after,
            limit=args.limit,
            exclude=args.exclude,
            include_groups=args.include_groups,
            active_group_days=args.active_group_days,
            participated_only=args.participated_only,
            owner_uin=args.owner_uin,
            event_export=args.event_export,
            collected_at=args.collected_at,
        )
    elif args.command == "recent":
        cmd_recent(db_dir, args.limit)
    elif args.command == "search":
        cmd_search(db_dir, args.keyword)
    elif args.command == "export":
        cmd_export(
            db_dir,
            args.output,
            event_export=args.event_export,
            source=args.source,
            collected_at=args.collected_at,
            owner_uin=args.owner_uin,
        )
    else:
        parser.print_help()


def _split_csv(value: str = None):
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _print_no_readable_db_error(db_dir: Path, prefix: str = "ERROR"):
    probe = probe_db_dir(db_dir)
    if probe.get("status") == "needs_decryption":
        print(f"{prefix}: 已找到新版QQ NT数据，但当前数据库仍是加密封装状态。")
        print("请先用 probe 查看能力，再用 prepare-nt / decrypt-nt 生成明文SQLite后采集。")
        return
    print(f"{prefix}: 未找到可读取的QQ消息数据库")


if __name__ == "__main__":
    main()
