#!/usr/bin/env python3
"""QQ collector normalization and event tests."""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from qq_query import cmd_collect
from qq.collect import collect_records, collect_records_to_messages
from qq.events import messages_to_events, write_events_jsonl
from qq.keyprobe import assess_version_compatibility, build_flash_guide
from qq.parser import (
    NT_HEADER,
    NT_HEADER_BYTES,
    NT_MARKER,
    extract_nt_plain_text,
    normalize_message,
    normalize_messages,
    prepare_nt_clean_copies,
    probe_db_dir,
    read_message_rows,
    read_nt_entities,
)


def test_normalize_message():
    msg = normalize_message(
        {
            "msgId": "m-001",
            "peerUin": "group-1",
            "senderUin": "10001",
            "msgTime": 1_720_000_000,
            "content": "这家公司先放观察池。",
            "msgType": "text",
        },
        owner_uin="10001",
    )

    assert msg["chat"] == "group-1"
    assert msg["sender"] == "10001"
    assert msg["sender_is_owner"] is True
    assert msg["message_id"] == "m-001"
    assert msg["text"] == "这家公司先放观察池。"


def test_sqlite_read_and_event_export():
    root = Path("/tmp/collectorx_qq_test")
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    db_path = root / "Msg_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE message (msgId TEXT, peerUin TEXT, chatName TEXT, senderUin TEXT, senderName TEXT, msgTime INTEGER, content TEXT, msgType TEXT, isGroup INTEGER)"
    )
    conn.execute(
        "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("m-001", "friend-1", "张三", "10001", "我", 1_720_000_000, "这家公司先放观察池。", "text", 0),
    )
    conn.execute(
        "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("m-002", "group-1", "投资讨论群", "10002", "李四", 1_720_000_060, "等半年报出来再看。", "text", 1),
    )
    conn.execute(
        "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("m-003", "group-1", "投资讨论群", "10001", "我", 1_720_000_120, "我先跟踪。", "text", 1),
    )
    conn.execute(
        "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("m-004", "group-2", "潜水群", "10002", "王五", 1_720_000_180, "今日资讯刷屏。", "text", 1),
    )
    conn.commit()
    conn.close()

    rows = read_message_rows(db_path)
    messages = normalize_messages(rows, owner_uin="10001")
    assert len(messages) == 4
    assert messages[0]["message_id"] == "m-004"

    events = messages_to_events(
        messages,
        raw_file=str(db_path),
        collected_at="2026-07-07T16:30:00+08:00",
    )
    assert len(events) == 4
    assert events[0]["schema"] == "collectorx.event.v1"
    assert events[0]["collector"] == "qq"
    assert events[0]["kind"] == "message"
    assert events[0]["privacy"]["local_only"] is True
    assert events[0]["data"]["chat"] == "潜水群"

    event_path = root / "events.jsonl"
    write_events_jsonl(str(event_path), events)
    lines = event_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4
    assert json.loads(lines[0])["collector"] == "qq"

    probe = probe_db_dir(root)
    assert probe["status"] == "ok"
    assert probe["db_file_count"] == 1
    assert probe["message_table"] == "message"
    assert probe["message_count"] == 4
    assert "content" in probe["message_columns"]

    collect = collect_records(messages, active_group_days=30)
    chats = [record["data"]["chat"] for record in collect]
    assert chats == ["张三", "投资讨论群", "投资讨论群"]
    assert "潜水群" not in chats
    assert collect[0]["source"].startswith("跟张三")
    assert "QQ群「投资讨论群」" in collect[1]["source"]

    collect_messages = collect_records_to_messages(collect)
    collect_events = messages_to_events(collect_messages)
    assert len(collect_events) == 3
    assert collect_events[0]["kind"] == "message"


