#!/usr/bin/env python3
"""
邮箱采集器 - 支持IMAP协议的邮箱邮件采集
"""
import imaplib
import email
import csv
import json
import mailbox
import os
import sys
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timedelta
from email import policy as email_policy
from email.header import decode_header
from pathlib import Path
from pathlib import PurePosixPath

from email_collector.events import emails_to_events, gap_event, write_events_jsonl, write_json

# Windows控制台utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

STATE_DIR = Path.home() / ".collectorx"
TOKEN_FILE = Path(os.environ.get("COLLECTORX_EMAIL_STATE", str(STATE_DIR / "email.json"))).expanduser()

PROVIDER_PRESETS = {
    "gmail": {
        "host": "imap.gmail.com",
        "domains": {"gmail.com", "googlemail.com"},
        "note": "需要在 Google 账户中开启 IMAP 并使用应用专用密码或 OAuth 方案。",
    },
    "outlook": {
        "host": "outlook.office365.com",
        "domains": {"outlook.com", "hotmail.com", "live.com", "msn.com"},
        "note": "Microsoft 账户通常需要应用专用密码或 OAuth 方案。",
    },
    "qq": {
        "host": "imap.qq.com",
        "domains": {"qq.com", "vip.qq.com", "foxmail.com"},
        "note": "QQ 邮箱需要在邮箱设置中开启 IMAP/SMTP 并使用授权码。",
    },
    "163": {
        "host": "imap.163.com",
        "domains": {"163.com"},
        "note": "网易邮箱需要开启 IMAP/SMTP 并使用授权码。",
    },
    "126": {
        "host": "imap.126.com",
        "domains": {"126.com"},
        "note": "网易邮箱需要开启 IMAP/SMTP 并使用授权码。",
    },
    "icloud": {
        "host": "imap.mail.me.com",
        "domains": {"icloud.com", "me.com", "mac.com"},
        "note": "iCloud 邮箱需要 Apple ID 应用专用密码。",
    },
}

