#!/usr/bin/env python3
"""
邮箱采集器 - 支持IMAP协议的邮箱邮件采集
"""
import imaplib
import email
import csv
import fnmatch
import json
import mailbox
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter
from datetime import datetime, timedelta
from email import policy as email_policy
from email.header import decode_header
from email.utils import getaddresses
from pathlib import Path
from pathlib import PurePosixPath
from pathlib import PureWindowsPath

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
SUPPORTED_IMPORT_EXTENSIONS = {".eml", ".emlx", ".mbox", ".json", ".jsonl", ".ndjson", ".csv", ".tsv", ".zip"}
SUPPORTED_ARCHIVE_EMAIL_EXTENSIONS = SUPPORTED_IMPORT_EXTENSIONS - {".zip"}
MAILDIR_PARENT_NAMES = {"cur", "new"}
THUNDERBIRD_MBOX_PARENT_NAMES = {"mail", "imapmail"}
THUNDERBIRD_SUMMARY_SUFFIX = ".msf"
EMAIL_HEADER_MARKERS = (
    b"from:",
    b"to:",
    b"subject:",
    b"date:",
    b"message-id:",
    b"return-path:",
    b"delivered-to:",
    b"mime-version:",
)
SUPPORTED_LOCAL_SCAN_PLATFORMS = {"auto", "mac", "windows", "linux", "generic"}
DEFAULT_MAC_EMAIL_ROOTS = (
    Path.home() / "Library" / "Mail",
    Path.home() / "Library" / "Containers" / "com.apple.mail" / "Data" / "Library" / "Mail",
    Path.home() / "Library" / "Thunderbird" / "Profiles",
)
DEFAULT_WINDOWS_EMAIL_ROOTS = (
    Path.home() / "AppData" / "Roaming" / "Thunderbird" / "Profiles",
    Path.home() / "AppData" / "Roaming" / "Mozilla" / "Thunderbird" / "Profiles",
    Path.home() / "Documents" / "Mail",
)
DEFAULT_LINUX_EMAIL_ROOTS = (
    Path.home() / ".thunderbird",
    Path.home() / ".local" / "share" / "evolution" / "mail",
    Path.home() / "Mail",
)
LOCAL_EMAIL_SCAN_MAX_FILES = 50000


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
    out_dir: str = None,
    source: str = "IMAP 邮件",
    collected_at: str = None,
    event_include_body: bool = False,
    account_id: str = "all",
    email_scope_policy: dict = None,
):
    """采集邮件"""
    state = _load_state()
    accounts = _select_accounts(state, account_id)
    if not accounts:
        if out_dir or event_export:
            audit = build_imap_collection_audit(
                accounts=[],
                account_audits=[],
                account_id=account_id,
                status="no_registered_account",
            )
            _empty_emails, scope_audit = apply_email_scope_policy([], email_scope_policy)
            attach_email_scope_policy_audit(audit, scope_audit)
            events = [gap_event(collected_at=collected_at, reason="email_imap_account_missing")]
            if event_export:
                write_events_jsonl(event_export, events)
            if out_dir:
                write_standard_email_package(
                    out_dir,
                    events,
                    collected_at=collected_at,
                    collection_audit=audit,
                    package_schema="collectorx.email_collect.manifest.v1",
                )
            print(json.dumps({"collector": "email", "event_count": len(events)}, ensure_ascii=False, sort_keys=True))
            return
        print("ERROR: 未找到邮箱账户，请先运行 register")
        sys.exit(1)

    try:
        emails = []
        account_audits = []
        for account in accounts:
            account_days = days if days is not None else int(account.get("days", 30))
            folders = [folder] if folder else account.get("folders") or list(DEFAULT_FOLDERS)
            account_emails, account_audit = _collect_account_emails_with_audit(
                account,
                days=account_days,
                folders=folders,
                limit=limit,
            )
            emails.extend(account_emails)
            account_audits.append(account_audit)

        candidate_email_count = len(emails)
        emails, scope_audit = apply_email_scope_policy(emails, email_scope_policy)
        if candidate_email_count and scope_audit.get("filtered_all"):
            audit_status = "scope_policy_filtered_all"
        else:
            audit_status = resolve_imap_audit_status(account_audits, emails)
        collection_audit = build_imap_collection_audit(
            accounts=accounts,
            account_audits=account_audits,
            account_id=account_id,
            status=audit_status,
        )
        attach_email_scope_policy_audit(collection_audit, scope_audit)

        if fmt == "json":
            print(json.dumps(emails, ensure_ascii=False, indent=2))
        else:
            for e in emails:
                print(f"[{e['date']}] From: {e['from']}")
                print(f"Subject: {e['subject']}")
                print(f"Body: {e['body'][:200]}...")
                print("---")

        events = []
        if emails:
            events = emails_to_events(
                emails,
                source=source,
                account=None,
                folder=None,
                collected_at=collected_at,
                include_body=event_include_body,
            )
        elif event_export or out_dir:
            events = [gap_event(collected_at=collected_at, reason=gap_reason_for_imap_audit(audit_status))]

        if event_export:
            write_events_jsonl(event_export, events)
            print(f"事件导出完成: {len(events)} 条 -> {event_export}")

        if out_dir:
            write_standard_email_package(
                out_dir,
                events,
                collected_at=collected_at,
                collection_audit=collection_audit,
                package_schema="collectorx.email_collect.manifest.v1",
            )
            print(f"标准采集包已写入: {out_dir}")

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
    local_scan: bool = False,
    platform: str = "auto",
    container_root: str = None,
    probe_export: str = None,
    email_scope_policy: dict = None,
):
    """Import user-authorized local email exports without requiring IMAP registration."""
    local_scan_files = find_local_email_files(container_root=container_root, platform=platform) if local_scan else []
    if probe_export:
        write_json(
            probe_export,
            build_local_email_scan_report(platform=platform, container_root=container_root, files=local_scan_files),
        )
    emails, import_audit = collect_imported_emails_with_audit(
        inputs or [],
        limit=limit,
        local_scan=local_scan,
        platform=platform,
        container_root=container_root,
        local_scan_files=local_scan_files,
        email_scope_policy=email_scope_policy,
    )
    if not emails:
        reason = "email_scope_policy_filtered_all" if import_audit.get("email_scope_policy_filtered_all") else "email_authorized_export_missing"
        events = [gap_event(collected_at=collected_at, reason=reason)]
    else:
        events = emails_to_events(
            emails,
            source="授权本机邮箱扫描" if local_scan else source,
            collected_at=collected_at,
            include_body=event_include_body,
        )

    if event_export:
        write_events_jsonl(event_export, events)
    if out_dir:
        write_standard_email_package(
            out_dir,
            events,
            collected_at=collected_at,
            collection_audit=import_audit,
            package_schema="collectorx.email_import.manifest.v1",
        )

    print(json.dumps({"collector": "email", "event_count": len(events)}, ensure_ascii=False, sort_keys=True))


def collect_imported_emails(inputs: list[str], *, limit: int = None) -> list[dict]:
    emails, _audit = collect_imported_emails_with_audit(inputs, limit=limit)
    return emails


