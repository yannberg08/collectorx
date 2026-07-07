"""
qq.parser — QQ chat record discovery, NT store probing, and normalization.
"""

from __future__ import annotations

import sqlite3
import shutil
import subprocess
import tempfile
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

NT_HEADER = b"SQLite header 3\x00"
NT_MARKER = b"QQ_NT DB"
NT_HEADER_BYTES = 1024
NT_CIPHER_PAGE_SIZE = 4096
NT_DB_ROLES = {
    "nt_msg.db": "messages",
    "guild_msg.db": "guild_messages",
    "profile_info.db": "contacts",
    "group_info.db": "groups",
    "recent_contact.db": "recent_contacts",
    "files_in_chat.db": "files",
    "rich_media.db": "media",
    "collection.db": "favorites",
    "settings.db": "settings",
    "misc.db": "misc",
}


def find_qq_db_dir() -> Optional[Path]:
    """自动查找QQ数据库目录"""
    import sys
    candidates = []
    
    if sys.platform == "darwin":
        qq_dir = Path.home() / "Library/Containers/com.tencent.qq/Data/Library/Application Support/QQ"
        if qq_dir.exists():
            # QQ NT for macOS stores account data under nt_qq_<hash>/nt_db.
            for nt_dir in qq_dir.glob("nt_qq_*/nt_db"):
                if nt_dir.is_dir() and list(nt_dir.glob("*.db")):
                    candidates.append(nt_dir)

            # Older QQ layouts used a numeric account directory with Msg/.
            for user_dir in qq_dir.iterdir():
                if user_dir.is_dir() and user_dir.name.isdigit():
                    msg_dir = user_dir / "Msg"
                    if msg_dir.exists():
                        candidates.append(msg_dir)
    
    elif sys.platform == "win32":
        documents = Path.home() / "Documents"
        tencent_files = documents / "Tencent Files"
        if tencent_files.exists():
            for user_dir in tencent_files.iterdir():
                if user_dir.is_dir() and user_dir.name.isdigit():
                    nt_dir = user_dir / "nt_qq" / "nt_db"
                    if nt_dir.exists():
                        candidates.append(nt_dir)
                    msg_dir = user_dir / "Msg"
                    if msg_dir.exists():
                        candidates.append(msg_dir)
    
    elif sys.platform == "linux":
        linux_paths = [
            Path.home() / ".local/share/QQ",
            Path.home() / ".QQ",
            Path("/opt/QQ"),
        ]
        for qq_base in linux_paths:
            if qq_base.exists():
                for user_dir in qq_base.iterdir():
                    if user_dir.is_dir() and user_dir.name.isdigit():
                        msg_dir = user_dir / "Msg"
                        if msg_dir.exists():
                            candidates.append(msg_dir)
    
    if not candidates:
        return None
    
    candidates = [path for path in candidates if list(path.rglob("*.db"))]
    if not candidates:
        return None
    candidates.sort(key=lambda p: max(f.stat().st_mtime for f in p.rglob("*.db")), reverse=True)
    return candidates[0]


def get_db_path(db_dir: Path) -> Optional[Path]:
    """获取数据库文件路径"""
    # Prefer already-decrypted QQ NT message databases if the user prepared one.
    for name in (
        "nt_msg.decrypted.db",
        "nt_msg.plain.db",
        "nt_msg.sqlite",
        "decrypted_db/nt_msg.db",
        "plaintext/nt_msg.db",
    ):
        candidate = db_dir / name
        if candidate.exists() and _is_sqlite_readable(candidate):
            return candidate

    nt_msg = db_dir / "nt_msg.db"
    if nt_msg.exists() and is_nt_wrapped_db(nt_msg):
        return None

    for db_file in db_dir.rglob("*.db"):
        if is_nt_wrapped_db(db_file):
            continue
        if "Msg" in db_file.name or "msg" in db_file.name:
            return db_file
    return None


