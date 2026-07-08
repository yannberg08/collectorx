#!/usr/bin/env python3
"""Email collector event tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from email.header import Header
from email.message import EmailMessage
from io import StringIO


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from email_collector.events import emails_to_events, write_events_jsonl
from email_api import _account_id, _accounts_from_state, _collect_account_emails, infer_provider


def test_email_event_without_full_body():
    emails = [
        {
            "id": "42",
            "message_id": "<sample@example.com>",
            "mailbox": "owner@example.com",
            "folder": "INBOX",
            "from": "Analyst <analyst@example.com>",
            "to": "Owner <owner@example.com>",
            "cc": "",
            "subject": "调研纪要",
            "date": "Tue, 07 Jul 2026 10:00:00 +0800",
            "body": "这是一封很长的邮件正文，用于测试默认事件不会携带完整正文。",
        }
    ]

    events = emails_to_events(
        emails,
        account="owner@example.com",
        folder="INBOX",
        collected_at="2026-07-07T16:30:00+08:00",
    )

    assert len(events) == 1
    event = events[0]
    assert event["schema"] == "collectorx.event.v1"
    assert event["collector"] == "email"
    assert event["kind"] == "email"
    assert event["privacy"]["local_only"] is True
    assert event["data"]["subject"] == "调研纪要"
    assert "body_preview" in event["data"]
    assert "body" not in event["data"]


def test_email_event_jsonl_writer():
    events = emails_to_events(
        [
            {
                "id": "43",
                "message_id": "<sample-2@example.com>",
                "from": "A <a@example.com>",
                "to": "B <b@example.com>",
                "subject": "项目更新",
                "date": "Tue, 07 Jul 2026 11:00:00 +0800",
                "body": "正文",
            }
        ],
        account="b@example.com",
        folder="INBOX",
        include_body=True,
        collected_at="2026-07-07T16:30:00+08:00",
    )
    assert "body" in events[0]["data"]

    path = Path("/tmp/collectorx_email_events.jsonl")
    write_events_jsonl(str(path), events)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["collector"] == "email"


def test_email_event_sanitizes_attachment_and_raw_ref_secrets():
    events = emails_to_events(
        [
            {
                "id": "44",
                "message_id": "<sample-3@example.com>",
                "from": "Research <research@example.com>",
                "to": "Owner <owner@example.com>",
                "subject": "请查收附件",
                "date": "Tue, 07 Jul 2026 12:00:00 +0800",
                "body": "正文",
                "attachments": [{"filename": "report.pdf", "content_type": "application/pdf", "token": "must-not-leak"}],
                "raw_ref": {"path": "mail.json", "token": "must-not-leak", "nested": {"cookie": "must-not-leak"}},
            }
        ],
        collected_at="2026-07-07T16:30:00+08:00",
    )
    serialized = json.dumps(events, ensure_ascii=False)
    assert "must-not-leak" not in serialized
    assert events[0]["data"]["attachment_refs"] == [{"filename": "report.pdf", "content_type": "application/pdf"}]
    assert events[0]["data"]["attachment_count"] == 1


def test_provider_inference_and_multi_account_state():
    gmail = infer_provider("owner@gmail.com")
    assert gmail["provider"] == "gmail"
    assert gmail["host"] == "imap.gmail.com"

    qq = infer_provider("owner@qq.com")
    assert qq["provider"] == "qq"
    assert qq["host"] == "imap.qq.com"

    custom = infer_provider("owner@example.local")
    assert custom["provider"] == "custom"
    assert custom["matched"] is False

    assert _account_id("Owner.Name+invest@gmail.com") == "owner_name_invest_gmail_com"

    old_state = {
        "account": {
            "host": "imap.gmail.com",
            "email": "owner@gmail.com",
            "password_env": "MAIL_PASSWORD",
        }
    }
    accounts = _accounts_from_state(old_state)
    assert len(accounts) == 1
    assert accounts[0]["id"] == "owner_gmail_com"
    assert accounts[0]["folders"] == ["INBOX"]


class FakeIMAP:
    mailboxes = {}

    def __init__(self, host):
        self.host = host
        self.email = None
        self.folder = None

    def login(self, email_addr, password):
        self.email = email_addr
        if password != "ok":
            raise RuntimeError("bad password")

    def select(self, folder):
        self.folder = folder
        return "OK", []

    def search(self, charset, criteria):
        ids = list(self.mailboxes.get((self.email, self.folder), {}))
        return "OK", [b" ".join(str(item).encode("ascii") for item in ids)]

    def fetch(self, msg_id, mode):
        message = self.mailboxes[(self.email, self.folder)][int(msg_id)]
        return "OK", [(b"RFC822", message)]

    def logout(self):
        return "BYE", []


def _mail_bytes(subject, sender, recipient, body, attachment_name=None):
    msg = EmailMessage()
    msg["Message-ID"] = "<sample@example.com>"
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["Date"] = "Tue, 07 Jul 2026 10:00:00 +0800"
    msg.set_content(body)
    if attachment_name:
        msg.add_attachment(b"attachment-bytes", maintype="application", subtype="pdf", filename=attachment_name)
    return msg.as_bytes()


def test_fake_imap_multi_folder_collection(monkeypatch=None):
    import email_api

    FakeIMAP.mailboxes = {
        ("owner@gmail.com", "INBOX"): {
            1: _mail_bytes("调研纪要", "Analyst <a@example.com>", "Owner <owner@gmail.com>", "正文A", "morning-note.pdf")
        },
        ("owner@gmail.com", "Sent"): {
            2: _mail_bytes("回复纪要", "Owner <owner@gmail.com>", "Analyst <a@example.com>", "正文B")
        },
    }
    original = email_api.imaplib.IMAP4_SSL
    email_api.imaplib.IMAP4_SSL = FakeIMAP
    try:
        emails = _collect_account_emails(
            {
                "email": "owner@gmail.com",
                "host": "imap.gmail.com",
                "password": "ok",
            },
            days=30,
            folders=["INBOX", "Sent"],
        )
    finally:
        email_api.imaplib.IMAP4_SSL = original

    assert len(emails) == 2
    folders = {item["folder"] for item in emails}
    assert folders == {"INBOX", "Sent"}
    assert {item["subject"] for item in emails} == {"调研纪要", "回复纪要"}
    assert any(ref["filename"] == "morning-note.pdf" for item in emails for ref in item.get("attachment_refs", []))


def test_imap_collect_standard_package():
    import email_api

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "out"
        state_path = root / "email.json"
        FakeIMAP.mailboxes = {
            ("owner@gmail.com", "INBOX"): {
                1: _mail_bytes("晨会纪要", "Analyst <a@example.com>", "Owner <owner@gmail.com>", "正文A")
            },
            ("owner@gmail.com", "Sent"): {
                2: _mail_bytes("调研回复", "Owner <owner@gmail.com>", "Analyst <a@example.com>", "正文B", "roadshow.pdf")
            },
        }

        original_imap = email_api.imaplib.IMAP4_SSL
        original_token_file = email_api.TOKEN_FILE
        email_api.imaplib.IMAP4_SSL = FakeIMAP
        email_api.TOKEN_FILE = state_path
        try:
            email_api._save_accounts(
                [
                    {
                        "id": "owner_gmail_com",
                        "provider": "gmail",
                        "host": "imap.gmail.com",
                        "email": "owner@gmail.com",
                        "password": "ok",
                        "folders": ["INBOX", "Sent"],
                        "days": 30,
                        "enabled": True,
                    }
                ]
            )
            with redirect_stdout(StringIO()):
                email_api.cmd_collect(
                    days=None,
                    folder=None,
                    fmt="json",
                    limit=None,
                    out_dir=str(out),
                    collected_at="2026-07-08T13:00:00+08:00",
                    account_id="all",
                )
        finally:
            email_api.imaplib.IMAP4_SSL = original_imap
            email_api.TOKEN_FILE = original_token_file

        events = [
            json.loads(line)
            for line in (out / "lake" / "email" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 2
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["schema"] == "collectorx.email_collect.manifest.v1"
        assert manifest["collection_readiness"]["can_enter_finclaw"] is True
        assert manifest["collection_readiness"]["source_collection_scope"] == "authorized_imap"
        assert manifest["collection_audit"]["source_type"] == "imap"
        assert manifest["collection_audit"]["account_status_counts"] == {"collected": 1}
        assert manifest["collection_audit"]["folder_status_counts"] == {"collected": 2}
        assert manifest["field_coverage"]["fields"]["from"]["present"] == 2
        assert manifest["evidence_policy"]["investor_wiki_requires_lens"] == "email-research"
        proof = manifest["mailbox_boundary_proof"]
        assert proof["proof_level"] == "authorized_imap_folder_window"
        assert proof["source_type"] == "imap"
        assert proof["email_event_count"] == 2
        assert proof["mailboxes"] == ["owner@gmail.com"]
        assert proof["folders"] == ["INBOX", "Sent"]
        assert proof["complete_mailbox_claimed"] is False
        assert proof["body_capture"]["full_body_included"] is False
        assert proof["attachment_capture"]["attachment_refs_included"] is True
        assert proof["attachment_capture"]["attachment_bodies_included"] is False
        assert proof["imap_boundary"]["requested_folders"] == ["INBOX", "Sent"]
        assert proof["imap_boundary"]["matched_message_count"] == 2
        assert proof["imap_boundary"]["password_material_in_output"] is False


def test_imap_collect_gap_package_without_registered_account():
    import email_api

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "out"
        original_token_file = email_api.TOKEN_FILE
        email_api.TOKEN_FILE = root / "missing-email-state.json"
        try:
            with redirect_stdout(StringIO()):
                email_api.cmd_collect(
                    days=30,
                    folder=None,
                    fmt="json",
                    limit=None,
                    out_dir=str(out),
                    collected_at="2026-07-08T13:10:00+08:00",
                    account_id="all",
                )
        finally:
            email_api.TOKEN_FILE = original_token_file

        events = [
            json.loads(line)
            for line in (out / "lake" / "email" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert events[0]["data"]["gap"] == "email_imap_account_missing"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["status"] == "needs_email_registered_account"
        assert manifest["collection_audit"]["status"] == "no_registered_account"
        proof = manifest["mailbox_boundary_proof"]
        assert proof["proof_level"] == "no_authorized_mailbox"
        assert proof["can_enter_finclaw"] is False
        assert proof["email_event_count"] == 0
        assert proof["imap_boundary"]["selected_account_count"] == 0


def test_local_email_import_package():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        eml_path = root / "broker-research.eml"
        json_path = root / "mail-export.json"
        csv_path = root / "mail-export.csv"
        unsupported_path = root / "notes.txt"
        out = root / "out"

        msg = EmailMessage()
        msg["Message-ID"] = "<research@example.com>"
        msg["From"] = "Broker Research <research@broker.example>"
        msg["To"] = "Owner <owner@example.com>"
        msg["Subject"] = str(Header("晨会纪要：新能源与半导体", "utf-8"))
        msg["Date"] = "Wed, 08 Jul 2026 08:30:00 +0800"
        msg.set_content("今日晨会关注新能源、半导体和估值变化。")
        msg.add_attachment(b"pdf-bytes", maintype="application", subtype="pdf", filename="morning-note.pdf")
        eml_path.write_bytes(msg.as_bytes())

        json_path.write_text(
            json.dumps(
                {
                    "emails": [
                        {
                            "from": "IR <ir@company.example>",
                            "to": "Owner <owner@example.com>",
                            "subject": "调研邀请",
                            "date": "2026-07-08T10:00:00+08:00",
                            "body": "邀请参加业绩说明会。",
                            "attachments": [{"filename": "roadshow.ics", "token": "must-not-leak"}],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        csv_path.write_text(
            "from,to,subject,date,body,attachments\n"
            "analyst@example.com,owner@example.com,行业深度,2026-07-08T11:00:00+08:00,见附件,industry.pdf\n",
            encoding="utf-8",
        )
        unsupported_path.write_text("not an email export", encoding="utf-8")

        script = Path(__file__).resolve().parents[1] / "scripts" / "email_api.py"
        subprocess.run(
            [
                sys.executable,
                str(script),
                "import",
                "--input",
                str(root),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T12:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [
            json.loads(line)
            for line in (out / "lake" / "email" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 3
        assert {event["collector"] for event in events} == {"email"}
        assert {event["kind"] for event in events} == {"email"}
        assert all("body_preview" in event["data"] for event in events)
        assert all("body" not in event["data"] for event in events)
        serialized = json.dumps(events, ensure_ascii=False)
        assert "must-not-leak" not in serialized
        assert "morning-note.pdf" in serialized
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["can_enter_finclaw"] is True
        assert manifest["collection_readiness"]["full_body_included"] is False
        assert manifest["collection_audit"]["source_type"] == "authorized_email_export"
        assert manifest["collection_audit"]["input_count"] == 1
        assert manifest["collection_audit"]["resolved_input_file_count"] == 3
        assert manifest["collection_audit"]["imported_email_count"] == 3
        assert manifest["collection_audit"]["parsed_record_count"] == 3
        assert manifest["collection_audit"]["skipped_file_count"] == 1
        assert manifest["collection_audit"]["skipped_reason_counts"] == {"unsupported_extension": 1}
        assert manifest["collection_audit"]["skipped_extension_counts"] == {".txt": 1}
        assert manifest["collection_audit"]["extension_counts"] == {
            ".csv": 1,
            ".eml": 1,
            ".json": 1,
            ".txt": 1,
        }
        assert len(manifest["collection_audit"]["path_results"]) == 4
        proof = manifest["mailbox_boundary_proof"]
        assert proof["proof_level"] == "authorized_local_export_boundary"
        assert proof["source_type"] == "authorized_email_export"
        assert proof["email_event_count"] == 3
        assert proof["folders"] == ["local-export"]
        assert proof["complete_account_history_claimed"] is False
        assert proof["body_capture"]["full_body_included"] is False
        assert proof["attachment_capture"]["attachment_bodies_included"] is False
        assert proof["local_export_boundary"]["resolved_input_file_count"] == 3
        assert proof["local_export_boundary"]["skipped_reason_counts"] == {"unsupported_extension": 1}


def test_local_email_import_apple_mail_emlx_and_maildir():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        apple_dir = root / "Apple Mail"
        maildir_cur = root / "Maildir" / "cur"
        out = root / "out"
        apple_dir.mkdir()
        maildir_cur.mkdir(parents=True)

        apple_msg = EmailMessage()
        apple_msg["Message-ID"] = "<apple-mail-research@example.com>"
        apple_msg["From"] = "Broker Research <research@broker.example>"
        apple_msg["To"] = "Owner <owner@example.com>"
        apple_msg["Subject"] = str(Header("Apple Mail 晨会纪要", "utf-8"))
        apple_msg["Date"] = "Wed, 08 Jul 2026 07:30:00 +0800"
        apple_msg.set_content("Apple Mail 本地导出的晨会纪要。")
        apple_raw = apple_msg.as_bytes()
        (apple_dir / "12345.emlx").write_bytes(
            str(len(apple_raw)).encode("ascii")
            + b"\n"
            + apple_raw
            + b"\n<?xml version=\"1.0\"?><plist></plist>"
        )

        maildir_msg = EmailMessage()
        maildir_msg["Message-ID"] = "<maildir-roadshow@example.com>"
        maildir_msg["From"] = "IR <ir@company.example>"
        maildir_msg["To"] = "Owner <owner@example.com>"
        maildir_msg["Subject"] = str(Header("Maildir 调研邀请", "utf-8"))
        maildir_msg["Date"] = "Wed, 08 Jul 2026 10:00:00 +0800"
        maildir_msg.set_content("邀请参加线上调研。")
        (maildir_cur / "1720000000.M123P456Q789.host:2,S").write_bytes(maildir_msg.as_bytes())
        (root / "README").write_text("not an email export", encoding="utf-8")

        script = Path(__file__).resolve().parents[1] / "scripts" / "email_api.py"
        subprocess.run(
            [
                sys.executable,
                str(script),
                "import",
                "--input",
                str(root),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T12:15:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [
            json.loads(line)
            for line in (out / "lake" / "email" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 2
        by_subject = {event["data"]["subject"]: event for event in events}
        assert "Apple Mail 晨会纪要" in by_subject
        assert "Maildir 调研邀请" in by_subject
        assert by_subject["Apple Mail 晨会纪要"]["raw_ref"]["format"] == "emlx"
        assert by_subject["Maildir 调研邀请"]["raw_ref"]["format"] == "maildir"
        assert all("body_preview" in event["data"] for event in events)
        assert all("body" not in event["data"] for event in events)

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["collection_audit"]
        assert audit["resolved_input_file_count"] == 2
        assert audit["imported_email_count"] == 2
        assert audit["parsed_record_count"] == 2
        assert audit["skipped_file_count"] == 1
        assert audit["skipped_reason_counts"] == {"unsupported_extension": 1}
        assert audit["skipped_extension_counts"] == {"<none>": 1}
        assert audit["extension_counts"] == {".emlx": 1, "<maildir>": 1, "<none>": 1}
        assert audit["apple_mail_emlx_file_count"] == 1
        assert audit["maildir_message_file_count"] == 1
        parser_counts = {result.get("parser") for result in audit["path_results"] if result["status"] == "parsed"}
        assert parser_counts == {"emlx", "maildir"}
        proof = manifest["mailbox_boundary_proof"]
        assert proof["local_export_boundary"]["apple_mail_emlx_file_count"] == 1
        assert proof["local_export_boundary"]["maildir_message_file_count"] == 1


def test_local_email_scan_package_masks_source_paths():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        local_root = root / "Library" / "Mail" / "private.path.account@example.net" / "13800138000"
        apple_dir = local_root / "V10" / "A1"
        maildir_new = local_root / "Maildir" / "new"
        apple_dir.mkdir(parents=True)
        maildir_new.mkdir(parents=True)
        out = root / "out"
        probe = root / "probe.json"

        apple_msg = EmailMessage()
        apple_msg["Message-ID"] = "<local-scan-apple@example.com>"
        apple_msg["From"] = "Broker Research <research@broker.example>"
        apple_msg["To"] = "Owner <owner@example.com>"
        apple_msg["Subject"] = str(Header("本机 Apple Mail 晨会纪要", "utf-8"))
        apple_msg["Date"] = "Wed, 08 Jul 2026 07:30:00 +0800"
        apple_msg.set_content("本机 Apple Mail 晨会纪要。")
        apple_raw = apple_msg.as_bytes()
        (apple_dir / "123456789.emlx").write_bytes(
            str(len(apple_raw)).encode("ascii")
            + b"\n"
            + apple_raw
            + b"\n<?xml version=\"1.0\"?><plist></plist>"
        )

        maildir_msg = EmailMessage()
        maildir_msg["Message-ID"] = "<local-scan-maildir@example.com>"
        maildir_msg["From"] = "IR <ir@company.example>"
        maildir_msg["To"] = "Owner <owner@example.com>"
        maildir_msg["Subject"] = str(Header("本机 Maildir 路演邀请", "utf-8"))
        maildir_msg["Date"] = "Wed, 08 Jul 2026 10:00:00 +0800"
        maildir_msg.set_content("邀请参加线上调研。")
        (maildir_new / "1720000000.M123P456Q789.host:2,S").write_bytes(maildir_msg.as_bytes())
        (local_root / "not-mail.txt").write_text("not an email export", encoding="utf-8")

        script = Path(__file__).resolve().parents[1] / "scripts" / "email_api.py"
        subprocess.run(
            [
                sys.executable,
                str(script),
                "import",
                "--local-scan",
                "--platform",
                "mac",
                "--container-root",
                str(local_root),
                "--probe-export",
                str(probe),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T13:00:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        events = [
            json.loads(line)
            for line in (out / "lake" / "email" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 2
        assert {event["source"] for event in events} == {"授权本机邮箱扫描"}
        assert all(event["raw_ref"]["local_scan"] is True for event in events)
        assert all(event["raw_ref"]["source_platform"] == "mac" for event in events)
        assert {event["raw_ref"]["format"] for event in events} == {"emlx", "maildir"}
        serialized_events = json.dumps(events, ensure_ascii=False)
        assert "13800138000" not in serialized_events
        assert "private.path.account@example.net" not in serialized_events

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_readiness"]["source_collection_scope"] == "partial_authorized_local_scan_or_input"
        audit = manifest["collection_audit"]
        assert audit["source_type"] == "authorized_email_export_or_local_scan"
        assert audit["input_count"] == 0
        assert audit["resolved_input_file_count"] == 2
        assert audit["imported_email_count"] == 2
        assert audit["local_scan_requested"] is True
        assert audit["local_scan_platform"]["resolved"] == "mac"
        assert audit["local_scan_candidate_file_count"] == 2
        assert audit["local_scan_imported_email_count"] == 2
        assert audit["apple_mail_emlx_file_count"] == 1
        assert audit["maildir_message_file_count"] == 1
        assert "13800138000" not in json.dumps(manifest, ensure_ascii=False)
        assert "private.path.account@example.net" not in json.dumps(manifest, ensure_ascii=False)
        proof = manifest["mailbox_boundary_proof"]
        assert proof["proof_level"] == "authorized_local_email_scan_boundary"
        assert proof["local_export_boundary"]["local_scan_imported_email_count"] == 2
        assert proof["local_export_boundary"]["attachment_bodies_included"] is False

        probe_payload = json.loads(probe.read_text(encoding="utf-8"))
        assert probe_payload["probe_type"] == "email_local_scan"
        assert probe_payload["platform"]["resolved"] == "mac"
        assert probe_payload["mail_candidates"]["file_count"] == 2
        assert probe_payload["privacy_policy"]["credentials"] == "not_read"
        assert "13800138000" not in json.dumps(probe_payload, ensure_ascii=False)
        assert "private.path.account@example.net" not in json.dumps(probe_payload, ensure_ascii=False)


def test_local_email_import_gap_event():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        script = Path(__file__).resolve().parents[1] / "scripts" / "email_api.py"
        subprocess.run(
            [sys.executable, str(script), "import", "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [
            json.loads(line)
            for line in (out / "lake" / "email" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 1
        assert events[0]["data"]["gap"] == "email_authorized_export_missing"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_audit"]["input_count"] == 0
        assert manifest["collection_audit"]["resolved_input_file_count"] == 0
        assert manifest["collection_audit"]["imported_email_count"] == 0
        assert manifest["mailbox_boundary_proof"]["proof_level"] == "no_authorized_email_export"


def test_local_email_import_missing_input_gap_audit():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        missing = root / "missing-mail-export"
        out = root / "out"
        script = Path(__file__).resolve().parents[1] / "scripts" / "email_api.py"
        subprocess.run(
            [sys.executable, str(script), "import", "--input", str(missing), "--out-dir", str(out)],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [
            json.loads(line)
            for line in (out / "lake" / "email" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert len(events) == 1
        assert events[0]["data"]["gap"] == "email_authorized_export_missing"
        assert manifest["collection_audit"]["input_count"] == 1
        assert manifest["collection_audit"]["input_missing_count"] == 1
        assert manifest["collection_audit"]["skipped_reason_counts"] == {"input_missing": 1}
        assert manifest["collection_audit"]["path_results"][0]["status"] == "missing"
        assert manifest["mailbox_boundary_proof"]["local_export_boundary"]["input_missing_count"] == 1


def test_local_email_import_zip_package():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        zip_path = root / "mail-export.zip"
        out = root / "out"

        msg = EmailMessage()
        msg["Message-ID"] = "<zip-research@example.com>"
        msg["From"] = "Broker Research <research@broker.example>"
        msg["To"] = "Owner <owner@example.com>"
        msg["Subject"] = str(Header("策略深度报告", "utf-8"))
        msg["Date"] = "Wed, 08 Jul 2026 09:00:00 +0800"
        msg.set_content("见附件。")
        msg.add_attachment(b"pdf-bytes", maintype="application", subtype="pdf", filename="zip-report.pdf")

        with zipfile.ZipFile(zip_path, "w") as package:
            package.writestr("nested/research.eml", msg.as_bytes())
            package.writestr("../escape.eml", msg.as_bytes())
            package.writestr("C:\\escape.eml", msg.as_bytes())
            package.writestr("nested/ignored.txt", "not email")

        script = Path(__file__).resolve().parents[1] / "scripts" / "email_api.py"
        subprocess.run(
            [
                sys.executable,
                str(script),
                "import",
                "--input",
                str(zip_path),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T12:30:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [
            json.loads(line)
            for line in (out / "lake" / "email" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 1
        assert events[0]["raw_ref"]["archive_member"] == "nested/research.eml"
        assert events[0]["data"]["attachment_refs"][0]["filename"] == "zip-report.pdf"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["collection_audit"]["archive_count"] == 1
        assert manifest["collection_audit"]["archive_member_count"] == 4
        assert manifest["collection_audit"]["archive_member_imported_email_count"] == 1
        assert manifest["collection_audit"]["skipped_archive_member_count"] == 3
        assert manifest["collection_audit"]["skipped_archive_member_reason_counts"] == {
            "unsafe_path": 2,
            "unsupported_extension": 1,
        }
        assert manifest["collection_audit"]["archive_path_traversal_members_collected"] is False
        assert manifest["collection_audit"]["windows_drive_archive_members_collected"] is False
        assert manifest["attachment_policy"]["attachment_bodies_included"] is False
        proof = manifest["mailbox_boundary_proof"]
        assert proof["local_export_boundary"]["archive_member_count"] == 4
        assert proof["local_export_boundary"]["archive_member_imported_email_count"] == 1
        assert proof["local_export_boundary"]["skipped_archive_member_reason_counts"] == {
            "unsafe_path": 2,
            "unsupported_extension": 1,
        }


def test_local_email_import_zip_supports_emlx_and_maildir_members():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        zip_path = root / "mail-local-formats.zip"
        out = root / "out"

        apple_msg = EmailMessage()
        apple_msg["Message-ID"] = "<zip-apple@example.com>"
        apple_msg["From"] = "Broker Research <research@broker.example>"
        apple_msg["To"] = "Owner <owner@example.com>"
        apple_msg["Subject"] = str(Header("ZIP Apple Mail 策略", "utf-8"))
        apple_msg.set_content("Apple Mail ZIP 成员。")
        apple_raw = apple_msg.as_bytes()

        maildir_msg = EmailMessage()
        maildir_msg["Message-ID"] = "<zip-maildir@example.com>"
        maildir_msg["From"] = "IR <ir@company.example>"
        maildir_msg["To"] = "Owner <owner@example.com>"
        maildir_msg["Subject"] = str(Header("ZIP Maildir 路演", "utf-8"))
        maildir_msg.set_content("Maildir ZIP 成员。")

        with zipfile.ZipFile(zip_path, "w") as package:
            package.writestr(
                "Apple Mail/strategy.emlx",
                str(len(apple_raw)).encode("ascii") + b"\n" + apple_raw + b"\n<plist></plist>",
            )
            package.writestr("Maildir/cur/1720000001.M1P1Q1.host:2,S", maildir_msg.as_bytes())

        script = Path(__file__).resolve().parents[1] / "scripts" / "email_api.py"
        subprocess.run(
            [
                sys.executable,
                str(script),
                "import",
                "--input",
                str(zip_path),
                "--out-dir",
                str(out),
                "--collected-at",
                "2026-07-08T12:45:00+08:00",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [
            json.loads(line)
            for line in (out / "lake" / "email" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert len(events) == 2
        archive_members = {event["raw_ref"]["archive_member"]: event for event in events}
        assert archive_members["Apple Mail/strategy.emlx"]["raw_ref"]["format"] == "emlx"
        assert archive_members["Maildir/cur/1720000001.M1P1Q1.host:2,S"]["raw_ref"]["format"] == "maildir"
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        audit = manifest["collection_audit"]
        assert audit["archive_member_count"] == 2
        assert audit["archive_member_imported_email_count"] == 2
        assert audit["skipped_archive_member_count"] == 0
        assert audit["archive_member_extension_counts"] == {".emlx": 1, "<maildir>": 1}


def test_local_email_import_zip_limit_counts_only_imported_records():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        zip_path = root / "mail-export.zip"
        out = root / "out"
        messages = []
        for index in range(2):
            msg = EmailMessage()
            msg["Message-ID"] = f"<zip-limit-{index}@example.com>"
            msg["From"] = "Broker Research <research@broker.example>"
            msg["To"] = "Owner <owner@example.com>"
            msg["Subject"] = f"策略报告 {index}"
            msg["Date"] = "Wed, 08 Jul 2026 09:00:00 +0800"
            msg.set_content("见附件。")
            messages.append(msg)
        with zipfile.ZipFile(zip_path, "w") as package:
            package.writestr("mail/one.eml", messages[0].as_bytes())
            package.writestr("mail/two.eml", messages[1].as_bytes())

        script = Path(__file__).resolve().parents[1] / "scripts" / "email_api.py"
        subprocess.run(
            [
                sys.executable,
                str(script),
                "import",
                "--input",
                str(zip_path),
                "--out-dir",
                str(out),
                "--limit",
                "1",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        events = [
            json.loads(line)
            for line in (out / "lake" / "email" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert len(events) == 1
        assert manifest["collection_audit"]["limit_reached"] is True
        assert manifest["collection_audit"]["imported_email_count"] == 1
        assert manifest["collection_audit"]["archive_member_imported_email_count"] == 1
        assert manifest["collection_audit"]["path_results"][0]["imported_email_count"] == 1


def test_register_refuses_local_password_storage():
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "email.json"
        script = Path(__file__).resolve().parents[1] / "scripts" / "email_api.py"
        env = {**os.environ, "COLLECTORX_EMAIL_STATE": str(state_path)}
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "register",
                "--email",
                "owner@qq.com",
                "--password",
                "must-not-store",
            ],
            text=True,
            capture_output=True,
            env=env,
        )
        assert result.returncode != 0
        assert not state_path.exists()


if __name__ == "__main__":
    test_email_event_without_full_body()
    test_email_event_jsonl_writer()
    test_email_event_sanitizes_attachment_and_raw_ref_secrets()
    test_provider_inference_and_multi_account_state()
    test_fake_imap_multi_folder_collection()
    test_imap_collect_standard_package()
    test_imap_collect_gap_package_without_registered_account()
    test_local_email_import_package()
    test_local_email_import_apple_mail_emlx_and_maildir()
    test_local_email_scan_package_masks_source_paths()
    test_local_email_import_gap_event()
    test_local_email_import_missing_input_gap_audit()
    test_local_email_import_zip_package()
    test_local_email_import_zip_supports_emlx_and_maildir_members()
    test_local_email_import_zip_limit_counts_only_imported_records()
    test_register_refuses_local_password_storage()
    print("All email collector event tests passed!")