def collect_imported_emails_with_audit(
    inputs: list[str],
    *,
    limit: int = None,
    local_scan: bool = False,
    platform: str = "auto",
    container_root: str = None,
    local_scan_files: list[Path] = None,
    email_scope_policy: dict = None,
) -> tuple[list[dict], dict]:
    input_list = list(inputs)
    local_scan_files = local_scan_files if local_scan_files is not None else (
        find_local_email_files(container_root=container_root, platform=platform) if local_scan else []
    )
    local_scan_report = build_local_email_scan_report(
        platform=platform,
        container_root=container_root,
        files=local_scan_files,
    ) if local_scan else None
    local_scan_meta = {
        path_key(path): {
            "local_scan": True,
            "source_platform": (local_scan_report or {}).get("platform", {}).get("resolved"),
            "source_path_label": local_email_file_label(path),
        }
        for path in local_scan_files
    }
    audit = {
        "source_type": "authorized_email_export_or_local_scan" if local_scan else "authorized_email_export",
        "input_count": len(input_list),
        "requested_inputs": [str(Path(raw).expanduser()) for raw in input_list] + [local_email_file_label(path) for path in local_scan_files],
        "resolved_input_file_count": 0,
        "input_missing_count": 0,
        "imported_email_count": 0,
        "parsed_record_count": 0,
        "extension_counts": {},
        "skipped_extension_counts": {},
        "skipped_reason_counts": {},
        "skipped_file_count": 0,
        "archive_count": 0,
        "archive_member_count": 0,
        "archive_member_extension_counts": {},
        "archive_member_imported_email_count": 0,
        "skipped_archive_member_count": 0,
        "skipped_archive_member_extension_counts": {},
        "skipped_archive_member_reason_counts": {},
        "limit": limit,
        "limit_reached": False,
        "supported_import_extensions": sorted(SUPPORTED_IMPORT_EXTENSIONS),
        "supported_local_mailbox_formats": ["eml", "emlx", "maildir", "mbox", "thunderbird_mbox"],
        "apple_mail_emlx_supported": True,
        "apple_mail_emlx_file_count": 0,
        "maildir_message_import_supported": True,
        "maildir_message_file_count": 0,
        "thunderbird_mbox_import_supported": True,
        "thunderbird_mbox_file_count": 0,
        "local_scan_requested": local_scan,
        "local_scan_platform": (local_scan_report or {}).get("platform"),
        "local_scan_roots": (local_scan_report or {}).get("scan_roots", []),
        "local_scan_root_statuses": (local_scan_report or {}).get("scan_summary", {}).get("root_statuses", []),
        "local_scan_root_type_counts": (local_scan_report or {}).get("scan_summary", {}).get("root_type_counts", {}),
        "local_scan_candidate_file_count": len(local_scan_files),
        "local_scan_candidate_files": [local_email_file_label(path) for path in local_scan_files],
        "local_scan_candidate_format_counts": (local_scan_report or {}).get("scan_summary", {}).get("candidate_format_counts", {}),
        "local_scan_candidate_selection": (local_scan_report or {}).get("candidate_selection", {}),
        "local_scan_scanned_file_count": (local_scan_report or {}).get("scan_summary", {}).get("scanned_file_count", 0),
        "local_scan_skipped_file_count": (local_scan_report or {}).get("scan_summary", {}).get("skipped_file_count", 0),
        "local_scan_skipped_reason_counts": (local_scan_report or {}).get("scan_summary", {}).get("skipped_reason_counts", {}),
        "local_scan_thunderbird_summary_index_skipped_count": (local_scan_report or {}).get("scan_summary", {}).get("thunderbird_summary_index_skipped_count", 0),
        "local_scan_truncated_root_count": (local_scan_report or {}).get("scan_summary", {}).get("scan_truncated_root_count", 0),
        "local_scan_imported_email_count": 0,
        "attachment_bodies_included": False,
        "archive_path_traversal_members_collected": False,
        "windows_drive_archive_members_collected": False,
        "path_results": [],
    }
    collected: list[dict] = []
    scan_inputs = [*input_list, *(str(path) for path in local_scan_files)]
    for raw in scan_inputs:
        if limit is not None and len(collected) >= limit:
            audit["limit_reached"] = True
            break
        input_path = Path(raw).expanduser()
        if not input_path.exists():
            audit["input_missing_count"] += 1
            increment_counter(audit, "skipped_reason_counts", "input_missing")
            audit["path_results"].append(path_result(input_path, status="missing", reason="input_missing"))
            continue
        if input_path.is_dir():
            paths = sorted(child for child in input_path.rglob("*") if child.is_file())
        elif input_path.is_file():
            paths = [input_path]
        else:
            increment_counter(audit, "skipped_reason_counts", "unsupported_input_kind")
            audit["path_results"].append(path_result(input_path, status="skipped", reason="unsupported_input_kind"))
            continue

        for path in paths:
            if limit is not None and len(collected) >= limit:
                audit["limit_reached"] = True
                break
            ext = extension_label(path)
            increment_counter(audit, "extension_counts", ext)
            if not is_supported_import_path(path):
                skip_reason = local_email_skip_reason(path)
                audit["skipped_file_count"] += 1
                increment_counter(audit, "skipped_extension_counts", ext)
                increment_counter(audit, "skipped_reason_counts", skip_reason)
                audit["path_results"].append(path_result(path, status="skipped", reason=skip_reason))
                continue
            audit["resolved_input_file_count"] += 1
            if path.suffix.lower() == ".emlx":
                audit["apple_mail_emlx_file_count"] += 1
            if is_maildir_message_path(path):
                audit["maildir_message_file_count"] += 1
            if is_thunderbird_mbox_path(path):
                audit["thunderbird_mbox_file_count"] += 1
            source_meta = local_scan_meta.get(path_key(path))
            result = path_result(path, status="pending", source_meta=source_meta)
            before_archive_member_count = audit["archive_member_count"]
            before_skipped_archive_member_count = audit["skipped_archive_member_count"]
            try:
                if path.suffix.lower() == ".zip":
                    audit["archive_count"] += 1
                    parsed = parse_email_zip(path, audit=audit, limit=remaining_limit(limit, collected))
                    parsed = [annotate_local_scan_email_record(record, source_meta=source_meta) for record in parsed]
                    result.update(
                        {
                            "status": "parsed" if parsed else "no_records_parsed",
                            "parser": "zip",
                            "parsed_record_count": len(parsed),
                            "imported_email_count": len(parsed),
                            "archive_member_count": audit["archive_member_count"] - before_archive_member_count,
                            "skipped_archive_member_count": audit["skipped_archive_member_count"] - before_skipped_archive_member_count,
                        }
                    )
                else:
                    parsed = parse_email_export(path)
                    remaining = remaining_limit(limit, collected)
                    parsed = parsed if remaining is None else parsed[:remaining]
                    parsed = [annotate_local_scan_email_record(record, source_meta=source_meta) for record in parsed]
                    result.update(
                        {
                            "status": "parsed" if parsed else "no_records_parsed",
                            "parser": parser_name_for_path(path),
                            "parsed_record_count": len(parsed),
                            "imported_email_count": len(parsed),
                        }
                    )
            except Exception:
                parsed = []
                audit["skipped_file_count"] += 1
                increment_counter(audit, "skipped_extension_counts", ext)
                increment_counter(audit, "skipped_reason_counts", "parse_error")
                result.update({"status": "parse_error", "reason": "parse_error", "parsed_record_count": 0, "imported_email_count": 0})
            audit["path_results"].append(result)
            collected.extend(parsed)
            if source_meta:
                audit["local_scan_imported_email_count"] += len(parsed)
            if limit is not None and len(collected) >= limit:
                audit["limit_reached"] = True
                collected = collected[:limit]
                break
        if limit is not None and len(collected) >= limit:
            break
    candidate_email_count = len(collected)
    collected, scope_audit = apply_email_scope_policy(collected, email_scope_policy)
    attach_email_scope_policy_audit(audit, scope_audit)
    audit["pre_scope_policy_email_count"] = candidate_email_count
    audit["pre_scope_policy_local_scan_email_count"] = audit.get("local_scan_imported_email_count", 0)
    audit["local_scan_imported_email_count"] = sum(
        1 for record in collected if (record.get("raw_ref") or {}).get("local_scan") is True
    )
    audit["imported_email_count"] = len(collected)
    audit["parsed_record_count"] = len(collected)
    if audit.get("email_scope_policy_filtered_all"):
        audit["status"] = "scope_policy_filtered_all"
    finalize_import_audit(audit)
    return collected, audit


def iter_import_paths(inputs: list[str]):
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and is_supported_import_path(child):
                    yield child
        elif path.is_file() and is_supported_import_path(path):
            yield path


def resolve_local_email_scan_platform(platform: str = "auto") -> str:
    if platform not in SUPPORTED_LOCAL_SCAN_PLATFORMS:
        raise ValueError(f"Unsupported email local-scan platform: {platform}")
    if platform != "auto":
        return platform
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return "generic"


def local_email_scan_roots(container_root: str = None, *, platform: str = "auto") -> list[Path]:
    if container_root:
        return [Path(container_root).expanduser()]
    resolved = resolve_local_email_scan_platform(platform)
    if resolved == "mac":
        return list(DEFAULT_MAC_EMAIL_ROOTS)
    if resolved == "windows":
        return list(DEFAULT_WINDOWS_EMAIL_ROOTS)
    if resolved == "linux":
        return list(DEFAULT_LINUX_EMAIL_ROOTS)
    return []


def find_local_email_files(container_root: str = None, *, platform: str = "auto") -> list[Path]:
    found: list[Path] = []
    for root in local_email_scan_roots(container_root, platform=platform):
        if not root.exists():
            continue
        scanned = 0
        try:
            iterator = root.rglob("*") if root.is_dir() else iter([root])
            for path in iterator:
                if not path.is_file():
                    continue
                scanned += 1
                if scanned > LOCAL_EMAIL_SCAN_MAX_FILES:
                    break
                if is_supported_import_path(path):
                    found.append(path)
        except OSError:
            continue
    return dedupe_paths(found)