def test_collect_standard_package_output():
    from tools.validate_collector_package import validate_package

    root = Path("/tmp/collectorx_qq_collect_package")
    shutil.rmtree(root, ignore_errors=True)
    db_dir = root / "db"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "Msg_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE message (msgId TEXT, peerUin TEXT, chatName TEXT, senderUin TEXT, senderName TEXT, msgTime INTEGER, content TEXT, msgType TEXT, isGroup INTEGER)"
    )
    conn.execute(
        "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("m-001", "friend-1", "张三", "10001", "我", 1_720_000_000, "这家公司先放观察池。", "text", 0),
    )
    conn.execute(
        "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("m-002", "group-1", "投资讨论群", "10002", "李四", 1_720_000_060, "等半年报出来再看。", "text", 1),
    )
    conn.execute(
        "INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("m-003", "group-1", "投资讨论群", "10001", "我", 1_720_000_120, "我先跟踪。", "text", 1),
    )
    conn.commit()
    conn.close()

    out_dir = root / "package"
    cmd_collect(
        db_dir,
        out_dir=str(out_dir),
        owner_uin="10001",
        collected_at="2026-07-08T10:00:00+08:00",
    )

    collect_payload = json.loads((out_dir / "qq.collect.json").read_text(encoding="utf-8"))
    assert len(collect_payload) == 3

    event_lines = (out_dir / "lake" / "qq" / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(event_lines) == 3
    first_event = json.loads(event_lines[0])
    assert first_event["collector"] == "qq"
    assert first_event["kind"] == "message"
    assert first_event["privacy"]["local_only"] is True

    manifest_text = (out_dir / "manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert manifest["schema"] == "collectorx.qq.collect_manifest.v1"
    assert manifest["collector"] == "qq"
    assert manifest["record_count"] == 3
    assert manifest["message_event_count"] == 3
    assert manifest["event_count"] == 3
    assert manifest["collection_readiness"]["status"] == "events_collected"
    assert manifest["evidence_policy"]["collector_writes_wiki_directly"] is False
    assert manifest["filter_policy"]["owner_uin_provided"] is True
    assert "10001" not in manifest_text
    assert "investor communication lens" in (out_dir / "SUMMARY.md").read_text(encoding="utf-8")

    summary, errors = validate_package(out_dir, collector="qq")
    assert summary["valid"] is True
    assert errors == []


def test_collect_gap_package_when_database_is_missing():
    from tools.validate_collector_package import validate_package

    root = Path("/tmp/collectorx_qq_collect_gap")
    shutil.rmtree(root, ignore_errors=True)
    db_dir = root / "empty"
    db_dir.mkdir(parents=True)
    out_dir = root / "package"

    cmd_collect(
        db_dir,
        out_dir=str(out_dir),
        collected_at="2026-07-08T10:00:00+08:00",
    )

    events = [
        json.loads(line)
        for line in (out_dir / "lake" / "qq" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(events) == 1
    assert events[0]["kind"] == "gap"
    assert events[0]["data"]["reason"] == "no_readable_qq_message_database"

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["record_count"] == 0
    assert manifest["message_event_count"] == 0
    assert manifest["event_count"] == 1
    assert manifest["collection_readiness"]["status"] == "needs_readable_qq_db"
    assert manifest["collection_readiness"]["can_enter_investor_wiki_directly"] is False

    summary, errors = validate_package(out_dir, collector="qq")
    assert summary["valid"] is True
    assert errors == []


def test_nt_wrapped_probe_and_prepare():
    root = Path("/tmp/collectorx_qq_nt_probe/nt_qq_abcdef0123456789/nt_db")
    shutil.rmtree(root.parents[1], ignore_errors=True)
    root.mkdir(parents=True)

    for name in ("nt_msg.db", "profile_info.db", "group_info.db", "recent_contact.db"):
        head = bytearray(b"\x00" * NT_HEADER_BYTES)
        head[: len(NT_HEADER)] = NT_HEADER
        head[32 : 32 + len(NT_MARKER)] = NT_MARKER
        head[47:55] = b"12345678"
        payload = bytes([len(name) % 251]) * 4096
        (root / name).write_bytes(bytes(head) + payload)

    probe = probe_db_dir(root)
    assert probe["status"] == "needs_decryption"
    assert probe["store_format"] == "qq_nt_sqlcipher_wrapped"
    assert probe["raw_capabilities"]["messages"] is True
    assert probe["raw_capabilities"]["contacts"] is True
    assert probe["raw_capabilities"]["groups"] is True
    assert probe["read_capabilities"]["messages"] is False
    assert probe["requires_passphrase"] is True
    assert probe["candidate_key_material"]["account_hash_present"] is True

    out = Path("/tmp/collectorx_qq_nt_clean")
    shutil.rmtree(out, ignore_errors=True)
    manifest = prepare_nt_clean_copies(root, out, include_roles=["messages"])
    assert len(manifest["files"]) == 1
    clean_path = Path(manifest["files"][0]["output"])
    assert clean_path.name == "nt_msg.clean.db"
    assert clean_path.stat().st_size == 4096


def test_keyprobe_flash_guide_for_sip_enabled():
    guide = build_flash_guide(
        {"enabled": True, "status": "enabled"},
        {"status": "attach_denied"},
        {"qq_key_path_ready": True},
    )
    assert guide["show"] is True
    assert guide["code"] == "SIP_ENABLED_BLOCKS_KEY_CAPTURE"
    assert guide["can_disable_without_reboot"] is False
    assert any("csrutil disable" in step for step in guide["minimal_steps"])


def test_keyprobe_version_compatibility_flags_wechat_41():
    compatibility = assess_version_compatibility(
        {
            "qq": {
                "installed": True,
                "version": "6.9.97",
            },
            "wechat": {
                "installed": True,
                "primary": {
                    "installed": True,
                    "version": "4.1.10",
                },
            },
        },
        wrapper_exists=True,
        offset_found=True,
    )
    assert compatibility["qq_key_path_ready"] is True
    assert any(
        item["app"] == "WeChat" and item["level"] == "warn" and "4.1+" in item["message"]
        for item in compatibility["items"]
    )


def test_keyprobe_version_compatibility_blocks_missing_qq_offset():
    compatibility = assess_version_compatibility(
        {
            "qq": {
                "installed": True,
                "version": "6.9.97",
            },
            "wechat": {
                "installed": False,
                "primary": None,
            },
        },
        wrapper_exists=True,
        offset_found=False,
    )
    assert compatibility["qq_key_path_ready"] is False
    assert any(
        item["app"] == "QQ" and item["level"] == "block" and "nt_sqlite3_key_v2" in item["message"]
        for item in compatibility["items"]
    )


def test_read_decrypted_nt_message_tables():
    root = Path("/tmp/collectorx_qq_nt_plain")
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    db_path = root / "nt_msg.db"
    conn = sqlite3.connect(str(db_path))
    for table in ("group_msg_table", "c2c_msg_table"):
        conn.execute(
            f'''CREATE TABLE {table} (
                "40001" INTEGER,
                "40003" INTEGER,
                "40011" INTEGER,
                "40012" INTEGER,
                "40020" TEXT,
                "40021" TEXT,
                "40027" INTEGER,
                "40033" INTEGER,
                "40040" INTEGER,
                "40050" INTEGER,
                "40090" TEXT,
                "40093" TEXT,
                "40800" BLOB
            )'''
        )

    def nt_text(text: str) -> bytes:
        body = text.encode("utf-8")
        return b"\x08\x01\x82\x16" + bytes([len(body)]) + body

    conn.execute(
        'INSERT INTO group_msg_table VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (1, 1001, 2, 1, "uid-a", "group-1", 0, 10002, 0, 1_720_000_060, "李四", "", nt_text("等半年报出来再看。")),
    )
    conn.execute(
        'INSERT INTO group_msg_table VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (2, 1002, 2, 1, "uid-me", "group-1", 0, 10001, 1, 1_720_000_120, "我", "", nt_text("我先跟踪。")),
    )
    conn.execute(
        'INSERT INTO c2c_msg_table VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (3, 1003, 2, 1, "friend-1", "friend-1", 0, 10003, 0, 1_720_000_180, "张三", "", nt_text("周末聊下估值。")),
    )
    conn.commit()
    conn.close()

    assert extract_nt_plain_text(nt_text("测试文本")) == "测试文本"
    rows = read_message_rows(db_path)
    messages = normalize_messages(rows, owner_uin="10001")
    assert len(messages) == 3
    assert messages[0]["chat"] == "friend-1"
    assert messages[0]["text"] == "周末聊下估值。"
    assert messages[1]["is_group"] is True
    assert messages[1]["sender_is_owner"] is True

    collect = collect_records(messages, active_group_days=30)
    assert [record["data"]["chat"] for record in collect] == ["group-1", "group-1", "friend-1"]


def test_read_decrypted_nt_entities():
    root = Path("/tmp/collectorx_qq_nt_entities")
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)

    profile_db = root / "profile_info.db"
    conn = sqlite3.connect(str(profile_db))
    conn.execute("CREATE TABLE buddy_list (uin TEXT, nickname TEXT, remark TEXT)")
    conn.execute("INSERT INTO buddy_list VALUES (?, ?, ?)", ("10002", "李四", "研究员"))
    conn.commit()
    conn.close()

    group_db = root / "group_info.db"
    conn = sqlite3.connect(str(group_db))
    conn.execute("CREATE TABLE group_info (group_code TEXT, group_name TEXT, member_count INTEGER)")
    conn.execute("INSERT INTO group_info VALUES (?, ?, ?)", ("group-1", "投资讨论群", 12))
    conn.commit()
    conn.close()

    recent_db = root / "recent_contact.db"
    conn = sqlite3.connect(str(recent_db))
    conn.execute("CREATE TABLE recent_contact (uid TEXT, nick TEXT)")
    conn.execute("INSERT INTO recent_contact VALUES (?, ?)", ("10003", "张三"))
    conn.commit()
    conn.close()

    entities = read_nt_entities(root)
    assert entities["status"] == "ok"
    assert entities["contacts"][0]["id"] == "10002"
    assert entities["contacts"][0]["name"] == "研究员"
    assert entities["groups"][0]["id"] == "group-1"
    assert entities["groups"][0]["name"] == "投资讨论群"
    assert entities["recent_contacts"][0]["id"] == "10003"


if __name__ == "__main__":
    test_normalize_message()
    test_sqlite_read_and_event_export()
    test_collect_standard_package_output()
    test_collect_gap_package_when_database_is_missing()
    test_nt_wrapped_probe_and_prepare()
    test_keyprobe_flash_guide_for_sip_enabled()
    test_keyprobe_version_compatibility_flags_wechat_41()
    test_keyprobe_version_compatibility_blocks_missing_qq_offset()
    test_read_decrypted_nt_message_tables()
    test_read_decrypted_nt_entities()
    print("All QQ collector tests passed!")