def probe_db_dir(db_dir: Path) -> Dict[str, Any]:
    """Inspect QQ database structure without reading message content."""
    nt_probe = probe_nt_db_dir(db_dir)
    if nt_probe:
        return nt_probe

    db_files = sorted(db_dir.rglob("*.db"))
    result: Dict[str, Any] = {
        "db_dir": str(db_dir),
        "db_file_count": len(db_files),
        "candidate_db": None,
        "message_table": None,
        "message_columns": [],
        "message_count": None,
        "status": "not_found",
    }
    db_path = get_db_path(db_dir)
    if not db_path:
        return result

    result["candidate_db"] = str(db_path)
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        table = _find_message_table(cursor)
        result["message_table"] = table
        result["message_columns"] = _table_columns(cursor, table)
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        result["message_count"] = int(cursor.fetchone()[0])
        result["status"] = "ok"
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return result


def probe_nt_db_dir(db_dir: Path) -> Optional[Dict[str, Any]]:
    """Probe a QQ NT nt_db directory without reading user message content."""
    db_files = _direct_db_files(db_dir)
    if not db_files:
        return None

    wrapped = [path for path in db_files if is_nt_wrapped_db(path)]
    role_files = {NT_DB_ROLES.get(path.name, _infer_nt_role(path.name)): path for path in db_files}
    looks_like_nt_dir = (
        bool(wrapped)
        or (db_dir.name == "nt_db" and any(path.name in NT_DB_ROLES for path in db_files))
        or any(path.name in {"nt_msg.db", "profile_info.db", "group_info.db"} for path in db_files)
    )
    if not looks_like_nt_dir:
        return None

    stores = [_probe_nt_store(path) for path in sorted(db_files, key=lambda p: p.name)]
    raw_capabilities = {
        "contacts": "contacts" in role_files,
        "groups": "groups" in role_files,
        "messages": "messages" in role_files,
        "guild_messages": "guild_messages" in role_files,
        "recent_contacts": "recent_contacts" in role_files,
        "files": "files" in role_files,
        "media": "media" in role_files,
    }
    readable_plaintext = [path for path in db_files if _is_sqlite_readable(path)]
    read_capabilities = {
        "contacts": any(path.name == "profile_info.db" for path in readable_plaintext),
        "groups": any(path.name == "group_info.db" for path in readable_plaintext),
        "messages": any(path.name == "nt_msg.db" for path in readable_plaintext),
        "guild_messages": any(path.name == "guild_msg.db" for path in readable_plaintext),
    }
    status = "ok" if read_capabilities["messages"] else "needs_decryption"
    message = (
        "QQ NT 数据库已发现，但需要运行时 passphrase 与 SQLCipher 解密后才能读取联系人、群和消息正文。"
        if status == "needs_decryption"
        else "QQ NT 明文数据库可读取。"
    )
    account_hash = _account_hash_from_nt_dir(db_dir)
    result: Dict[str, Any] = {
        "status": status,
        "store_format": "qq_nt_sqlcipher_wrapped" if wrapped else "qq_nt_sqlite",
        "db_dir": str(db_dir),
        "account_hash": account_hash,
        "db_file_count": len(db_files),
        "stores": stores,
        "raw_capabilities": raw_capabilities,
        "read_capabilities": read_capabilities,
        "requires_passphrase": status == "needs_decryption",
        "requires_sqlcipher": status == "needs_decryption",
        "nt_header_bytes": NT_HEADER_BYTES,
        "cipher_page_size": NT_CIPHER_PAGE_SIZE,
        "message": message,
    }
    if wrapped and account_hash:
        result["candidate_key_material"] = _summarize_candidate_key_material(account_hash, wrapped[0])
    return result


def is_nt_wrapped_db(path: Path) -> bool:
    """Return true for QQ NT databases with the custom 1024-byte wrapper."""
    try:
        head = path.read_bytes()[:128]
    except OSError:
        return False
    return head.startswith(NT_HEADER) and NT_MARKER in head