def build_local_email_scan_summary(roots: list[Path]) -> dict:
    candidate_format_counts = Counter()
    root_type_counts = Counter()
    skipped_reason_counts = Counter()
    root_statuses: list[dict] = []
    scanned_file_count = 0
    supported_file_count = 0
    skipped_file_count = 0
    thunderbird_mbox_file_count = 0
    thunderbird_summary_index_skipped_count = 0
    truncated_root_count = 0

    for root in roots:
        status = {
            "root": safe_path_label(root),
            "exists": root.exists(),
            "readable": root.exists() and os.access(root, os.R_OK),
            "kind": "missing",
            "scanned_file_count": 0,
            "truncated": False,
        }
        if not root.exists():
            root_statuses.append(status)
            continue
        if root.is_file():
            status["kind"] = "file"
            iterator = iter([root])
        elif root.is_dir():
            status["kind"] = "directory"
            iterator = root.rglob("*")
        else:
            status["kind"] = "unsupported"
            root_statuses.append(status)
            continue

        try:
            for path in iterator:
                if not path.is_file():
                    continue
                status["scanned_file_count"] += 1
                scanned_file_count += 1
                if status["scanned_file_count"] > LOCAL_EMAIL_SCAN_MAX_FILES:
                    status["truncated"] = True
                    truncated_root_count += 1
                    break
                if is_supported_import_path(path):
                    supported_file_count += 1
                    candidate_format_counts[parser_name_for_path(path)] += 1
                    root_type_counts[classify_local_email_path(path)] += 1
                    if is_thunderbird_mbox_path(path):
                        thunderbird_mbox_file_count += 1
                else:
                    reason = local_email_skip_reason(path)
                    skipped_file_count += 1
                    skipped_reason_counts[reason] += 1
                    if reason == "thunderbird_summary_index":
                        thunderbird_summary_index_skipped_count += 1
        except OSError:
            status["kind"] = "unreadable"
        root_statuses.append(status)

    return {
        "root_statuses": root_statuses,
        "scanned_file_count": scanned_file_count,
        "supported_file_count": supported_file_count,
        "skipped_file_count": skipped_file_count,
        "skipped_reason_counts": dict(sorted(skipped_reason_counts.items())),
        "candidate_format_counts": dict(sorted(candidate_format_counts.items())),
        "root_type_counts": dict(sorted(root_type_counts.items())),
        "thunderbird_mbox_file_count": thunderbird_mbox_file_count,
        "thunderbird_summary_index_skipped_count": thunderbird_summary_index_skipped_count,
        "scan_truncated_root_count": truncated_root_count,
    }


def build_local_email_scan_report(
    *,
    platform: str = "auto",
    container_root: str = None,
    files: list[Path] = None,
) -> dict:
    resolved = resolve_local_email_scan_platform(platform)
    file_list = dedupe_paths(files if files is not None else find_local_email_files(container_root=container_root, platform=platform))
    roots = local_email_scan_roots(container_root, platform=platform)
    scan_summary = build_local_email_scan_summary(roots)
    return {
        "probe_type": "email_local_scan",
        "platform": {
            "requested": platform,
            "resolved": resolved,
            "structure_status": (
                "verified_on_current_mac"
                if resolved == "mac" and sys.platform == "darwin"
                else "candidate_rules_need_real_machine_verification"
            ),
        },
        "scan_roots": [safe_path_label(root) for root in roots],
        "scan_summary": scan_summary,
        "mail_candidates": {
            "file_count": len(file_list),
            "files": [local_email_file_label(path) for path in file_list],
            "status": "available" if file_list else "not_found",
        },
        "candidate_selection": {
            "supported_import_extensions": sorted(SUPPORTED_IMPORT_EXTENSIONS),
            "supported_local_mailbox_formats": ["eml", "emlx", "maildir", "mbox", "thunderbird_mbox"],
            "maildir_parent_names": sorted(MAILDIR_PARENT_NAMES),
            "thunderbird_mbox_supported": True,
            "thunderbird_summary_index_skip_reason": "thunderbird_summary_index",
            "max_scan_files_per_root": LOCAL_EMAIL_SCAN_MAX_FILES,
        },
        "privacy_policy": {
            "credentials": "not_read",
            "cookies_tokens_sessions": "not_read",
            "attachment_bodies": "not_read_into_events",
            "full_body_in_events": "disabled_by_default",
            "path_emails_and_long_numeric_fragments": "masked_in_probe_and_local_scan_refs",
        },
    }


def annotate_local_scan_email_record(record: dict, *, source_meta: dict = None) -> dict:
    if not source_meta:
        return record
    annotated = dict(record)
    annotated["folder"] = annotated.get("folder") or "local-email-scan"
    raw_ref = dict(annotated.get("raw_ref") or {})
    original_path = str(raw_ref.get("path") or "")
    source_path_label = source_meta.get("source_path_label") or (safe_path_label(Path(original_path)) if original_path else "")
    if original_path and source_path_label:
        raw_ref["path"] = original_path.replace(original_path.split("::", 1)[0], source_path_label)
    elif source_path_label:
        raw_ref["path"] = source_path_label
    if raw_ref.get("archive"):
        raw_ref["archive"] = source_path_label
    raw_ref["local_scan"] = True
    raw_ref["source_platform"] = source_meta.get("source_platform")
    raw_ref["source_path_label"] = source_path_label
    annotated["raw_ref"] = raw_ref
    return annotated


def is_supported_import_path(path: Path) -> bool:
    return (
        path.suffix.lower() in SUPPORTED_IMPORT_EXTENSIONS
        or is_maildir_message_path(path)
        or is_thunderbird_mbox_path(path)
    )


def local_email_skip_reason(path: Path) -> str:
    if is_thunderbird_summary_index_path(path):
        return "thunderbird_summary_index"
    return "unsupported_extension"


def classify_local_email_path(path: Path) -> str:
    lower_parts = {part.lower() for part in path.parts}
    if is_thunderbird_mbox_path(path) or "thunderbird" in lower_parts or ".thunderbird" in lower_parts:
        return "thunderbird"
    if "com.apple.mail" in lower_parts or ("library" in lower_parts and "mail" in lower_parts and path.suffix.lower() == ".emlx"):
        return "apple_mail"
    if "evolution" in lower_parts:
        return "evolution"
    if is_maildir_message_path(path):
        return "maildir"
    return "generic"


def extension_label(path: Path) -> str:
    if is_thunderbird_mbox_path(path):
        return "<thunderbird-mbox>"
    if is_maildir_message_path(path):
        return "<maildir>"
    return path.suffix.lower() or "<none>"


def remaining_limit(limit: int = None, collected: list[dict] = None):
    collected = collected or []
    if limit is None:
        return None
    return max(limit - len(collected), 0)


def parser_name_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return "zip"
    if suffix == ".eml":
        return "eml"
    if suffix == ".emlx":
        return "emlx"
    if is_thunderbird_mbox_path(path):
        return "thunderbird_mbox"
    if is_maildir_message_path(path):
        return "maildir"
    if suffix == ".mbox":
        return "mbox"
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return "json"
    if suffix in {".csv", ".tsv"}:
        return "table"
    return "unknown"


def path_result(path: Path, *, status: str, reason: str = None, source_meta: dict = None) -> dict:
    result = {
        "path": (source_meta or {}).get("source_path_label") or str(path),
        "extension": extension_label(path),
        "status": status,
    }
    if reason:
        result["reason"] = reason
    return result