DEFAULT_FOLDERS = ["INBOX"]
SUPPORTED_IMPORT_EXTENSIONS = {".eml", ".mbox", ".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".zip"}
SUPPORTED_ARCHIVE_EMAIL_EXTENSIONS = SUPPORTED_IMPORT_EXTENSIONS - {".zip"}


def _load_state() -> dict:
    if not TOKEN_FILE.exists():
        return {}
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(state, indent=2, ensure_ascii=False)
    with open(TOKEN_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def _account_id(email_addr: str) -> str:
    safe = []
    for ch in email_addr.lower():
        safe.append(ch if ch.isalnum() else "_")
    return "".join(safe).strip("_") or "email"


def infer_provider(email_addr: str) -> dict:
    domain = email_addr.split("@")[-1].lower() if "@" in email_addr else ""
    for provider, preset in PROVIDER_PRESETS.items():
        if domain in preset["domains"]:
            return {
                "provider": provider,
                "host": preset["host"],
                "note": preset["note"],
                "matched": True,
            }
    return {
        "provider": "custom",
        "host": "",
        "note": "未识别邮箱服务商，需要手动提供 IMAP host。",
        "matched": False,
    }


def _normalize_folders(value: str = None) -> list[str]:
    if not value:
        return list(DEFAULT_FOLDERS)
    folders = [part.strip() for part in value.split(",") if part.strip()]
    return folders or list(DEFAULT_FOLDERS)


def _accounts_from_state(state: dict) -> list[dict]:
    accounts = state.get("accounts")
    if isinstance(accounts, list):
        return accounts

    # Backward compatibility with the original single-account state.
    old = state.get("account")
    if isinstance(old, dict) and old.get("email"):
        migrated = dict(old)
        migrated.setdefault("id", _account_id(migrated["email"]))
        migrated.setdefault("provider", infer_provider(migrated["email"])["provider"])
        migrated.setdefault("folders", list(DEFAULT_FOLDERS))
        migrated.setdefault("days", 30)
        migrated.setdefault("enabled", True)
        return [migrated]
    return []


def _save_accounts(accounts: list[dict]) -> None:
    _save_state({"accounts": accounts})


def _select_accounts(state: dict, account_id: str = "all", *, enabled_only: bool = True) -> list[dict]:
    accounts = _accounts_from_state(state)
    if enabled_only:
        accounts = [account for account in accounts if account.get("enabled", True)]
    if account_id in (None, "", "all"):
        return accounts
    selected = [
        account
        for account in accounts
        if account.get("id") == account_id or account.get("email") == account_id
    ]
    if not selected:
        print(f"ERROR: 未找到邮箱账户: {account_id}")
        sys.exit(1)
    return selected


def decode_mime_header(header):
    """解码MIME头部"""
    if not header:
        return ""
    decoded_parts = decode_header(header)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def get_email_body(msg):
    """提取邮件正文"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    return body


def get_email_attachments(msg):
    """Return attachment metadata only; never write attachment bodies into events."""
    attachments = []
    if not msg.is_multipart():
        return attachments
    for part in msg.walk():
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        attachments.append(
            {
                "filename": decode_mime_header(filename),
                "content_type": part.get_content_type(),
                "size": len(payload),
            }
        )
    return attachments


def cmd_preflight(email_addrs: list[str]) -> None:
    """前置识别：判断邮箱服务商、IMAP host 和授权提示。"""
    if not email_addrs:
        state = _load_state()
        accounts = _accounts_from_state(state)
        if not accounts:
            print("未配置邮箱账户。请使用 preflight --email user@example.com 先识别通道。")
            return
        email_addrs = [account["email"] for account in accounts if account.get("email")]

    results = []
    for email_addr in email_addrs:
        result = infer_provider(email_addr)
        result["email"] = email_addr
        result["account_id"] = _account_id(email_addr)
        result["default_folders"] = list(DEFAULT_FOLDERS)
        results.append(result)

    print(json.dumps(results, ensure_ascii=False, indent=2))


def cmd_register(
    host: str = None,
    email_addr: str = None,
    password: str = None,
    password_env: str = None,
    provider: str = None,
    account_id: str = None,
    folders: str = None,
    days: int = 30,
    enabled: bool = True,
):
    """注册邮箱账户"""
    if password and not password_env:
        print("ERROR: 出于安全边界，register 不再把密码写入本地状态；请改用 --password-env")
        sys.exit(1)
    if enabled and not password_env:
        print("ERROR: 启用账户请提供 --password-env；如只是加入待接入清单，可加 --disabled")
        sys.exit(1)
    if not email_addr:
        print("ERROR: 请提供 --email")
        sys.exit(1)

    inferred = infer_provider(email_addr)
    provider_name = provider or inferred["provider"]
    preset = PROVIDER_PRESETS.get(provider_name, {})
    resolved_host = host or preset.get("host") or inferred["host"]
    if not resolved_host:
        print("ERROR: 未识别 IMAP 服务器，请使用 --host 手动指定")
        sys.exit(1)

    state = _load_state()
    accounts = _accounts_from_state(state)
    new_account = {
        "id": account_id or _account_id(email_addr),
        "provider": provider_name,
        "host": resolved_host,
        "email": email_addr,
        "folders": _normalize_folders(folders),
        "days": days,
        "enabled": enabled,
    }
    if password_env:
        new_account["password_env"] = password_env

    replaced = False
    for index, account in enumerate(accounts):
        if account.get("id") == new_account["id"] or account.get("email") == email_addr:
            accounts[index] = new_account
            replaced = True
            break
    if not replaced:
        accounts.append(new_account)

    _save_accounts(accounts)
    print(f"邮箱账户已注册: {email_addr} ({new_account['id']}, {provider_name}, {resolved_host})")


def cmd_collect(
    days: int = 30,
    folder: str = "INBOX",
    fmt: str = "json",
    limit: int = None,
    event_export: str = None,
    source: str = "IMAP 邮件",
    collected_at: str = None,
    event_include_body: bool = False,
    account_id: str = "all",
):
    """采集邮件"""
    state = _load_state()
    accounts = _select_accounts(state, account_id)
    if not accounts:
        print("ERROR: 未找到邮箱账户，请先运行 register")
        sys.exit(1)

    try:
        emails = []
        for account in accounts:
            account_days = days if days is not None else int(account.get("days", 30))
            folders = [folder] if folder else account.get("folders") or list(DEFAULT_FOLDERS)
            emails.extend(
                _collect_account_emails(
                    account,
                    days=account_days,
                    folders=folders,
                    limit=limit,
                )
            )

        if fmt == "json":
            print(json.dumps(emails, ensure_ascii=False, indent=2))
        else:
            for e in emails:
                print(f"[{e['date']}] From: {e['from']}")
                print(f"Subject: {e['subject']}")
                print(f"Body: {e['body'][:200]}...")
                print("---")

        if event_export:
            events = emails_to_events(
                emails,
                source=source,
                account=None,
                folder=None,
                collected_at=collected_at,
                include_body=event_include_body,
            )
            write_events_jsonl(event_export, events)
            print(f"事件导出完成: {len(events)} 条 -> {event_export}")

        print(f"采集完成: {len(emails)} 封邮件")

    except Exception as e:
        print(f"采集失败: {e}")
        sys.exit(1)


def cmd_import(
    inputs: list[str],
    out_dir: str = None,
    event_export: str = None,
    limit: int = None,
    source: str = "授权邮件导出",
    collected_at: str = None,
    event_include_body: bool = False,
):
    """Import user-authorized local email exports without requiring IMAP registration."""
    emails, import_audit = collect_imported_emails_with_audit(inputs or [], limit=limit)
    if not emails:
        events = [gap_event(collected_at=collected_at, reason="email_authorized_export_missing")]
    else:
        events = emails_to_events(
            emails,
            source=source,
            collected_at=collected_at,
            include_body=event_include_body,
        )

    if event_export:
        write_events_jsonl(event_export, events)
    if out_dir:
        out = Path(out_dir).expanduser()
        write_events_jsonl(str(out / "lake" / "email" / "events.jsonl"), events)
        manifest = build_import_manifest(events, collected_at=collected_at, import_audit=import_audit)
        write_json(str(out / "manifest.json"), manifest)
        write_import_summary(out / "SUMMARY.md", manifest)

    print(json.dumps({"collector": "email", "event_count": len(events)}, ensure_ascii=False, sort_keys=True))


def collect_imported_emails(inputs: list[str], *, limit: int = None) -> list[dict]:
    emails, _audit = collect_imported_emails_with_audit(inputs, limit=limit)
    return emails


def collect_imported_emails_with_audit(inputs: list[str], *, limit: int = None) -> tuple[list[dict], dict]:
    paths = list(iter_import_paths(inputs))
    audit = {
        "input_count": len(inputs),
        "resolved_input_file_count": len(paths),
        "imported_email_count": 0,
        "extension_counts": {},
        "archive_member_count": 0,
        "archive_member_extension_counts": {},
        "skipped_archive_member_count": 0,
        "skipped_archive_member_extension_counts": {},
        "limit": limit,
        "supported_import_extensions": sorted(SUPPORTED_IMPORT_EXTENSIONS),
        "attachment_bodies_included": False,
    }
    collected = []
    for path in paths:
        increment_counter(audit, "extension_counts", path.suffix.lower() or "<none>")
        for item in parse_email_export(path, audit=audit):
            collected.append(item)
            if limit is not None and len(collected) >= limit:
                audit["imported_email_count"] = len(collected[:limit])
                finalize_import_audit(audit)
                return collected[:limit], audit
    audit["imported_email_count"] = len(collected)
    finalize_import_audit(audit)
    return collected, audit


def iter_import_paths(inputs: list[str]):
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_IMPORT_EXTENSIONS:
                    yield child
        elif path.is_file() and path.suffix.lower() in SUPPORTED_IMPORT_EXTENSIONS:
            yield path


def parse_email_export(path: Path, *, audit: dict = None) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".eml":
        raw = path.read_bytes()
        msg = email.message_from_bytes(raw, policy=email_policy.default)
        return [message_to_record(msg, path=path, row=1)]
    if suffix == ".mbox":
        box = mailbox.mbox(str(path))
        try:
            return [message_to_record(msg, path=path, row=index) for index, msg in enumerate(box, start=1)]
        finally:
            box.close()
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return parse_email_json(path)
    if suffix in {".csv", ".tsv"}:
        return parse_email_table(path)
    if suffix == ".zip":
        return parse_email_zip(path, audit=audit)
    return []


def parse_email_zip(path: Path, *, audit: dict = None) -> list[dict]:
    records: list[dict] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="collectorx-email-zip-") as tmp:
        tmp_root = Path(tmp)
        for info in archive.infolist():
            if info.is_dir():
                continue
            member_name = info.filename.replace("\\", "/")
            member_path = PurePosixPath(member_name)
            suffix = Path(member_name).suffix.lower()
            if audit is not None:
                audit["archive_member_count"] += 1
                increment_counter(audit, "archive_member_extension_counts", suffix or "<none>")
            if not is_safe_archive_member(member_path) or suffix not in SUPPORTED_ARCHIVE_EMAIL_EXTENSIONS:
                if audit is not None:
                    audit["skipped_archive_member_count"] += 1
                    increment_counter(audit, "skipped_archive_member_extension_counts", suffix or "<none>")
                continue
            target = tmp_root.joinpath(*member_path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            for record in parse_email_export(target):
                raw_ref = record.setdefault("raw_ref", {})
                raw_ref["path"] = f"{path}::{member_name}"
                raw_ref["archive"] = str(path)
                raw_ref["archive_member"] = member_name
                records.append(record)
    return records


def is_safe_archive_member(member_path: PurePosixPath) -> bool:
    return bool(member_path.parts) and not member_path.is_absolute() and ".." not in member_path.parts


def message_to_record(msg, *, path: Path, row: int) -> dict:
    return {
        "id": f"{path.name}:{row}",
        "message_id": decode_mime_header(msg.get("Message-ID")),
        "mailbox": "",
        "folder": "local-export",
        "from": decode_mime_header(msg.get("From")),
        "to": decode_mime_header(msg.get("To")),
        "cc": decode_mime_header(msg.get("Cc")),
        "subject": decode_mime_header(msg.get("Subject")),
        "date": decode_mime_header(msg.get("Date")),
        "body": get_email_body(msg)[:5000],
        "attachment_refs": get_email_attachments(msg),
        "raw_ref": {"path": str(path), "row": row, "format": path.suffix.lower().lstrip(".")},
    }


def parse_email_json(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    if not text:
        return []
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = extract_email_records(json.loads(text))
    return [normalize_export_record(row if isinstance(row, dict) else {"subject": str(row)}, path=path, row_index=index) for index, row in enumerate(rows, start=1)]


def extract_email_records(loaded):
    if isinstance(loaded, list):
        return loaded
    if not isinstance(loaded, dict):
        return [{"subject": str(loaded)}]
    for key in ("emails", "messages", "items", "records", "data", "mail", "邮件"):
        value = loaded.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = extract_email_records(value)
            if not (len(nested) == 1 and nested[0] == value):
                return nested
    return [loaded]


def parse_email_table(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if not text.strip():
        return []
    delimiter = "\t" if path.suffix.lower() == ".tsv" else sniff_delimiter(text)
    return [
        normalize_export_record({str(key): value for key, value in row.items() if key is not None}, path=path, row_index=index)
        for index, row in enumerate(csv.DictReader(text.splitlines(), delimiter=delimiter), start=1)
    ]


def sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def normalize_export_record(record_row: dict, *, path: Path, row_index: int) -> dict:
    record = {
        "id": first(record_row, ["id", "uid", "imap_uid", "序号"]) or f"{path.name}:{row_index}",
        "message_id": first(record_row, ["message_id", "message-id", "Message-ID", "邮件ID"]),
        "mailbox": first(record_row, ["mailbox", "account", "email", "邮箱", "账号"]) or "",
        "folder": first(record_row, ["folder", "mailbox_folder", "文件夹"]) or "local-export",
        "from": first(record_row, ["from", "sender", "from_addr", "发件人"]),
        "to": first(record_row, ["to", "recipient", "收件人"]),
        "cc": first(record_row, ["cc", "抄送"]),
        "subject": first(record_row, ["subject", "title", "主题", "标题"]),
        "date": first(record_row, ["date", "time", "sent_at", "received_at", "日期", "时间"]),
        "body": (first(record_row, ["body", "content", "text", "正文", "内容"]) or "")[:5000],
        "attachment_refs": normalize_attachments(first_raw(record_row, "attachments") or first_raw(record_row, "attachment_refs") or first_raw(record_row, "附件")),
        "raw_ref": {"path": str(path), "row": row_index, "format": path.suffix.lower().lstrip(".")},
    }
    return {key: value for key, value in record.items() if value not in (None, "", [])}


def normalize_attachments(value):
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [normalize_attachment_item(item) for item in value if normalize_attachment_item(item)]
    if isinstance(value, dict):
        item = normalize_attachment_item(value)
        return [item] if item else []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            loaded = json.loads(stripped)
            return normalize_attachments(loaded)
        except json.JSONDecodeError:
            return [{"filename": part.strip()} for part in stripped.replace("；", ";").split(";") if part.strip()]
    return []


def normalize_attachment_item(item):
    if isinstance(item, dict):
        filename = first(item, ["filename", "name", "file_name", "文件名"])
        if not filename:
            return {}
        result = {
            "filename": filename,
            "content_type": first(item, ["content_type", "mime", "type", "类型"]),
            "size": first(item, ["size", "bytes", "大小"]),
        }
        return {key: value for key, value in result.items() if value not in (None, "")}
    text = str(item).strip()
    return {"filename": text} if text else {}


def first(record: dict, keys: list[str]) -> str:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    normalized = {_normalize_key(key): value for key, value in record.items()}
    for key in keys:
        value = normalized.get(_normalize_key(key))
        if value not in (None, ""):
            return str(value)
    return ""


def first_raw(record: dict, key: str):
    if key in record:
        return record.get(key)
    normalized_key = _normalize_key(key)
    for candidate, value in record.items():
        if _normalize_key(candidate) == normalized_key:
            return value
    return None


def _normalize_key(value) -> str:
    return str(value).lower().replace("_", "").replace("-", "").replace(" ", "")


def build_import_manifest(events: list[dict], *, collected_at: str = None, import_audit: dict = None) -> dict:
    kind_counts = Counter(event["kind"] for event in events)
    folder_counts = Counter((event.get("data") or {}).get("folder", "unknown") for event in events if event["kind"] == "email")
    mailbox_counts = Counter((event.get("data") or {}).get("mailbox", "unknown") for event in events if event["kind"] == "email")
    gap_only = bool(events) and all((event.get("data") or {}).get("gap") for event in events)
    return {
        "schema": "collectorx.email_import.manifest.v1",
        "collector": "email",
        "collected_at": collected_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "folder_counts": dict(sorted(folder_counts.items())),
        "mailbox_counts": dict(sorted(mailbox_counts.items())),
        "collection_readiness": {
            "status": "needs_email_authorized_export" if gap_only else "events_collected",
            "can_enter_finclaw": bool(events) and not gap_only,
            "source_collection_scope": "none" if gap_only else "partial_authorized_input",
            "full_body_included": any("body" in (event.get("data") or {}) for event in events),
            "next_action": "Provide authorized local email exports." if gap_only else "Feed lake/email/events.jsonl into email-research lens.",
        },
        "body_policy": {
            "full_body_included": any("body" in (event.get("data") or {}) for event in events),
            "full_body_requires_event_include_body": True,
            "body_preview_char_limit": 300,
        },
        "attachment_policy": {
            "attachment_refs_included": any((event.get("data") or {}).get("attachment_refs") for event in events),
            "attachment_bodies_included": False,
            "retained_fields": ["filename", "content_type", "size"],
        },
        "collection_audit": import_audit or {},
    }


def increment_counter(audit: dict, key: str, value: str) -> None:
    counts = audit.setdefault(key, {})
    counts[value] = int(counts.get(value, 0)) + 1


def finalize_import_audit(audit: dict) -> None:
    for key in (
        "extension_counts",
        "archive_member_extension_counts",
        "skipped_archive_member_extension_counts",
    ):
        audit[key] = dict(sorted((audit.get(key) or {}).items()))


def write_import_summary(path: Path, manifest: dict) -> None:
    lines = [
        "# Email Collector Import Package",
        "",
        "- collector: `email`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        "",
        "Local email exports are generic email evidence. Use the `email-research` lens for broker research, roadshow, and IR mail evidence.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def cmd_status():
    """显示状态"""
    state = _load_state()
    accounts = _accounts_from_state(state)
    if accounts:
        print(f"已配置邮箱账户: {len(accounts)} 个")
        for account in accounts:
            print(f"- {account.get('id')}: {account.get('email')}")
            print(f"  服务商: {account.get('provider', 'custom')}")
            print(f"  IMAP服务器: {account.get('host')}")
            print(f"  文件夹: {', '.join(account.get('folders') or DEFAULT_FOLDERS)}")
            print(f"  默认天数: {account.get('days', 30)}")
            print(f"  启用: {account.get('enabled', True)}")
            if account.get("password_env"):
                print(f"  密码来源: 环境变量 {account['password_env']}")
            elif account.get("password"):
                print("  密码来源: 旧版本地状态文件（建议迁移到 password_env）")
            else:
                print("  密码来源: 未配置")
    else:
        print("未注册邮箱账户")


def _collect_account_emails(
    account: dict,
    *,
    days: int,
    folders: list[str],
    limit: int = None,
) -> list[dict]:
    password = _resolve_password(account)
    if not password:
        print(f"ERROR: {account.get('email')} 未找到邮箱密码，请检查 --password 或 --password-env 配置")
        sys.exit(1)

    mail = imaplib.IMAP4_SSL(account["host"])
    mail.login(account["email"], password)
    collected: list[dict] = []
    try:
        for folder_name in folders:
            mail.select(folder_name)
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            status, messages = mail.search(None, f'(SINCE "{since_date}")')
            if status != "OK":
                print(f"{account['email']} / {folder_name} 搜索失败: {status}")
                continue

            msg_ids = messages[0].split()
            if limit:
                msg_ids = msg_ids[-limit:]

            for msg_id in msg_ids:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                msg = email.message_from_bytes(msg_data[0][1])
                collected.append(
                    {
                        "id": msg_id.decode(),
                        "message_id": decode_mime_header(msg["Message-ID"]),
                        "mailbox": account["email"],
                        "folder": folder_name,
                        "from": decode_mime_header(msg["From"]),
                        "to": decode_mime_header(msg["To"]),
                        "cc": decode_mime_header(msg["Cc"]),
                        "subject": decode_mime_header(msg["Subject"]),
                        "date": msg["Date"],
                        "body": get_email_body(msg)[:5000],
                        "attachment_refs": get_email_attachments(msg),
                    }
                )
    finally:
        mail.logout()
    return collected


def _resolve_password(account: dict) -> str:
    if account.get("password_env"):
        return os.environ.get(account["password_env"], "")
    return account.get("password", "")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="邮箱采集器")
    subparsers = parser.add_subparsers(dest="command")

    # preflight命令
    preflight_parser = subparsers.add_parser("preflight", help="识别邮箱通道并生成接入建议")
    preflight_parser.add_argument("--email", action="append", dest="emails", help="待识别邮箱地址，可重复")
    
    # register命令
    reg_parser = subparsers.add_parser("register", help="注册邮箱账户")
    reg_parser.add_argument("--host", help="IMAP服务器，未提供时按provider/email推断")
    reg_parser.add_argument("--email", required=True, help="邮箱地址")
    reg_parser.add_argument("--provider", choices=sorted(PROVIDER_PRESETS) + ["custom"], help="邮箱服务商")
    reg_parser.add_argument("--account-id", help="账户ID，默认由邮箱地址生成")
    reg_parser.add_argument("--password", help="密码或应用专用密码")
    reg_parser.add_argument("--password-env", help="从环境变量读取密码,避免写入本地状态文件")
    reg_parser.add_argument("--folders", default="INBOX", help="默认采集文件夹，逗号分隔")
    reg_parser.add_argument("--days", type=int, default=30, help="默认采集最近N天")
    reg_parser.add_argument("--disabled", action="store_true", help="注册但暂不启用")
    
    # collect命令
    col_parser = subparsers.add_parser("collect", help="采集邮件")
    col_parser.add_argument("--account", default="all", help="账户ID/邮箱地址，默认采集全部已启用账户")
    col_parser.add_argument("--days", type=int, help="覆盖采集最近N天")
    col_parser.add_argument("--folder", help="覆盖邮箱文件夹；不填则使用账户配置")
    col_parser.add_argument("--format", choices=["json", "txt"], default="json")
    col_parser.add_argument("--limit", type=int, help="限制数量")
    col_parser.add_argument("--event-export", help="导出CollectorX Event JSONL路径")
    col_parser.add_argument("--source", default="IMAP 邮件", help="事件source字段")
    col_parser.add_argument("--collected-at", help="事件collected_at字段，默认当前时间")
    col_parser.add_argument("--event-include-body", action="store_true", help="事件中包含完整正文，默认只包含预览")

    # import命令
    import_parser = subparsers.add_parser("import", help="导入用户授权的本地邮件导出文件/目录")
    import_parser.add_argument("--input", action="append", help="本地邮件导出文件或目录，可重复；支持 EML/MBOX/JSON/JSONL/CSV/TSV/ZIP")
    import_parser.add_argument("--out-dir", help="输出标准采集包目录")
    import_parser.add_argument("--event-export", help="导出CollectorX Event JSONL路径")
    import_parser.add_argument("--limit", type=int, help="限制数量")
    import_parser.add_argument("--source", default="授权邮件导出", help="事件source字段")
    import_parser.add_argument("--collected-at", help="事件collected_at字段，默认当前时间")
    import_parser.add_argument("--event-include-body", action="store_true", help="事件中包含完整正文，默认只包含预览")
    
    # status命令
    subparsers.add_parser("status", help="显示状态")
    
    args = parser.parse_args()
    
    if args.command == "preflight":
        cmd_preflight(args.emails or [])
    elif args.command == "register":
        cmd_register(
            args.host,
            args.email,
            args.password,
            args.password_env,
            provider=args.provider,
            account_id=args.account_id,
            folders=args.folders,
            days=args.days,
            enabled=not args.disabled,
        )
    elif args.command == "collect":
        cmd_collect(
            args.days,
            args.folder,
            args.format,
            args.limit,
            event_export=args.event_export,
            source=args.source,
            collected_at=args.collected_at,
            event_include_body=args.event_include_body,
            account_id=args.account,
        )
    elif args.command == "import":
        cmd_import(
            args.input or [],
            out_dir=args.out_dir,
            event_export=args.event_export,
            limit=args.limit,
            source=args.source,
            collected_at=args.collected_at,
            event_include_body=args.event_include_body,
        )
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