def prepare_nt_clean_copies(db_dir: Path, out_dir: Path, *, include_roles: Optional[List[str]] = None) -> Dict[str, Any]:
    """Strip the 1024-byte QQ NT wrapper into clean SQLCipher files.

    The output remains encrypted. It is safe to hand to SQLCipher/DB Browser
    together with the passphrase, and this function never prints or stores that
    passphrase.
    """
    include = set(include_roles or [])
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {
        "source_db_dir": str(db_dir),
        "output_dir": str(out_dir),
        "nt_header_bytes": NT_HEADER_BYTES,
        "cipher_page_size": NT_CIPHER_PAGE_SIZE,
        "files": [],
    }
    for db_file in _direct_db_files(db_dir):
        role = NT_DB_ROLES.get(db_file.name, _infer_nt_role(db_file.name))
        if include and role not in include and db_file.name not in include:
            continue
        if not is_nt_wrapped_db(db_file):
            continue
        target = out_dir / db_file.name.replace(".db", ".clean.db")
        with db_file.open("rb") as src, target.open("wb") as dst:
            src.seek(NT_HEADER_BYTES)
            shutil.copyfileobj(src, dst)
        manifest["files"].append(
            {
                "source": str(db_file),
                "output": str(target),
                "role": role,
                "size": target.stat().st_size,
            }
        )
    return manifest