def dedupe_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    result = []
    for path in paths:
        key = path_key(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def path_key(path: Path) -> str:
    try:
        return str(path.expanduser().resolve())
    except OSError:
        return str(path.expanduser().absolute())


def safe_path_label(path: Path) -> str:
    text = str(path.expanduser())
    text = re.sub(r"([A-Za-z0-9._%+-]{2})[A-Za-z0-9._%+-]*(@)", r"\1***\2", text)
    text = re.sub(r"(?<!\d)\d{6,}(?!\d)", "<digits>", text)
    return text


def local_email_file_label(path: Path) -> str:
    return safe_path_label(path)


def parse_email_export(path: Path, *, audit: dict = None) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".eml":
        raw = path.read_bytes()
        msg = email.message_from_bytes(raw, policy=email_policy.default)
        return [message_to_record(msg, path=path, row=1)]
    if suffix == ".emlx":
        raw = apple_mail_emlx_message_bytes(path.read_bytes())
        msg = email.message_from_bytes(raw, policy=email_policy.default)
        return [message_to_record(msg, path=path, row=1)]
    if is_maildir_message_path(path):
        raw = path.read_bytes()
        msg = email.message_from_bytes(raw, policy=email_policy.default)
        return [message_to_record(msg, path=path, row=1)]
    if suffix == ".mbox" or is_thunderbird_mbox_path(path):
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


def parse_email_zip(path: Path, *, audit: dict = None, limit: int = None) -> list[dict]:
    records: list[dict] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="collectorx-email-zip-") as tmp:
        tmp_root = Path(tmp)
        members = sorted(archive.infolist(), key=lambda item: item.filename.replace("\\", "/"))
        for index, info in enumerate(members):
            member_name = info.filename.replace("\\", "/")
            member_path = PurePosixPath(member_name)
            member_ext = archive_member_extension_label(member_name)
            if audit is not None:
                audit["archive_member_count"] += 1
                increment_counter(audit, "archive_member_extension_counts", member_ext)
            skip_reason = archive_member_skip_reason(info)
            if skip_reason:
                if audit is not None:
                    audit["skipped_archive_member_count"] += 1
                    increment_counter(audit, "skipped_archive_member_extension_counts", member_ext)
                    increment_counter(audit, "skipped_archive_member_reason_counts", skip_reason)
                    append_archive_member_result(audit, member_name, status="skipped", reason=skip_reason)
                continue
            target = tmp_root.joinpath(*member_path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.write_bytes(archive.read(info))
                parsed = parse_email_export(target)
            except Exception:
                if audit is not None:
                    audit["skipped_archive_member_count"] += 1
                    increment_counter(audit, "skipped_archive_member_extension_counts", member_ext)
                    increment_counter(audit, "skipped_archive_member_reason_counts", "parse_error")
                    append_archive_member_result(audit, member_name, status="parse_error", reason="parse_error")
                continue
            remaining = None if limit is None else max(limit - len(records), 0)
            emittable = parsed if remaining is None else parsed[:remaining]
            if audit is not None:
                append_archive_member_result(
                    audit,
                    member_name,
                    status="parsed" if parsed else "no_records_parsed",
                    parsed_record_count=len(parsed),
                    imported_email_count=len(emittable),
                )
            for record in emittable:
                raw_ref = record.setdefault("raw_ref", {})
                raw_ref["path"] = f"{path}::{member_name}"
                raw_ref["archive"] = str(path)
                raw_ref["archive_member"] = member_name
                records.append(record)
                if audit is not None:
                    audit["archive_member_imported_email_count"] += 1
            if limit is not None and len(records) >= limit:
                if audit is not None:
                    audit["limit_reached"] = True
                    audit["unvisited_archive_member_count_due_limit"] = max(0, len(members) - index - 1)
                return records
    if audit is not None and "unvisited_archive_member_count_due_limit" not in audit:
        audit["unvisited_archive_member_count_due_limit"] = 0
    return records


def is_safe_archive_member(member_path: PurePosixPath) -> bool:
    return bool(member_path.parts) and not member_path.is_absolute() and ".." not in member_path.parts


def archive_member_skip_reason(info: zipfile.ZipInfo):
    member_name = info.filename.replace("\\", "/")
    member_path = PurePosixPath(member_name)
    windows_path = PureWindowsPath(info.filename)
    suffix = Path(member_name).suffix.lower()
    if info.is_dir():
        return "directory"
    if not is_safe_archive_member(member_path) or windows_path.drive:
        return "unsafe_path"
    if archive_member_is_thunderbird_summary_index_path(member_name):
        return "thunderbird_summary_index"
    if (
        suffix not in SUPPORTED_ARCHIVE_EMAIL_EXTENSIONS
        and not archive_member_is_maildir_message_path(member_name)
        and not archive_member_is_thunderbird_mbox_path(member_name)
    ):
        return "unsupported_extension"
    return None


def archive_member_extension_label(member_name: str) -> str:
    if archive_member_is_thunderbird_mbox_path(member_name):
        return "<thunderbird-mbox>"
    if archive_member_is_maildir_message_path(member_name):
        return "<maildir>"
    return Path(member_name).suffix.lower() or "<none>"


def archive_member_is_maildir_message_path(member_name: str) -> bool:
    parts = PurePosixPath(member_name.replace("\\", "/")).parts
    if not parts:
        return False
    return len(parts) >= 2 and parts[-2] in MAILDIR_PARENT_NAMES and not parts[-1].startswith(".")


def archive_member_is_thunderbird_mbox_path(member_name: str) -> bool:
    normalized = member_name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if len(parts) < 3:
        return False
    name = parts[-1]
    if not name or name.startswith(".") or Path(name).suffix:
        return False
    lower_parts = [part.lower() for part in parts[:-1]]
    return any(part in THUNDERBIRD_MBOX_PARENT_NAMES for part in lower_parts)


def archive_member_is_thunderbird_summary_index_path(member_name: str) -> bool:
    return Path(member_name.replace("\\", "/")).suffix.lower() == THUNDERBIRD_SUMMARY_SUFFIX


def is_maildir_message_path(path: Path) -> bool:
    if path.name.startswith(".") or path.parent.name not in MAILDIR_PARENT_NAMES:
        return False
    return looks_like_rfc822_message(path)


def is_thunderbird_summary_index_path(path: Path) -> bool:
    return path.suffix.lower() == THUNDERBIRD_SUMMARY_SUFFIX


def is_thunderbird_mbox_path(path: Path) -> bool:
    if path.name.startswith(".") or path.suffix:
        return False
    lower_parts = [part.lower() for part in path.parts[:-1]]
    has_thunderbird_container = any(part in THUNDERBIRD_MBOX_PARENT_NAMES for part in lower_parts)
    has_summary_sibling = path.with_name(path.name + THUNDERBIRD_SUMMARY_SUFFIX).exists()
    if not (has_thunderbird_container or has_summary_sibling):
        return False
    return looks_like_mbox_file(path)


def looks_like_rfc822_message(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:4096].lower()
    except OSError:
        return False
    return any(marker in chunk for marker in EMAIL_HEADER_MARKERS)


def looks_like_mbox_file(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:4096].lower()
    except OSError:
        return False
    if not chunk.startswith(b"from "):
        return False
    return any(marker in chunk for marker in EMAIL_HEADER_MARKERS)


def apple_mail_emlx_message_bytes(raw: bytes) -> bytes:
    first_newline = raw.find(b"\n")
    if first_newline < 0:
        return raw
    count = raw[:first_newline].strip()
    if not count.isdigit():
        return raw
    start = first_newline + 1
    size = int(count)
    end = start + size
    if len(raw) >= end:
        return raw[start:end]
    return raw[start:]


def append_archive_member_result(audit: dict, member: str, *, status: str, reason: str = None, parsed_record_count: int = None, imported_email_count: int = None) -> None:
    results = audit.setdefault("archive_member_results", [])
    result = {"member": member, "status": status}
    if reason:
        result["reason"] = reason
    if parsed_record_count is not None:
        result["parsed_record_count"] = parsed_record_count
    if imported_email_count is not None:
        result["imported_email_count"] = imported_email_count
    results.append(result)


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
        "raw_ref": {"path": str(path), "row": row, "format": source_format_for_path(path)},
    }


def source_format_for_path(path: Path) -> str:
    if is_thunderbird_mbox_path(path):
        return "thunderbird_mbox"
    if is_maildir_message_path(path):
        return "maildir"
    suffix = path.suffix.lower().lstrip(".")
    return suffix or "rfc822"


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


EMAIL_SCOPE_POLICY_KEYS = (
    "allow_mailbox",
    "deny_mailbox",
    "allow_folder",
    "deny_folder",
    "allow_sender",
    "deny_sender",
    "allow_sender_domain",
    "deny_sender_domain",
    "allow_recipient",
    "deny_recipient",
    "allow_subject",
    "deny_subject",
    "allow_attachment",
    "deny_attachment",
    "allow_keyword",
    "deny_keyword",
)


def split_scope_values(values) -> list[str]:
    if values in (None, ""):
        return []
    if isinstance(values, (list, tuple, set)):
        raw_items = values
    else:
        raw_items = [values]
    out: list[str] = []
    seen = set()
    for item in raw_items:
        if isinstance(item, (list, tuple, set)):
            parts = split_scope_values(item)
        else:
            parts = [part.strip() for part in re.split(r"[,，;；]", str(item)) if part.strip()]
        for part in parts:
            key = part.lower()
            if key and key not in seen:
                seen.add(key)
                out.append(part)
    return out


