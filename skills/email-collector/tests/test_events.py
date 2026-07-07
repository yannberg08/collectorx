#!/usr/bin/env python3
"""Email collector event tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from email.header import Header
from email.message import EmailMessage


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


def _mail_bytes(subject, sender, recipient, body):
    msg = EmailMessage()
    msg["Message-ID"] = "<sample@example.com>"
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["Date"] = "Tue, 07 Jul 2026 10:00:00 +0800"
    msg.set_content(body)
    return msg.as_bytes()


def test_fake_imap_multi_folder_collection(monkeypatch=None):
    import email_api

    FakeIMAP.mailboxes = {
        ("owner@gmail.com", "INBOX"): {
            1: _mail_bytes("调研纪要", "Analyst <a@example.com>", "Owner <owner@gmail.com>", "正文A")
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


def test_local_email_import_package():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        eml_path = root / "broker-research.eml"
        json_path = root / "mail-export.json"
        csv_path = root / "mail-export.csv"
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
    test_provider_inference_and_multi_account_state()
    test_fake_imap_multi_folder_collection()
    test_local_email_import_package()
    test_local_email_import_gap_event()
    test_register_refuses_local_password_storage()
    print("All email collector event tests passed!")