def decrypt_nt_with_sqlcipher(
    db_dir: Path,
    out_dir: Path,
    *,
    passphrase: str,
    include_roles: Optional[List[str]] = None,
    sqlcipher_bin: str = "sqlcipher",
) -> Dict[str, Any]:
    """Decrypt QQ NT databases with an external sqlcipher binary."""
    if not shutil.which(sqlcipher_bin):
        return {
            "status": "missing_sqlcipher",
            "message": f"未找到 {sqlcipher_bin}，请先安装 SQLCipher 或提供可执行文件路径。",
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    include = set(include_roles or [])
    results = []
    with tempfile.TemporaryDirectory(prefix="collectorx-qq-nt-") as tmp:
        tmp_dir = Path(tmp)
        clean_manifest = prepare_nt_clean_copies(db_dir, tmp_dir, include_roles=include_roles)
        for item in clean_manifest["files"]:
            role = item["role"]
            if include and role not in include and Path(item["source"]).name not in include:
                continue
            clean_path = Path(item["output"])
            out_path = out_dir / Path(item["source"]).name
            ok, message = _sqlcipher_export(clean_path, out_path, passphrase, sqlcipher_bin)
            results.append(
                {
                    "source": item["source"],
                    "output": str(out_path),
                    "role": role,
                    "status": "ok" if ok else "error",
                    "message": message,
                }
            )
    return {
        "status": "ok" if results and all(item["status"] == "ok" for item in results) else "partial_or_error",
        "output_dir": str(out_dir),
        "files": results,
    }


def read_nt_entities(db_dir: Path, *, limit_per_table: Optional[int] = None) -> Dict[str, Any]:
    """Read contacts/groups/recent-contact rows from decrypted QQ NT databases.

    QQ NT relation-chain schemas change across versions. This reader uses table
    and column heuristics and preserves raw row fields so the downstream
    adapter can be tightened after seeing a real decrypted schema.
    """
    result: Dict[str, Any] = {
        "db_dir": str(db_dir),
        "contacts": [],
        "groups": [],
        "recent_contacts": [],
        "tables": [],
        "status": "ok",
    }
    role_to_file = {
        "contacts": db_dir / "profile_info.db",
        "groups": db_dir / "group_info.db",
        "recent_contacts": db_dir / "recent_contact.db",
    }
    for role, path in role_to_file.items():
        if not path.exists():
            result["tables"].append({"role": role, "path": str(path), "status": "missing"})
            continue
        if not _is_sqlite_readable(path):
            result["tables"].append({"role": role, "path": str(path), "status": "not_readable"})
            if result["status"] == "ok":
                result["status"] = "partial"
            continue
        _read_entity_db(path, role, result, limit_per_table=limit_per_table)
    return result


def read_message_rows(
    db_path: Path,
    *,
    limit: Optional[int] = None,
    keyword: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read rows from a QQ-like message table as dictionaries.

    This is intentionally conservative. Real QQ NT schemas vary, so the caller
    still needs to verify fixtures from each platform/version before claiming
    full support.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        nt_tables = _find_nt_message_tables(cursor)
        if nt_tables:
            return _read_nt_message_rows(cursor, nt_tables, limit=limit, keyword=keyword)

        table = _find_message_table(cursor)
        columns = _table_columns(cursor, table)
        text_col = _first_present(columns, ["content", "msgContent", "msg", "message", "text"])
        time_col = _first_present(columns, ["msgTime", "time", "timestamp", "createTime", "created_at"])

        sql = f"SELECT * FROM {table}"
        params: List[Any] = []
        if keyword and text_col:
            sql += f" WHERE {text_col} LIKE ?"
            params.append(f"%{keyword}%")
        if time_col:
            sql += f" ORDER BY {time_col} DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def normalize_message(row: Dict[str, Any], *, owner_uin: Optional[str] = None) -> Dict[str, Any]:
    """Normalize one QQ message row into CollectorX-friendly fields."""
    chat_id = _coalesce(row, ["chat_id", "peerUin", "peer_uid", "uin", "conversation_id", "chat"])
    chat_name = _coalesce(row, ["chat_name", "chatName", "peerName", "peer_name", "uinName", "conversation_name"])
    sender = _coalesce(row, ["sender", "senderUin", "sender_uin", "fromUin", "from_uid", "from"])
    sender_name = _coalesce(row, ["sender_name", "senderName", "fromName", "from_name", "nickname", "nickName"])
    message_id = _coalesce(row, ["msgId", "msg_id", "message_id", "id", "seq"])
    text = _coalesce(row, ["content", "msgContent", "msg", "message", "text"]) or ""
    timestamp = _coalesce(row, ["msgTime", "time", "timestamp", "createTime", "created_at"])
    message_type = _coalesce(row, ["msgType", "msg_type", "message_type", "type"]) or "text"
    sender_str = str(sender or "")
    is_group = _coalesce(row, ["is_group", "isGroup", "group", "is_group_chat"])
    is_group_bool = _truthy(is_group) or _looks_like_group(chat_id, chat_name)
    is_received = _coalesce(row, ["is_received", "isReceived", "is_recv", "isRecv", "direction"])
    sender_is_owner = bool(owner_uin and sender_str == str(owner_uin))
    is_received_bool = not sender_is_owner if owner_uin else _received_bool(is_received)
    time_text = _normalize_time(timestamp)

    return {
        "chat": str(chat_name or chat_id or ""),
        "chat_name": str(chat_name or chat_id or ""),
        "chat_id": str(chat_id or ""),
        "sender": str(sender_name or sender or ""),
        "sender_id": sender_str,
        "sender_is_owner": sender_is_owner,
        "is_received": is_received_bool,
        "is_group": is_group_bool,
        "text": str(text),
        "message_type": str(message_type),
        "time": time_text,
        "time_ts": _to_epoch(timestamp),
        "message_id": str(message_id or ""),
    }


def normalize_messages(rows: List[Dict[str, Any]], *, owner_uin: Optional[str] = None) -> List[Dict[str, Any]]:
    return [normalize_message(row, owner_uin=owner_uin) for row in rows]


def _find_message_table(cursor: sqlite3.Cursor) -> str:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [str(row[0]) for row in cursor.fetchall()]
    for preferred in ("message", "messages", "msg", "Msg"):
        if preferred in tables:
            return preferred
    for table in tables:
        if "msg" in table.lower() or "message" in table.lower():
            return table
    raise ValueError("No QQ message table found")


def _find_nt_message_tables(cursor: sqlite3.Cursor) -> List[str]:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {str(row[0]) for row in cursor.fetchall()}
    preferred = []
    for table in ("c2c_msg_table", "group_msg_table", "guild_msg_table"):
        if table in tables:
            preferred.append(table)
    return preferred


def _read_nt_message_rows(
    cursor: sqlite3.Cursor,
    tables: List[str],
    *,
    limit: Optional[int] = None,
    keyword: Optional[str] = None,
) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = []
    for table in tables:
        columns = _table_columns(cursor, table)
        quoted_columns = ", ".join([f'"{column}"' for column in columns])
        sql = f'SELECT {quoted_columns} FROM "{table}"'
        where = []
        if "40011" in columns:
            where.append('"40011"=2')
        if "40012" in columns:
            where.append('"40012"=1')
        if where:
            sql += " WHERE " + " AND ".join(where)
        if "40050" in columns:
            sql += ' ORDER BY "40050" DESC'
        cursor.execute(sql)
        for row in cursor.fetchall():
            raw = dict(zip(columns, row))
            normalized = _normalize_nt_message_row(raw, table)
            if keyword and keyword not in (normalized.get("content") or ""):
                continue
            messages.append(normalized)

    messages.sort(key=lambda row: _to_epoch(row.get("msgTime")) or 0, reverse=True)
    if limit:
        return messages[:limit]
    return messages


def _normalize_nt_message_row(row: Dict[str, Any], table: str) -> Dict[str, Any]:
    is_group = table in {"group_msg_table", "guild_msg_table"}
    chat_id = _coalesce(row, ["40021", "40027", "40030"])
    sender_id = _coalesce(row, ["40033", "40020", "40006"])
    sender_name = _coalesce(row, ["40090", "40093", "40020", "40033"])
    is_self = _truthy(_coalesce(row, ["40040", "40105", "40005"]))
    text = extract_nt_plain_text(_coalesce(row, ["40800"]) or b"")
    timestamp = _coalesce(row, ["40050", "40058"])
    message_id = _coalesce(row, ["40003", "40001"])
    return {
        "msgId": str(message_id or ""),
        "peerUin": str(chat_id or ""),
        "chatName": str(chat_id or ""),
        "senderUin": str(sender_id or ""),
        "senderName": str(sender_name or sender_id or ""),
        "msgTime": timestamp,
        "content": text,
        "msgType": "text",
        "isGroup": 1 if is_group else 0,
        "is_received": not is_self,
        "raw_table": table,
    }


def extract_nt_plain_text(value: Any) -> str:
    """Extract plain text from QQ NT protobuf-ish message bytes.

    QQ NT stores message elements in column 40800. For text elements, current
    public parsers look for the byte tag sequence 0x82 0x16 and then a
    single-byte text length. This conservative extractor only returns those
    pure text fragments and ignores images/cards/files.
    """
    if value in (None, ""):
        return ""
    if isinstance(value, memoryview):
        data = value.tobytes()
    elif isinstance(value, bytes):
        data = value
    elif isinstance(value, bytearray):
        data = bytes(value)
    else:
        return str(value)

    chunks: List[bytes] = []
    i = 0
    while i < len(data) - 2:
        if data[i] == 0x82 and data[i + 1] == 0x16:
            length = data[i + 2]
            start = i + 3
            end = start + length
            if length > 0 and end <= len(data):
                chunks.append(data[start:end].replace(b"\x00", b"\n"))
                i = end
                continue
        i += 1
    text_parts = []
    for chunk in chunks:
        try:
            text_parts.append(chunk.decode("utf-8", errors="ignore"))
        except Exception:
            pass
    return "".join(text_parts).strip()


def _direct_db_files(db_dir: Path) -> List[Path]:
    if not db_dir.exists():
        return []
    return [
        path
        for path in sorted(db_dir.glob("*.db"))
        if path.is_file() and not path.name.endswith(("-wal", "-shm"))
    ]


def _read_entity_db(path: Path, role: str, result: Dict[str, Any], *, limit_per_table: Optional[int]) -> None:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        for table in [str(row[0]) for row in cursor.fetchall()]:
            if table == "sqlite_sequence":
                continue
            columns = _table_columns(cursor, table)
            count = _safe_count(cursor, table)
            selected_role = _entity_role_for_table(table, role)
            result["tables"].append(
                {
                    "role": selected_role,
                    "path": str(path),
                    "table": table,
                    "columns": columns,
                    "count": count,
                    "status": "readable",
                }
            )
            if selected_role not in {"contacts", "groups", "recent_contacts"}:
                continue
            quoted_columns = ", ".join([f'"{column}"' for column in columns])
            sql = f'SELECT {quoted_columns} FROM "{table}"'
            if limit_per_table:
                sql += " LIMIT ?"
                cursor.execute(sql, (limit_per_table,))
            else:
                cursor.execute(sql)
            for row in cursor.fetchall():
                raw = dict(row)
                entity = _normalize_entity(raw, selected_role, table)
                if entity["id"] or entity["name"]:
                    result[selected_role].append(entity)
    finally:
        conn.close()


def _safe_count(cursor: sqlite3.Cursor, table: str) -> Optional[int]:
    try:
        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        return int(cursor.fetchone()[0])
    except Exception:
        return None


def _entity_role_for_table(table: str, fallback: str) -> str:
    lower = table.lower()
    if "recent" in lower:
        return "recent_contacts"
    if "group" in lower:
        return "groups"
    if "buddy" in lower or "profile" in lower or "friend" in lower or "contact" in lower:
        return "contacts"
    return fallback if fallback in {"contacts", "groups", "recent_contacts"} else "other"


def _normalize_entity(row: Dict[str, Any], role: str, table: str) -> Dict[str, Any]:
    if role == "groups":
        entity_id = _coalesce_fuzzy(row, ["group", "code", "uin", "id", "40021", "40027", "40030"])
        name = _coalesce_fuzzy(row, ["group_name", "name", "remark", "nick", "display", "40090", "40093"])
        member_count = _coalesce_fuzzy(row, ["member", "count", "40083", "40084"])
        return {
            "type": "group",
            "id": _stringify_entity_value(entity_id),
            "name": _stringify_entity_value(name),
            "member_count": member_count,
            "source_table": table,
            "raw": row,
        }
    entity_id = _coalesce_fuzzy(row, ["uin", "uid", "user", "account", "id", "40020", "40033", "40006"])
    name = _coalesce_fuzzy(row, ["remark", "nick", "nickname", "name", "display", "alias", "40090", "40093"])
    return {
        "type": "recent_contact" if role == "recent_contacts" else "contact",
        "id": _stringify_entity_value(entity_id),
        "name": _stringify_entity_value(name),
        "source_table": table,
        "raw": row,
    }


def _coalesce_fuzzy(row: Dict[str, Any], preferred_tokens: List[str]) -> Any:
    lowered = {str(key).lower(): key for key in row.keys()}
    for token in preferred_tokens:
        token_lower = token.lower()
        if token_lower in lowered:
            value = row.get(lowered[token_lower])
            if value not in (None, ""):
                return value
    for token in preferred_tokens:
        token_lower = token.lower()
        for key in row.keys():
            if token_lower in str(key).lower():
                value = row.get(key)
                if value not in (None, ""):
                    return value
    return None


def _stringify_entity_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return str(value)


def _probe_nt_store(path: Path) -> Dict[str, Any]:
    role = NT_DB_ROLES.get(path.name, _infer_nt_role(path.name))
    wrapped = is_nt_wrapped_db(path)
    readable = _is_sqlite_readable(path)
    wal = Path(str(path) + "-wal")
    shm = Path(str(path) + "-shm")
    size = path.stat().st_size
    clean_size = max(size - NT_HEADER_BYTES, 0) if wrapped else size
    return {
        "name": path.name,
        "role": role,
        "path": str(path),
        "format": "qq_nt_wrapped_sqlcipher" if wrapped else ("sqlite" if readable else "unknown"),
        "size": size,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
        "has_wal": wal.exists(),
        "wal_size": wal.stat().st_size if wal.exists() else 0,
        "has_shm": shm.exists(),
        "shm_size": shm.stat().st_size if shm.exists() else 0,
        "clean_size": clean_size,
        "clean_pages": clean_size // NT_CIPHER_PAGE_SIZE if clean_size % NT_CIPHER_PAGE_SIZE == 0 else None,
        "readable": readable,
        "needs_decryption": wrapped and not readable,
    }


def _infer_nt_role(name: str) -> str:
    lower = name.lower()
    if "msg" in lower:
        return "messages"
    if "profile" in lower or "buddy" in lower:
        return "contacts"
    if "group" in lower:
        return "groups"
    if "media" in lower:
        return "media"
    if "file" in lower:
        return "files"
    return "other"


def _is_sqlite_readable(path: Path) -> bool:
    if not path.exists() or is_nt_wrapped_db(path):
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def _account_hash_from_nt_dir(db_dir: Path) -> Optional[str]:
    for part in reversed(db_dir.parts):
        if part.startswith("nt_qq_") and len(part) > len("nt_qq_"):
            return part[len("nt_qq_") :]
    return None


def _summarize_candidate_key_material(account_hash: str, wrapped_db: Path) -> Dict[str, Any]:
    """Summarize key material without exposing candidate passphrases."""
    try:
        head = wrapped_db.read_bytes()[:NT_HEADER_BYTES]
    except OSError:
        head = b""
    marker_at = head.find(NT_MARKER)
    printable_offsets = []
    if marker_at >= 0:
        start = marker_at + len(NT_MARKER)
        for offset in range(start, min(start + 128, len(head) - 8)):
            chunk = head[offset : offset + 8]
            if all(32 <= byte < 127 for byte in chunk):
                printable_offsets.append(offset)
    return {
        "account_hash_present": bool(account_hash),
        "nt_marker_offset": marker_at if marker_at >= 0 else None,
        "printable_rand_candidate_count": len(printable_offsets),
        "printable_rand_candidate_offsets": printable_offsets[:16],
        "note": "不输出候选 passphrase/key；真实解密需从 QQ 运行时捕获或由用户提供。",
    }


def _sqlcipher_export(clean_path: Path, out_path: Path, passphrase: str, sqlcipher_bin: str) -> Tuple[bool, str]:
    if out_path.exists():
        out_path.unlink()
    escaped_passphrase = passphrase.replace("'", "''")
    escaped_out = str(out_path).replace("'", "''")
    sql = "\n".join(
        [
            f"PRAGMA key = '{escaped_passphrase}';",
            "PRAGMA kdf_iter = 4000;",
            "PRAGMA cipher_page_size = 4096;",
            f"ATTACH DATABASE '{escaped_out}' AS plaintext KEY '';",
            "SELECT sqlcipher_export('plaintext');",
            "DETACH DATABASE plaintext;",
            ".exit",
            "",
        ]
    )
    proc = subprocess.run(
        [sqlcipher_bin, str(clean_path)],
        input=sql,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        error = (proc.stderr or proc.stdout or "SQLCipher failed").strip()
        return False, _redact_secret(error, passphrase)
    if not out_path.exists():
        output = (proc.stderr or proc.stdout or "SQLCipher did not create output").strip()
        return False, _redact_secret(output, passphrase)
    return True, "decrypted"


def _redact_secret(text: str, secret: str) -> str:
    if secret:
        text = text.replace(secret, "[REDACTED]")
    return text


def _table_columns(cursor: sqlite3.Cursor, table: str) -> List[str]:
    cursor.execute(f"PRAGMA table_info({table})")
    return [str(row[1]) for row in cursor.fetchall()]


def _first_present(columns: List[str], names: List[str]) -> Optional[str]:
    column_set = set(columns)
    for name in names:
        if name in column_set:
            return name
    return None


def _coalesce(row: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _normalize_time(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        from datetime import datetime, timezone

        return datetime.fromtimestamp(timestamp, timezone.utc).astimezone().isoformat(timespec="seconds")
    text = str(value)
    if text.isdigit():
        return _normalize_time(int(text))
    return text


def _to_epoch(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return timestamp
    text = str(value).strip()
    if text.isdigit():
        return _to_epoch(int(text))
    from datetime import datetime

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            pass
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).lower() in {"1", "true", "yes", "group", "群", "群聊"}


def _received_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return True
    text = str(value).lower()
    if text in {"sent", "send", "out", "outgoing", "0", "false"}:
        return False
    if text in {"recv", "received", "in", "incoming", "1", "true"}:
        return True
    return True


def _looks_like_group(chat_id: Any, chat_name: Any) -> bool:
    text = f"{chat_id or ''} {chat_name or ''}".lower()
    return "group" in text or "群" in text or text.endswith("@chatroom")