def normalize_email_scope_policy(policy: dict = None) -> dict:
    policy = policy or {}
    return {key: split_scope_values(policy.get(key)) for key in EMAIL_SCOPE_POLICY_KEYS}


def email_scope_policy_configured(policy: dict) -> bool:
    return any(policy.get(key) for key in EMAIL_SCOPE_POLICY_KEYS)


def apply_email_scope_policy(emails: list[dict], policy: dict = None) -> tuple[list[dict], dict]:
    normalized_policy = normalize_email_scope_policy(policy)
    configured = email_scope_policy_configured(normalized_policy)
    candidates = list(emails)
    reason_counts = Counter()
    retained = []
    for record in candidates:
        reasons = email_scope_filter_reasons(record, normalized_policy) if configured else []
        if reasons:
            for reason in reasons:
                reason_counts[reason] += 1
            continue
        retained.append(record)
    audit = {
        "configured": configured,
        "filters": normalized_policy,
        "candidate_email_count": len(candidates),
        "retained_email_count": len(retained),
        "filtered_email_count": len(candidates) - len(retained),
        "filter_reason_counts": dict(sorted(reason_counts.items())),
        "filtered_all": configured and bool(candidates) and not retained,
        "policy_is_user_authorization_scope": True,
        "policy_does_not_assert_investment_relevance": True,
        "deny_rules_win_over_allow_rules": True,
        "allow_rule_semantics": {
            "mailbox_folder": "case-insensitive exact match unless wildcard is used",
            "sender_recipient_subject_attachment_keyword": "case-insensitive substring match unless wildcard is used",
            "sender_domain": "case-insensitive exact or subdomain match unless wildcard is used",
        },
    }
    return retained, audit


def attach_email_scope_policy_audit(audit: dict, scope_audit: dict) -> None:
    audit["email_scope_policy"] = scope_audit
    audit["scope_policy_candidate_email_count"] = scope_audit.get("candidate_email_count", 0)
    audit["scope_policy_retained_email_count"] = scope_audit.get("retained_email_count", 0)
    audit["scope_policy_filtered_email_count"] = scope_audit.get("filtered_email_count", 0)
    audit["scope_policy_filter_reason_counts"] = scope_audit.get("filter_reason_counts", {})
    audit["email_scope_policy_filtered_all"] = bool(scope_audit.get("filtered_all"))


def email_scope_filter_reasons(record: dict, policy: dict) -> list[str]:
    checks = [
        (
            "mailbox",
            policy.get("allow_mailbox", []),
            policy.get("deny_mailbox", []),
            [str(record.get("mailbox") or "")],
            scope_identity_match,
        ),
        (
            "folder",
            policy.get("allow_folder", []),
            policy.get("deny_folder", []),
            [str(record.get("folder") or "")],
            scope_identity_match,
        ),
        (
            "sender",
            policy.get("allow_sender", []),
            policy.get("deny_sender", []),
            email_text_candidates(record.get("from")),
            scope_text_match,
        ),
        (
            "sender_domain",
            policy.get("allow_sender_domain", []),
            policy.get("deny_sender_domain", []),
            email_domain_candidates(record.get("from")),
            scope_domain_match,
        ),
        (
            "recipient",
            policy.get("allow_recipient", []),
            policy.get("deny_recipient", []),
            email_text_candidates(record.get("to"), record.get("cc")),
            scope_text_match,
        ),
        (
            "subject",
            policy.get("allow_subject", []),
            policy.get("deny_subject", []),
            [str(record.get("subject") or "")],
            scope_text_match,
        ),
        (
            "attachment",
            policy.get("allow_attachment", []),
            policy.get("deny_attachment", []),
            email_attachment_names(record),
            scope_text_match,
        ),
        (
            "keyword",
            policy.get("allow_keyword", []),
            policy.get("deny_keyword", []),
            [email_scope_search_text(record)],
            scope_text_match,
        ),
    ]
    reasons: list[str] = []
    for name, allow_patterns, deny_patterns, values, matcher in checks:
        if deny_patterns and any_scope_match(values, deny_patterns, matcher):
            reasons.append(f"deny_{name}")
        if allow_patterns and not any_scope_match(values, allow_patterns, matcher):
            reasons.append(f"allow_{name}_mismatch")
    return reasons


def any_scope_match(values: list[str], patterns: list[str], matcher) -> bool:
    return any(matcher(value, pattern) for value in values if value not in (None, "") for pattern in patterns)


def scope_identity_match(value: str, pattern: str) -> bool:
    value_norm = str(value or "").strip().lower()
    pattern_norm = str(pattern or "").strip().lower()
    if not value_norm or not pattern_norm:
        return False
    if "*" in pattern_norm or "?" in pattern_norm:
        return fnmatch.fnmatch(value_norm, pattern_norm)
    return value_norm == pattern_norm


def scope_text_match(value: str, pattern: str) -> bool:
    value_norm = str(value or "").strip().lower()
    pattern_norm = str(pattern or "").strip().lower()
    if not value_norm or not pattern_norm:
        return False
    if "*" in pattern_norm or "?" in pattern_norm:
        return fnmatch.fnmatch(value_norm, pattern_norm)
    return pattern_norm in value_norm


def scope_domain_match(value: str, pattern: str) -> bool:
    domain = str(value or "").strip().lower().lstrip("@")
    pattern_norm = str(pattern or "").strip().lower().lstrip("@")
    if not domain or not pattern_norm:
        return False
    if "*" in pattern_norm or "?" in pattern_norm:
        return fnmatch.fnmatch(domain, pattern_norm)
    return domain == pattern_norm or domain.endswith(f".{pattern_norm}")


def email_text_candidates(*values) -> list[str]:
    texts = [str(value or "") for value in values if value not in (None, "")]
    addresses = []
    for display, address in getaddresses(texts):
        if display:
            addresses.append(display)
        if address:
            addresses.append(address)
    return [*texts, *addresses]


def email_domain_candidates(*values) -> list[str]:
    domains = set()
    texts = [str(value or "") for value in values if value not in (None, "")]
    for _display, address in getaddresses(texts):
        if "@" in address:
            domains.add(address.rsplit("@", 1)[1].lower())
    for text in texts:
        for match in re.findall(r"@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", text):
            domains.add(match.lower())
    return sorted(domains)


def email_attachment_names(record: dict) -> list[str]:
    names: list[str] = []
    for item in normalize_attachments(record.get("attachment_refs") or record.get("attachments") or []):
        if item.get("filename"):
            names.append(str(item["filename"]))
    return names


def email_scope_search_text(record: dict) -> str:
    values = [
        record.get("mailbox"),
        record.get("folder"),
        record.get("from"),
        record.get("to"),
        record.get("cc"),
        record.get("subject"),
        record.get("body"),
    ]
    values.extend(email_attachment_names(record))
    return "\n".join(str(value) for value in values if value not in (None, "", []))


def write_standard_email_package(
    out_dir: str,
    events: list[dict],
    *,
    collected_at: str = None,
    collection_audit: dict = None,
    package_schema: str,
) -> None:
    out = Path(out_dir).expanduser()
    write_events_jsonl(str(out / "lake" / "email" / "events.jsonl"), events)
    manifest = build_email_manifest(
        events,
        collected_at=collected_at,
        collection_audit=collection_audit,
        package_schema=package_schema,
    )
    write_json(str(out / "manifest.json"), manifest)
    write_email_summary(out / "SUMMARY.md", manifest)


def build_email_manifest(
    events: list[dict],
    *,
    collected_at: str = None,
    collection_audit: dict = None,
    package_schema: str,
) -> dict:
    kind_counts = Counter(event["kind"] for event in events)
    folder_counts = Counter((event.get("data") or {}).get("folder", "unknown") for event in events if event["kind"] == "email")
    mailbox_counts = Counter((event.get("data") or {}).get("mailbox", "unknown") for event in events if event["kind"] == "email")
    gap_only = bool(events) and all((event.get("data") or {}).get("gap") for event in events)
    audit = collection_audit or {}
    is_imap = package_schema == "collectorx.email_collect.manifest.v1"
    if gap_only:
        status = readiness_status_for_gap(events[0], audit=audit, is_imap=is_imap)
        source_scope = "none"
        next_action = next_action_for_gap(events[0], is_imap=is_imap)
    else:
        status = "events_collected"
        if is_imap:
            source_scope = "authorized_imap"
        elif int(audit.get("local_scan_imported_email_count") or 0) > 0:
            source_scope = "partial_authorized_local_scan_or_input"
        else:
            source_scope = "partial_authorized_input"
        next_action = "Feed lake/email/events.jsonl into email-research lens."
    field_coverage = build_email_field_coverage(events)
    body_policy = {
        "full_body_included": any("body" in (event.get("data") or {}) for event in events),
        "full_body_requires_event_include_body": True,
        "body_preview_char_limit": 300,
    }
    attachment_policy = {
        "attachment_refs_included": any((event.get("data") or {}).get("attachment_refs") for event in events),
        "attachment_bodies_included": False,
        "retained_fields": ["filename", "content_type", "size"],
    }
    collection_readiness = {
        "status": status,
        "can_enter_finclaw": bool(events) and not gap_only,
        "source_collection_scope": source_scope,
        "full_body_included": body_policy["full_body_included"],
        "next_action": next_action,
    }
    return {
        "schema": package_schema,
        "collector": "email",
        "collected_at": collected_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "event_count": len(events),
        "kind_counts": dict(sorted(kind_counts.items())),
        "folder_counts": dict(sorted(folder_counts.items())),
        "mailbox_counts": dict(sorted(mailbox_counts.items())),
        "field_coverage": field_coverage,
        "collection_readiness": collection_readiness,
        "body_policy": body_policy,
        "attachment_policy": attachment_policy,
        "mailbox_boundary_proof": build_mailbox_boundary_proof(
            events,
            audit=audit,
            is_imap=is_imap,
            field_coverage=field_coverage,
            body_policy=body_policy,
            attachment_policy=attachment_policy,
            collection_readiness=collection_readiness,
        ),
        "evidence_policy": {
            "generic_collector": True,
            "investor_wiki_requires_lens": "email-research",
            "collector_claims_investment_conclusion": False,
            "broker_trade_fact_source": False,
        },
        "collection_audit": audit,
    }


def build_import_manifest(events: list[dict], *, collected_at: str = None, import_audit: dict = None) -> dict:
    return build_email_manifest(
        events,
        collected_at=collected_at,
        collection_audit=import_audit,
        package_schema="collectorx.email_import.manifest.v1",
    )


def readiness_status_for_gap(event: dict, *, audit: dict, is_imap: bool) -> str:
    reason = (event.get("data") or {}).get("gap")
    if reason == "email_scope_policy_filtered_all":
        return "scope_policy_filtered_all"
    if reason == "email_imap_account_missing":
        return "needs_email_registered_account"
    if reason == "email_imap_no_messages":
        return "no_matching_mail_in_time_window"
    if reason == "email_imap_collection_failed":
        return audit.get("status") or "imap_collection_failed"
    if reason == "email_authorized_export_missing":
        return "needs_email_authorized_export"
    return "collection_gap"


def next_action_for_gap(event: dict, *, is_imap: bool) -> str:
    reason = (event.get("data") or {}).get("gap")
    if reason == "email_scope_policy_filtered_all":
        return "Review or relax the email scope policy, then rerun the collector."
    if reason == "email_imap_account_missing":
        return "Register at least one mailbox with password_env, then run collect --out-dir again."
    if reason == "email_imap_no_messages":
        return "Increase --days, review folders, or feed another authorized email source."
    if reason == "email_imap_collection_failed":
        return "Review collection_audit account/folder errors and rerun after fixing authorization."
    if reason == "email_authorized_export_missing":
        return "Provide authorized local email exports or run import --local-scan on an authorized mail root."
    return "Resolve the collection gap and rerun the collector."


def build_email_field_coverage(events: list[dict]) -> dict:
    email_events = [event for event in events if event.get("kind") == "email"]
    fields = [
        "mailbox",
        "folder",
        "from",
        "to",
        "cc",
        "subject",
        "body_preview",
        "has_body",
        "attachment_refs",
        "message_id",
    ]
    coverage = {}
    for field in fields:
        if field == "message_id":
            count = sum(1 for event in email_events if (event.get("raw_ref") or {}).get("message_id"))
        else:
            count = sum(1 for event in email_events if (event.get("data") or {}).get(field) not in (None, "", []))
        coverage[field] = {"present": count, "missing": max(len(email_events) - count, 0)}
    return {
        "email_event_count": len(email_events),
        "fields": coverage,
    }


def build_mailbox_boundary_proof(
    events: list[dict],
    *,
    audit: dict,
    is_imap: bool,
    field_coverage: dict,
    body_policy: dict,
    attachment_policy: dict,
    collection_readiness: dict,
) -> dict:
    email_events = [event for event in events if event.get("kind") == "email"]
    source_type = audit.get("source_type") or ("imap" if is_imap else "authorized_email_export")
    mailbox_values = sorted(
        {
            str((event.get("data") or {}).get("mailbox"))
            for event in email_events
            if (event.get("data") or {}).get("mailbox")
        }
    )
    folder_values = sorted(
        {
            str((event.get("data") or {}).get("folder"))
            for event in email_events
            if (event.get("data") or {}).get("folder")
        }
    )
    required_fields = ["from", "to", "subject", "body_preview", "message_id"]
    present_required = [
        field
        for field in required_fields
        if (field_coverage.get("fields") or {}).get(field, {}).get("present", 0) > 0
    ]
    proof = {
        "source_type": source_type,
        "proof_level": mailbox_boundary_proof_level(email_events, audit=audit, is_imap=is_imap),
        "email_event_count": len(email_events),
        "mailbox_count": len(mailbox_values),
        "folder_count": len(folder_values),
        "mailboxes": mailbox_values,
        "folders": folder_values,
        "required_field_presence": {
            "required_fields": required_fields,
            "present_fields": present_required,
            "missing_fields": [field for field in required_fields if field not in present_required],
        },
        "body_capture": {
            "body_preview_included": (field_coverage.get("fields") or {}).get("body_preview", {}).get("present", 0) > 0,
            "full_body_included": body_policy["full_body_included"],
            "full_body_requires_event_include_body": body_policy["full_body_requires_event_include_body"],
            "body_preview_char_limit": body_policy["body_preview_char_limit"],
        },
        "attachment_capture": {
            "attachment_refs_included": attachment_policy["attachment_refs_included"],
            "attachment_bodies_included": attachment_policy["attachment_bodies_included"],
            "retained_fields": attachment_policy["retained_fields"],
        },
        "complete_mailbox_claimed": False,
        "complete_account_history_claimed": False,
        "bounded_by_user_selected_accounts_folders_days": bool(is_imap),
        "authorization_scope_boundary": email_authorization_scope_boundary_from_audit(audit),
        "investor_wiki_requires_lens": "email-research",
        "collector_writes_investor_wiki_directly": False,
        "can_enter_finclaw": collection_readiness["can_enter_finclaw"],
    }
    if is_imap:
        proof["imap_boundary"] = imap_boundary_from_audit(audit)
    else:
        proof["local_export_boundary"] = local_export_boundary_from_audit(audit)
    return proof


def mailbox_boundary_proof_level(email_events: list[dict], *, audit: dict, is_imap: bool) -> str:
    if not email_events:
        if audit.get("email_scope_policy_filtered_all"):
            return "email_scope_policy_filtered_all"
        if is_imap and audit.get("status") == "no_registered_account":
            return "no_authorized_mailbox"
        if is_imap:
            return "authorized_imap_gap"
        return "no_authorized_email_export"
    if is_imap:
        if audit.get("status") == "partial_success":
            return "partial_authorized_imap_folder_window"
        return "authorized_imap_folder_window"
    if int(audit.get("local_scan_imported_email_count") or 0) > 0:
        return "authorized_local_email_scan_boundary"
    return "authorized_local_export_boundary"


def imap_boundary_from_audit(audit: dict) -> dict:
    accounts = audit.get("accounts") if isinstance(audit.get("accounts"), list) else []
    requested_folders = sorted(
        {
            str(folder)
            for account in accounts
            for folder in account.get("folders_requested", [])
            if folder
        }
    )
    collected_folders = sorted(
        {
            str(folder.get("folder"))
            for account in accounts
            for folder in account.get("folder_results", [])
            if folder.get("status") == "collected" and folder.get("folder")
        }
    )
    return {
        "requested_account": audit.get("requested_account"),
        "configured_account_count": audit.get("configured_account_count", 0),
        "selected_account_count": audit.get("selected_account_count", 0),
        "account_status_counts": audit.get("account_status_counts", {}),
        "folder_status_counts": audit.get("folder_status_counts", {}),
        "requested_folders": requested_folders,
        "collected_folders": collected_folders,
        "days_windows": sorted({account.get("days") for account in accounts if account.get("days") is not None}),
        "limit_values": sorted({account.get("limit") for account in accounts if account.get("limit") is not None}),
        "matched_message_count": audit.get("matched_message_count", 0),
        "fetched_message_count": audit.get("fetched_message_count", 0),
        "skipped_fetch_count": audit.get("skipped_fetch_count", 0),
        "read_only": audit.get("read_only", True),
        "password_material_in_output": audit.get("password_material_in_output", False),
        "scope_policy_candidate_email_count": audit.get("scope_policy_candidate_email_count", 0),
        "scope_policy_retained_email_count": audit.get("scope_policy_retained_email_count", 0),
        "scope_policy_filtered_email_count": audit.get("scope_policy_filtered_email_count", 0),
        "email_scope_policy_filtered_all": audit.get("email_scope_policy_filtered_all", False),
    }


def local_export_boundary_from_audit(audit: dict) -> dict:
    return {
        "input_count": audit.get("input_count", 0),
        "requested_inputs": audit.get("requested_inputs", []),
        "resolved_input_file_count": audit.get("resolved_input_file_count", 0),
        "input_missing_count": audit.get("input_missing_count", 0),
        "pre_scope_policy_email_count": audit.get("pre_scope_policy_email_count", 0),
        "imported_email_count": audit.get("imported_email_count", 0),
        "parsed_record_count": audit.get("parsed_record_count", 0),
        "extension_counts": audit.get("extension_counts", {}),
        "skipped_reason_counts": audit.get("skipped_reason_counts", {}),
        "archive_count": audit.get("archive_count", 0),
        "archive_member_count": audit.get("archive_member_count", 0),
        "archive_member_imported_email_count": audit.get("archive_member_imported_email_count", 0),
        "skipped_archive_member_reason_counts": audit.get("skipped_archive_member_reason_counts", {}),
        "apple_mail_emlx_file_count": audit.get("apple_mail_emlx_file_count", 0),
        "maildir_message_file_count": audit.get("maildir_message_file_count", 0),
        "thunderbird_mbox_file_count": audit.get("thunderbird_mbox_file_count", 0),
        "local_scan_requested": audit.get("local_scan_requested", False),
        "local_scan_platform": audit.get("local_scan_platform"),
        "local_scan_roots": audit.get("local_scan_roots", []),
        "local_scan_root_statuses": audit.get("local_scan_root_statuses", []),
        "local_scan_root_type_counts": audit.get("local_scan_root_type_counts", {}),
        "local_scan_candidate_file_count": audit.get("local_scan_candidate_file_count", 0),
        "local_scan_candidate_files": audit.get("local_scan_candidate_files", []),
        "local_scan_candidate_format_counts": audit.get("local_scan_candidate_format_counts", {}),
        "local_scan_candidate_selection": audit.get("local_scan_candidate_selection", {}),
        "local_scan_scanned_file_count": audit.get("local_scan_scanned_file_count", 0),
        "local_scan_skipped_file_count": audit.get("local_scan_skipped_file_count", 0),
        "local_scan_skipped_reason_counts": audit.get("local_scan_skipped_reason_counts", {}),
        "local_scan_thunderbird_summary_index_skipped_count": audit.get("local_scan_thunderbird_summary_index_skipped_count", 0),
        "local_scan_truncated_root_count": audit.get("local_scan_truncated_root_count", 0),
        "local_scan_imported_email_count": audit.get("local_scan_imported_email_count", 0),
        "pre_scope_policy_local_scan_email_count": audit.get("pre_scope_policy_local_scan_email_count", 0),
        "limit": audit.get("limit"),
        "limit_reached": audit.get("limit_reached", False),
        "attachment_bodies_included": audit.get("attachment_bodies_included", False),
        "archive_path_traversal_members_collected": audit.get("archive_path_traversal_members_collected", False),
        "windows_drive_archive_members_collected": audit.get("windows_drive_archive_members_collected", False),
        "scope_policy_candidate_email_count": audit.get("scope_policy_candidate_email_count", 0),
        "scope_policy_retained_email_count": audit.get("scope_policy_retained_email_count", 0),
        "scope_policy_filtered_email_count": audit.get("scope_policy_filtered_email_count", 0),
        "email_scope_policy_filtered_all": audit.get("email_scope_policy_filtered_all", False),
    }


def email_authorization_scope_boundary_from_audit(audit: dict) -> dict:
    scope = audit.get("email_scope_policy") or {}
    return {
        "policy_configured": bool(scope.get("configured")),
        "filters": scope.get("filters", {}),
        "candidate_email_count": scope.get("candidate_email_count", 0),
        "retained_email_count": scope.get("retained_email_count", 0),
        "filtered_email_count": scope.get("filtered_email_count", 0),
        "filter_reason_counts": scope.get("filter_reason_counts", {}),
        "filtered_all": bool(scope.get("filtered_all")),
        "policy_is_user_authorization_scope": scope.get("policy_is_user_authorization_scope", True),
        "policy_does_not_assert_investment_relevance": scope.get("policy_does_not_assert_investment_relevance", True),
    }


def increment_counter(audit: dict, key: str, value: str) -> None:
    counts = audit.setdefault(key, {})
    counts[value] = int(counts.get(value, 0)) + 1


def finalize_import_audit(audit: dict) -> None:
    for key in (
        "extension_counts",
        "skipped_extension_counts",
        "skipped_reason_counts",
        "archive_member_extension_counts",
        "skipped_archive_member_extension_counts",
        "skipped_archive_member_reason_counts",
        "local_scan_root_type_counts",
        "local_scan_candidate_format_counts",
        "local_scan_skipped_reason_counts",
        "scope_policy_filter_reason_counts",
    ):
        audit[key] = dict(sorted((audit.get(key) or {}).items()))


def write_email_summary(path: Path, manifest: dict) -> None:
    lines = [
        "# Email Collector Package",
        "",
        "- collector: `email`",
        f"- event_count: {manifest['event_count']}",
        f"- readiness: `{manifest['collection_readiness']['status']}`",
        f"- source_scope: `{manifest['collection_readiness']['source_collection_scope']}`",
        f"- mailbox_boundary: `{manifest['mailbox_boundary_proof']['proof_level']}`",
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


def build_imap_collection_audit(
    *,
    accounts: list[dict],
    account_audits: list[dict],
    account_id: str,
    status: str,
) -> dict:
    status_counts = Counter(item.get("status", "unknown") for item in account_audits)
    folder_status_counts = Counter(
        folder.get("status", "unknown")
        for item in account_audits
        for folder in item.get("folder_results", [])
    )
    return {
        "source_type": "imap",
        "requested_account": account_id or "all",
        "configured_account_count": len(accounts),
        "selected_account_count": len(accounts),
        "account_status_counts": dict(sorted(status_counts.items())),
        "folder_status_counts": dict(sorted(folder_status_counts.items())),
        "collected_email_count": sum(int(item.get("collected_email_count", 0)) for item in account_audits),
        "matched_message_count": sum(int(item.get("matched_message_count", 0)) for item in account_audits),
        "fetched_message_count": sum(int(item.get("fetched_message_count", 0)) for item in account_audits),
        "skipped_fetch_count": sum(int(item.get("skipped_fetch_count", 0)) for item in account_audits),
        "status": status,
        "read_only": True,
        "password_material_in_output": False,
        "accounts": account_audits,
    }


def resolve_imap_audit_status(account_audits: list[dict], emails: list[dict]) -> str:
    if emails:
        failed_count = sum(1 for item in account_audits if item.get("status") not in {"collected", "no_messages"})
        return "partial_success" if failed_count else "events_collected"
    statuses = {item.get("status") for item in account_audits}
    if not statuses:
        return "no_registered_account"
    if statuses == {"no_messages"}:
        return "no_matching_mail_in_time_window"
    if "missing_password" in statuses:
        return "missing_password_env"
    if "login_failed" in statuses:
        return "login_failed"
    if "connect_failed" in statuses:
        return "connect_failed"
    return "imap_collection_failed"


def gap_reason_for_imap_audit(status: str) -> str:
    if status == "scope_policy_filtered_all":
        return "email_scope_policy_filtered_all"
    if status == "no_registered_account":
        return "email_imap_account_missing"
    if status == "no_matching_mail_in_time_window":
        return "email_imap_no_messages"
    return "email_imap_collection_failed"


def _collect_account_emails(
    account: dict,
    *,
    days: int,
    folders: list[str],
    limit: int = None,
) -> list[dict]:
    emails, audit = _collect_account_emails_with_audit(account, days=days, folders=folders, limit=limit)
    if audit.get("status") in {"collected", "no_messages"}:
        return emails
    print(f"ERROR: {account.get('email')} 邮箱采集失败: {audit.get('status')}")
    sys.exit(1)


def _collect_account_emails_with_audit(
    account: dict,
    *,
    days: int,
    folders: list[str],
    limit: int = None,
) -> tuple[list[dict], dict]:
    audit = {
        "account_id": account.get("id") or _account_id(account.get("email", "")),
        "email": account.get("email"),
        "provider": account.get("provider", "custom"),
        "host": account.get("host"),
        "folders_requested": list(folders),
        "days": days,
        "limit": limit,
        "password_env_configured": bool(account.get("password_env")),
        "legacy_password_present": bool(account.get("password")),
        "folder_results": [],
        "matched_message_count": 0,
        "fetched_message_count": 0,
        "skipped_fetch_count": 0,
        "collected_email_count": 0,
        "status": "started",
    }
    password = _resolve_password(account)
    if not password:
        audit["status"] = "missing_password"
        audit["error"] = "Password environment variable is not set."
        return [], audit

    collected: list[dict] = []
    mail = None
    try:
        mail = imaplib.IMAP4_SSL(account["host"])
    except Exception as exc:
        audit["status"] = "connect_failed"
        audit["error"] = safe_error_text(exc)
        return collected, audit

    try:
        mail.login(account["email"], password)
    except Exception as exc:
        audit["status"] = "login_failed"
        audit["error"] = safe_error_text(exc)
        try:
            mail.logout()
        except Exception:
            pass
        return collected, audit

    try:
        for folder_name in folders:
            folder_audit = {
                "folder": folder_name,
                "status": "started",
                "matched_message_count": 0,
                "fetched_message_count": 0,
                "skipped_fetch_count": 0,
            }
            audit["folder_results"].append(folder_audit)
            try:
                status, _select_data = mail.select(folder_name)
                if status != "OK":
                    folder_audit["status"] = "select_failed"
                    folder_audit["select_status"] = status
                    continue
                since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
                status, messages = mail.search(None, f'(SINCE "{since_date}")')
                if status != "OK":
                    folder_audit["status"] = "search_failed"
                    folder_audit["search_status"] = status
                    continue

                msg_ids = messages[0].split()
                folder_audit["matched_message_count"] = len(msg_ids)
                audit["matched_message_count"] += len(msg_ids)
                if limit:
                    msg_ids = msg_ids[-limit:]

                for msg_id in msg_ids:
                    try:
                        status, msg_data = mail.fetch(msg_id, "(RFC822)")
                        if status != "OK":
                            folder_audit["skipped_fetch_count"] += 1
                            audit["skipped_fetch_count"] += 1
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
                        folder_audit["fetched_message_count"] += 1
                        audit["fetched_message_count"] += 1
                    except Exception as exc:
                        folder_audit["skipped_fetch_count"] += 1
                        audit["skipped_fetch_count"] += 1
                        folder_audit["last_fetch_error"] = safe_error_text(exc)
                folder_audit["status"] = "collected" if folder_audit["fetched_message_count"] else "no_messages"
            except Exception as exc:
                folder_audit["status"] = "folder_error"
                folder_audit["error"] = safe_error_text(exc)
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    audit["collected_email_count"] = len(collected)
    if collected:
        audit["status"] = "collected"
    elif any(folder.get("status") in {"select_failed", "search_failed"} for folder in audit["folder_results"]):
        audit["status"] = "folder_failed"
    else:
        audit["status"] = "no_messages"
    return collected, audit


def safe_error_text(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    text = text.replace("\n", " ").replace("\r", " ").strip()
    return text[:240]


def _resolve_password(account: dict) -> str:
    if account.get("password_env"):
        return os.environ.get(account["password_env"], "")
    return account.get("password", "")


def add_email_scope_policy_args(parser) -> None:
    parser.add_argument("--allow-mailbox", action="append", help="只保留匹配的邮箱账号，可重复或逗号分隔")
    parser.add_argument("--deny-mailbox", action="append", help="排除匹配的邮箱账号，可重复或逗号分隔")
    parser.add_argument("--allow-folder", action="append", help="只保留匹配的邮箱文件夹，可重复或逗号分隔")
    parser.add_argument("--deny-folder", action="append", help="排除匹配的邮箱文件夹，可重复或逗号分隔")
    parser.add_argument("--allow-sender", action="append", help="只保留匹配的发件人/发件地址，可重复或逗号分隔")
    parser.add_argument("--deny-sender", action="append", help="排除匹配的发件人/发件地址，可重复或逗号分隔")
    parser.add_argument("--allow-sender-domain", action="append", help="只保留匹配的发件域名，可重复或逗号分隔")
    parser.add_argument("--deny-sender-domain", action="append", help="排除匹配的发件域名，可重复或逗号分隔")
    parser.add_argument("--allow-recipient", action="append", help="只保留匹配的收件人/抄送人，可重复或逗号分隔")
    parser.add_argument("--deny-recipient", action="append", help="排除匹配的收件人/抄送人，可重复或逗号分隔")
    parser.add_argument("--allow-subject", action="append", help="只保留主题匹配的邮件，可重复或逗号分隔")
    parser.add_argument("--deny-subject", action="append", help="排除主题匹配的邮件，可重复或逗号分隔")
    parser.add_argument("--allow-attachment", action="append", help="只保留附件名匹配的邮件，可重复或逗号分隔")
    parser.add_argument("--deny-attachment", action="append", help="排除附件名匹配的邮件，可重复或逗号分隔")
    parser.add_argument("--allow-keyword", action="append", help="只保留正文预览/主题/联系人/附件名含关键词的邮件，可重复或逗号分隔")
    parser.add_argument("--deny-keyword", action="append", help="排除正文预览/主题/联系人/附件名含关键词的邮件，可重复或逗号分隔")


def email_scope_policy_from_args(args) -> dict:
    return normalize_email_scope_policy({key: getattr(args, key, None) for key in EMAIL_SCOPE_POLICY_KEYS})


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
    col_parser.add_argument("--out-dir", help="输出标准采集包目录")
    col_parser.add_argument("--source", default="IMAP 邮件", help="事件source字段")
    col_parser.add_argument("--collected-at", help="事件collected_at字段，默认当前时间")
    col_parser.add_argument("--event-include-body", action="store_true", help="事件中包含完整正文，默认只包含预览")
    add_email_scope_policy_args(col_parser)

    # import命令
    import_parser = subparsers.add_parser("import", help="导入用户授权的本地邮件导出文件/目录，或扫描授权本机邮箱目录")
    import_parser.add_argument("--input", action="append", help="本地邮件导出文件或目录，可重复；支持 EML/EMLX/Maildir/MBOX/JSON/JSONL/CSV/TSV/ZIP")
    import_parser.add_argument("--local-scan", action="store_true", help="扫描授权本机邮箱目录中的 EML/EMLX/Maildir/MBOX/JSON/CSV/ZIP 邮件文件")
    import_parser.add_argument("--platform", choices=sorted(SUPPORTED_LOCAL_SCAN_PLATFORMS), default="auto", help="本机邮箱扫描平台适配器")
    import_parser.add_argument("--container-root", help="用户授权的本机邮箱目录；不填则按平台尝试常见邮件目录")
    import_parser.add_argument("--probe-export", help="导出本机邮箱扫描探测报告 JSON")
    import_parser.add_argument("--out-dir", help="输出标准采集包目录")
    import_parser.add_argument("--event-export", help="导出CollectorX Event JSONL路径")
    import_parser.add_argument("--limit", type=int, help="限制数量")
    import_parser.add_argument("--source", default="授权邮件导出", help="事件source字段")
    import_parser.add_argument("--collected-at", help="事件collected_at字段，默认当前时间")
    import_parser.add_argument("--event-include-body", action="store_true", help="事件中包含完整正文，默认只包含预览")
    add_email_scope_policy_args(import_parser)
    
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
            out_dir=args.out_dir,
            source=args.source,
            collected_at=args.collected_at,
            event_include_body=args.event_include_body,
            account_id=args.account,
            email_scope_policy=email_scope_policy_from_args(args),
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
            local_scan=args.local_scan,
            platform=args.platform,
            container_root=args.container_root,
            probe_export=args.probe_export,
            email_scope_policy=email_scope_policy_from_args(args),
        )
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
